import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Union

from optimuspy.results import ExecutionContext, PermutationResult

CHECKPOINT_VERSION = 3

# A run's stamp, as it appears in its report and checkpoint file names.
RUN_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
_RUN_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")


def new_run_stamp() -> str:
    return time.strftime(RUN_STAMP_FORMAT, time.localtime())


class CheckpointManager:
    """Manages checkpoint files for resuming interrupted optimization runs.

    A local checkpoint is named like the run's report and sits beside it:
    results/<instance>/checkpoint_<instance>_<cube>_<run stamp>.json. The
    instance in the name keeps two servers that share a cube name from
    overwriting, or deleting, each other's checkpoint. The stamp names the run:
    `exists()` finds the checkpoint for this instance and cube whatever its
    stamp, and from then on `run_stamp` is that run's stamp, so a resumed run
    carries on under the name it started with.

    A TM1 blob checkpoint lives on the instance it belongs to, so it is named by
    cube alone; its run stamp is read from its content.
    """

    def __init__(self, cube_name: str, instance: str, config_fingerprint: str,
                 result_path: Union[str, Path] = Path("results/"), tm1=None,
                 run_stamp: str = None):
        self.cube_name = cube_name
        self.instance = instance
        self.config_fingerprint = config_fingerprint
        self.result_path = Path(result_path)
        self.tm1 = tm1  # When set, use TM1 blob storage instead of local files
        self._created_at = None
        # This run's stamp until exists() finds an earlier run's checkpoint.
        self._fresh_stamp = run_stamp or new_run_stamp()
        self.run_stamp = self._fresh_stamp

    @staticmethod
    def compute_config_fingerprint(cube_config: dict, extra: dict = None) -> str:
        payload = {"config": cube_config, "extra": extra or {}}
        config_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()

    @property
    def _prefix(self) -> str:
        return f"checkpoint_{self.instance}_{self.cube_name}_"

    @property
    def checkpoint_path(self) -> Path:
        return self.result_path / self.instance / f"{self._prefix}{self.run_stamp}.json"

    def _existing_stamps(self) -> List[str]:
        """Run stamps of this instance's checkpoints for this cube, oldest first.

        The remainder after the prefix must be exactly a stamp, so cube 'A' never
        claims the checkpoint of cube 'A_B'.
        """
        folder = self.result_path / self.instance
        if not folder.is_dir():
            return []
        stamps = []
        for f in folder.iterdir():
            if f.suffix == ".json" and f.name.startswith(self._prefix):
                stamp = f.name[len(self._prefix):-len(".json")]
                if _RUN_STAMP.fullmatch(stamp):
                    stamps.append(stamp)
        return sorted(stamps)

    @property
    def blob_name(self) -> str:
        return f"optimuspy_checkpoint_{self.cube_name}.json"

    def exists(self) -> bool:
        """Is there a checkpoint for this cube on this instance?

        When there is, the manager now points at it — `load`, `save` and `remove`
        act on that file and `run_stamp` is the stamp of the run it belongs to —
        until `discard()`.
        """
        if self.tm1:
            result = self.tm1.files.exists(self.blob_name)
            logging.info(f"TM1 blob checkpoint exists check '{self.blob_name}': {result}")
            return result
        stamps = self._existing_stamps()
        if stamps:
            self.run_stamp = stamps[-1]
        return bool(stamps)

    def discard(self):
        """Delete the checkpoint `exists()` found and go back to this run's own stamp."""
        self.remove()
        self.run_stamp = self._fresh_stamp
        self._created_at = None

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
            "run_stamp": self.run_stamp,
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
            os.makedirs(self.checkpoint_path.parent, exist_ok=True)
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
