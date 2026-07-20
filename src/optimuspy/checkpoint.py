import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Union

from optimuspy.results import ExecutionContext, PermutationResult

CHECKPOINT_VERSION = 3


class CheckpointManager:
    """Manages checkpoint files for resuming interrupted optimization runs."""

    def __init__(self, cube_name: str, instance: str, config_fingerprint: str,
                 result_path: Union[str, Path] = Path("results/"), tm1=None):
        self.cube_name = cube_name
        self.instance = instance
        self.config_fingerprint = config_fingerprint
        self.result_path = Path(result_path)
        self.tm1 = tm1  # When set, use TM1 blob storage instead of local files
        self._created_at = None

    @staticmethod
    def compute_config_fingerprint(cube_config: dict, extra: dict = None) -> str:
        payload = {"config": cube_config, "extra": extra or {}}
        config_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()

    @property
    def checkpoint_path(self) -> Path:
        return self.result_path / f"checkpoint_{self.cube_name}.json"

    @property
    def blob_name(self) -> str:
        return f"optimuspy_checkpoint_{self.cube_name}.json"

    def exists(self) -> bool:
        if self.tm1:
            result = self.tm1.files.exists(self.blob_name)
            logging.info(f"TM1 blob checkpoint exists check '{self.blob_name}': {result}")
            return result
        return self.checkpoint_path.exists()

    def load(self) -> dict:
        if self.tm1:
            logging.info(f"Loading checkpoint from TM1 blob '{self.blob_name}'")
            content = self.tm1.files.get(self.blob_name)
            return json.loads(content.decode("utf-8"))
        with open(self.checkpoint_path, "r") as f:
            return json.load(f)

    def validate(self, current_dimension_order: List[str]) -> bool:
        """Return True if the checkpoint applies to the cube's current schema.

        Validation is by dimension *set*, not order: every iterating mode leaves
        the cube physically reordered after an interruption, so the live order is
        never expected to equal the stored original. The only thing that makes the
        stored orders inapplicable is a schema change (a dimension added, removed,
        or renamed), which the set comparison catches. Version, config-fingerprint,
        cube, and instance checks are unchanged.
        """
        try:
            data = self.load()
        except Exception as e:
            logging.warning(f"Checkpoint corrupted or unreadable: {e}")
            return False

        if data.get("version") != CHECKPOINT_VERSION:
            logging.warning(f"Checkpoint version mismatch: expected {CHECKPOINT_VERSION}, "
                            f"got {data.get('version')}")
            return False

        if data.get("config_fingerprint") != self.config_fingerprint:
            logging.warning("Checkpoint config fingerprint mismatch — JSON config has changed")
            return False

        if data.get("cube_name") != self.cube_name:
            logging.warning(f"Checkpoint cube mismatch: expected '{self.cube_name}', "
                            f"got '{data.get('cube_name')}'")
            return False

        if data.get("instance") != self.instance:
            logging.warning(f"Checkpoint instance mismatch: expected '{self.instance}', "
                            f"got '{data.get('instance')}'")
            return False

        if set(data.get("initial_dimension_order") or []) != set(current_dimension_order):
            logging.warning("Checkpoint dimension set does not match current cube — "
                            "a dimension was added, removed, or renamed")
            return False

        # Cache created_at from the validated checkpoint
        self._created_at = data.get("created_at")
        return True

    def save(self, executor_type: str, execution_context: ExecutionContext,
             initial_dimension_order: List[str], last_applied_order: List[str],
             original_order_result: PermutationResult,
             completed_results: List[PermutationResult],
             executor_state: dict = None, pending: dict = None):
        now = datetime.now().isoformat(timespec="seconds")

        data = {
            "version": CHECKPOINT_VERSION,
            "cube_name": self.cube_name,
            "instance": self.instance,
            "config_fingerprint": self.config_fingerprint,
            "executor_type": executor_type,
            "initial_dimension_order": initial_dimension_order,
            "last_applied_order": last_applied_order,
            # The single in-flight order (v3): written as `submitted` before the
            # reorder, cleared to None once the full evaluation is `received`.
            "pending": pending,
            "execution_context": execution_context.to_checkpoint_dict(),
            "original_order_result": self.serialize_result(original_order_result),
            "completed_results": [self.serialize_result(r) for r in completed_results],
            "updated_at": now,
        }

        # Use cached created_at or set it on first save
        if self._created_at is None:
            self._created_at = now
        data["created_at"] = self._created_at

        # Store executor-specific state under its own key for isolation
        if executor_state:
            data["executor_state"] = executor_state

        if self.tm1:
            content = json.dumps(data, indent=2).encode("utf-8")
            logging.info(f"Saving checkpoint to TM1 blob '{self.blob_name}' ({len(content)} bytes)")
            self.tm1.files.update_or_create(self.blob_name, content)
            logging.info(f"Checkpoint saved to TM1 blob '{self.blob_name}'")
        else:
            # Atomic write: write to temp file, then rename
            os.makedirs(self.result_path, exist_ok=True)
            tmp_path = self.checkpoint_path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(self.checkpoint_path)

    def remove(self):
        if self.tm1:
            logging.info(f"Checking TM1 blob '{self.blob_name}' for removal")
            if self.tm1.files.exists(self.blob_name):
                self.tm1.files.delete(self.blob_name)
                logging.info(f"Checkpoint blob removed: {self.blob_name}")
        else:
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
                logging.info(f"Checkpoint removed: {self.checkpoint_path}")

    @staticmethod
    def serialize_result(result: PermutationResult) -> dict:
        return {
            "permutation_id": result.permutation_id,
            "mode": result.mode.value,
            "cube_name": result.cube_name,
            "view_names": result.view_names,
            "process_names": result.process_names,
            "dimension_order": list(result.dimension_order),
            "query_times_by_view": {k: list(v) for k, v in result.query_times_by_view.items()},
            "process_times_by_process": {k: list(v) for k, v in result.process_times_by_process.items()}
            if result.process_times_by_process else {},
            "ram_usage": result.ram_usage,
            "ram_percentage_change": result.ram_percentage_change,
            "ram_reduction": result.ram_reduction,
            "reorder_duration": result.reorder_duration,
        }

    @staticmethod
    def deserialize_result(data: dict) -> PermutationResult:
        return PermutationResult.from_checkpoint(data)

    @staticmethod
    def restore_execution_context(context: ExecutionContext, checkpoint: dict):
        context.restore_from_checkpoint(checkpoint["execution_context"])
