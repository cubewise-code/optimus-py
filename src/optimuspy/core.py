import configparser
import itertools
import json
import logging
import math
import os
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import List, NamedTuple, Optional

from TM1py import TM1Service
from mdxpy import MdxBuilder, Member, MdxHierarchySet

from optimuspy import tau
from optimuspy.checkpoint import CheckpointManager
from optimuspy.executors import (OriginalOrderExecutor, MainExecutor, PredefinedOrderExecutor,
                                 PositionOptimizerExecutor, DimensionOptimizerExecutor,
                                 OptimizationCancelled)
from optimuspy.metrics import (detect_is_v12, cube_memory_used_bytes, memory_by_cube_bytes,
                               ram_source_ready, read_cube_memory_bytes)
from optimuspy.resume import recover, RecoveryEffects
from optimuspy.results import ExecutionContext, OptimusResult

APP_NAME = "optimuspy"
TIME_STAMP = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
LOGFILE = APP_NAME + ".log"
RESULT_PATH = Path("results/")
RESULT_FILENAME = "{}_{}_{}"  # instance, cube_name, timestamp
DEFAULT_CONFIG_INI = "config/config.ini"


def set_current_directory():
    # determine if application is a script file or frozen exe
    if getattr(sys, 'frozen', False):
        application_path = os.path.abspath(sys.executable)
    else:
        application_path = os.path.abspath(__file__)

    directory = os.path.dirname(application_path)
    # set current directory
    os.chdir(directory)
    return directory


def get_app_base_dir() -> Path:
    """Return the application's install directory.

    For a PyInstaller frozen build this is the directory containing the executable;
    for a source/repo run it is the project root (two levels above this package:
    src/optimuspy/core.py -> repo root).
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_logfile_path() -> Path:
    """Resolve the optimuspy.log path under a logs/ directory in the install dir.

    Pinned to the install directory (see get_app_base_dir), so the log always lands
    in the same place regardless of the current working directory or a relative config
    path. The logs/ directory is created if it does not exist.
    """
    logs_dir = get_app_base_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / LOGFILE


def configure_logging():
    logging.basicConfig(
        filename=LOGFILE,
        format="%(asctime)s - " + APP_NAME + " - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # also log to stdout
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def get_tm1_config(config_ini_path: str):
    config = configparser.ConfigParser()
    config.read(config_ini_path, encoding="utf-8")
    return config


class ConfigLocation(NamedTuple):
    path: str
    read_only: bool


def resolve_config_path(cli_path: Optional[str]) -> ConfigLocation:
    """Resolve the config.ini path and whether it must be treated as read-only.

    A path supplied explicitly via --config is assumed to be owned by another tool
    (shared credentials) and is therefore read-only. The built-in default is OptimusPy's
    own file and remains writable. Existence is checked only for an explicit path
    (fail-fast); the default is left to the existing read path.
    """
    if cli_path is None:
        return ConfigLocation(DEFAULT_CONFIG_INI, read_only=False)
    if not os.path.isfile(cli_path):
        raise FileNotFoundError(cli_path)
    return ConfigLocation(cli_path, read_only=True)


def load_cube_config(path: str) -> dict:
    with open(path, 'r') as f:
        return json.load(f)


def validate_cube_config(config: dict, mode: str):
    required = ['instance', 'cube', 'executions', 'output']
    for field in required:
        if field not in config:
            raise ValueError(f"Missing required field '{field}' in cube config")

    if 'views' in config and not isinstance(config['views'], list):
        raise ValueError("'views' must be a list")

    if mode == 'set':
        if 'predefined_orders' not in config or len(config['predefined_orders']) != 1:
            raise ValueError("'set' mode requires 'predefined_orders' with exactly one entry")

    # Mutual exclusivity check
    exclusive_fields = ['predefined_orders', 'optimize_position', 'optimize_dimension']
    active = [f for f in exclusive_fields if f in config]
    if len(active) > 1:
        raise ValueError(f"Only one of {exclusive_fields} can be set. Found: {active}")

    if 'predefined_orders' in config:
        for order in config['predefined_orders']:
            if not isinstance(order, list):
                raise ValueError("Each entry in 'predefined_orders' must be a list of dimension names")

    if 'orders_to_ignore' in config:
        for order in config['orders_to_ignore']:
            if not isinstance(order, list):
                raise ValueError("Each entry in 'orders_to_ignore' must be a list of dimension names")

    if 'dimension_position_rules' in config:
        rules = config['dimension_position_rules']
        if not isinstance(rules, list):
            raise ValueError("'dimension_position_rules' must be a list")
        for rule in rules:
            if not isinstance(rule, dict) or 'dimension' not in rule or 'position' not in rule:
                raise ValueError("Each entry in 'dimension_position_rules' must have 'dimension' and 'position' keys")

    if 'optimize_position' in config:
        val = config['optimize_position']
        if val not in ('first', 'last') and not isinstance(val, int):
            raise ValueError("'optimize_position' must be 'first', 'last', or an integer (1-based)")
        if isinstance(val, int) and val < 1:
            raise ValueError("'optimize_position' must be >= 1")

    if 'optimize_dimension' in config:
        val = config['optimize_dimension']
        if not isinstance(val, str) or not val.strip():
            raise ValueError("'optimize_dimension' must be a non-empty string")

    if 'process_parameters' in config:
        pp = config['process_parameters']
        if not isinstance(pp, dict):
            raise ValueError("'process_parameters' must be a dict of {process_name: {param: value}}")
        for proc, params in pp.items():
            if not isinstance(params, dict):
                raise ValueError(f"'process_parameters[\"{proc}\"]' must be a dict of parameter values")


def resolve_position(value, num_dimensions: int) -> int:
    if value == "first":
        return 0
    if value == "last":
        return num_dimensions - 1
    pos = int(value)
    if pos < 1 or pos > num_dimensions:
        raise ValueError(f"Position {pos} out of range (1-{num_dimensions})")
    return pos - 1


def is_dimension_only_numeric(tm1: TM1Service, dimension_name: str) -> bool:
    if tm1.hierarchies.exists(dimension_name=dimension_name, hierarchy_name="Leaves"):
        hierarchy_name = "Leaves"
    else:
        hierarchy_name = dimension_name

    elements = tm1.elements.get_element_types(
        dimension_name=dimension_name,
        hierarchy_name=hierarchy_name,
        skip_consolidations=True)

    return all(e == "Numeric" for e in elements.values())


def build_vmm_vmt_mdx(cube_name: str):
    return MdxBuilder.from_cube("}CubeProperties") \
        .add_member_tuple_to_rows(Member.of("}Cubes", cube_name)) \
        .add_hierarchy_set_to_column_axis(
        MdxHierarchySet.members([
            Member.of("}CubeProperties", "VMM"),
            Member.of("}CubeProperties", "VMT")])) \
        .to_mdx()


def retrieve_vmm_vmt(tm1: TM1Service, cube_name: str) -> tuple:
    mdx = build_vmm_vmt_mdx(cube_name)
    values = list(tm1.cells.execute_mdx_values(mdx))
    return str(values[0]), str(values[1])


def write_vmm_vmt(tm1: TM1Service, cube_name: str, vmm: str, vmt: str):
    mdx = build_vmm_vmt_mdx(cube_name)
    tm1.cells.write_values_through_cellset(mdx, [vmm, vmt])


def safe_restore_dimension_order(tm1: TM1Service, cube_name: str, dimension_order: List[str]):
    """Best-effort restore of a cube's storage dimension order (crash/cancel paths).

    An interrupted run leaves the cube at the last-applied permutation. Restoring
    the true original keeps a non-resumed cube from being left reordered. Wrapped
    in suppress(Exception) because the common interruption is a dropped
    connection, which makes this a no-op — resume still recovers the work.
    """
    if not dimension_order:
        return
    with suppress(Exception):
        tm1.cubes.update_storage_dimension_order(cube_name, dimension_order)


def retrieve_ram_usage(tm1: TM1Service, cube_name: str) -> float:
    """Retrieve a cube's RAM in bytes via MetricService (cube_memory_used).

    Best-effort: returns 0.0 when the metric is absent (used only for set-mode
    before/after logging, which is wrapped in a swallowing try/except).
    """
    rows = tm1.metrics.by_cube(cube=cube_name)
    ram = cube_memory_used_bytes(rows)
    return ram if ram else 0.0


def main(mode: str, cube_config: dict, config_ini_path: str, password: str = None,
         no_resume: bool = False, tm1_checkpoint: bool = False, cancel_event=None,
         tm1_holder: dict = None) -> bool:
    instance_name = cube_config['instance']
    cube_name = cube_config['cube']
    view_names = cube_config.get('views', [])
    process_names = cube_config.get('processes', [])
    executions = cube_config['executions']
    output = cube_config['output']
    update = cube_config.get('update', False) or cube_config.get('auto_apply', False)
    fast = cube_config.get('fast', False)
    dimensions_to_exclude = cube_config.get('dimensions_to_exclude', [])
    predefined_orders = cube_config.get('predefined_orders', [])
    orders_to_ignore = cube_config.get('orders_to_ignore', [])
    dimension_position_rules = cube_config.get('dimension_position_rules', [])
    optimize_position = cube_config.get('optimize_position')
    optimize_dimension = cube_config.get('optimize_dimension')
    process_parameters = cube_config.get('process_parameters', {})

    config = get_tm1_config(config_ini_path)
    tm1_args = dict(config[instance_name])
    tm1_args['session_context'] = APP_NAME
    if password:
        tm1_args['password'] = password
        tm1_args['decode_b64'] = False

    with TM1Service(**tm1_args) as tm1:
        # Expose tm1 service for external cancellation (UI stop button)
        if tm1_holder is not None:
            tm1_holder["tm1"] = tm1

        # Detect the major version once; gates the Performance Monitor lifecycle
        # and the RAM read-retry behaviour (see optimuspy.metrics).
        is_v12 = detect_is_v12(tm1)
        logging.info(f"Connected to TM1 {'v12' if is_v12 else 'v11'} instance '{instance_name}'")

        # Validate cube exists
        if not tm1.cubes.exists(cube_name):
            logging.error(f"Cube '{cube_name}' does not exist")
            return False

        # Validate views exist
        for view_name in view_names:
            if not tm1.cubes.views.exists(cube_name, view_name, private=False):
                logging.error(f"View '{view_name}' does not exist in cube '{cube_name}'")
                return False

        # Validate processes exist
        for process_name in process_names:
            if not tm1.processes.exists(process_name):
                logging.error(f"Process '{process_name}' does not exist")
                return False

        initial_dimension_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)
        logging.info(f"Current dimension order for cube '{cube_name}': {initial_dimension_order}")

        # SET mode: apply order directly, no benchmarking
        if mode == 'set':
            return _execute_set_mode(tm1, cube_name, predefined_orders[0], is_v12)

        # OPTIMIZE mode
        return _execute_optimize_mode(
            tm1, cube_name, instance_name, view_names, process_names, executions,
            output, update, fast, dimensions_to_exclude, predefined_orders,
            orders_to_ignore, optimize_position, optimize_dimension,
            initial_dimension_order, cube_config, no_resume, tm1_checkpoint,
            process_parameters, dimension_position_rules, cancel_event, is_v12)


def _deduplicate_results(*result_lists):
    """Deduplicate PermutationResult objects by permutation_id, preserving order."""
    seen = set()
    unique = []
    for r in itertools.chain(*result_lists):
        if r is not None and r.permutation_id not in seen:
            seen.add(r.permutation_id)
            unique.append(r)
    return unique


def _recover_pending_order(tm1: TM1Service, cube_name: str, executor, pending: dict,
                           original_order_result, resumed_results: list, is_v12: bool):
    """Recover the single in-flight order (checkpoint v3 `pending`) on resume.

    Delegates the land-check + back-calc to optimuspy.resume.recover, injecting
    the executor's TM1 I/O as effects, then registers the recovered result so the
    executor never re-applies that order.
    """
    pending_order = pending["dimension_order"]
    current_order = list(tm1.cubes.get_storage_dimension_order(cube_name=cube_name))
    # % is chained from the last completed order's absolute RAM (the original if
    # nothing else completed).
    prev_abs_ram = (resumed_results[-1].ram_usage if resumed_results
                    else original_order_result.ram_usage)

    effects = RecoveryEffects(
        read_absolute_ram=lambda: read_cube_memory_bytes(tm1, cube_name, is_v12),
        apply_and_measure=lambda order: executor._evaluate_permutation(order, retrieve_ram=True),
        measure_views_processes=lambda order, abs_ram, pct: executor.measure_recovered_landed(
            order, abs_ram, pct))

    recovered = recover(pending_order, current_order, prev_abs_ram, effects)
    executor.register_recovered(recovered)
    logging.info(f"Recovered in-flight order for cube '{cube_name}': {pending_order}")


def _execute_set_mode(tm1: TM1Service, cube_name: str, target_order: List[str], is_v12: bool = False) -> bool:
    logging.info(f"SET mode: applying dimension order for cube '{cube_name}' to: {target_order}")

    # Before/after RAM logging is best-effort; never let the RAM source lifecycle
    # block the actual reorder, which is the primary purpose of set mode.
    ram_before = None
    with suppress(Exception), ram_source_ready(tm1, is_v12):
        ram_before = retrieve_ram_usage(tm1, cube_name)

    tm1.cubes.update_storage_dimension_order(cube_name, target_order)
    logging.info(f"Dimension order updated for cube '{cube_name}'")

    with suppress(Exception), ram_source_ready(tm1, is_v12):
        time.sleep(5)
        ram_after = retrieve_ram_usage(tm1, cube_name)
        if ram_before and ram_after:
            logging.info(f"RAM before: {ram_before / 1024 ** 3:.2f} GB, after: {ram_after / 1024 ** 3:.2f} GB")

    return True


def _execute_optimize_mode(tm1: TM1Service, cube_name: str, instance_name: str,
                           view_names: List[str],
                           process_names: List[str], executions: int, output: str, update: bool,
                           fast: bool, dimensions_to_exclude: List[str], predefined_orders: List[List[str]],
                           orders_to_ignore: List[List[str]], optimize_position=None,
                           optimize_dimension: str = None,
                           initial_dimension_order: List[str] = None,
                           cube_config: dict = None, no_resume: bool = False,
                           tm1_checkpoint: bool = False,
                           process_parameters: dict = None,
                           dimension_position_rules: list = None,
                           cancel_event=None, is_v12: bool = False) -> bool:
    # VMM/VMT live in the }CubeProperties control cube, which only exists on v11.
    # On v12 those caps are gone, so we neither raise nor restore them there.
    original_vmm, original_vmt = (None, None)
    if not is_v12:
        original_vmm, original_vmt = retrieve_vmm_vmt(tm1, cube_name)
        write_vmm_vmt(tm1, cube_name, "1000000", "1000000")

    displayed_dimension_order = tm1.cubes.get_dimension_names(cube_name=cube_name)
    # The live storage order (may be a crashed/reordered state); used only to
    # validate the checkpoint by dimension SET. The true original is sourced from
    # the checkpoint on resume (see below), never from this reordered read.
    current_dimension_order = initial_dimension_order

    context = ExecutionContext()
    permutation_results = []
    optimus_result = None

    # Checkpoint setup
    config_fingerprint = CheckpointManager.compute_config_fingerprint(
        cube_config,
        extra={"tau_ram": tau.TAU_RAM, "tau_query": tau.TAU_QUERY,
               "fold_b_max_passes": tau.FOLD_B_MAX_PASSES}) if cube_config else ""
    checkpoint_mgr = CheckpointManager(
        cube_name, instance_name, config_fingerprint, RESULT_PATH,
        tm1=tm1 if tm1_checkpoint else None)

    # Try to resume from checkpoint
    resumed_results = []
    original_order_result = None
    resume_state = None

    if not no_resume and checkpoint_mgr.exists():
        if checkpoint_mgr.validate(current_dimension_order):
            checkpoint_data = checkpoint_mgr.load()
            logging.info("Resuming from checkpoint — restoring previous progress")

            # The checkpoint is the source of truth for the original order — the
            # live cube may be left reordered by the interruption, so re-reading it
            # would lose the true original (baseline + end-restore target).
            initial_dimension_order = checkpoint_data["initial_dimension_order"]

            # Restore execution context
            CheckpointManager.restore_execution_context(context, checkpoint_data)

            # Restore original order result
            original_order_result = CheckpointManager.deserialize_result(
                checkpoint_data["original_order_result"])

            # Restore completed results
            resumed_results = [
                CheckpointManager.deserialize_result(r)
                for r in checkpoint_data["completed_results"]
            ]

            resume_state = checkpoint_data
            logging.info(f"Restored {len(resumed_results)} completed permutations from checkpoint")
        else:
            logging.warning("Checkpoint invalid — starting fresh")
            checkpoint_mgr.remove()
    elif no_resume and checkpoint_mgr.exists():
        logging.info("--no-resume specified — ignoring existing checkpoint")
        checkpoint_mgr.remove()

    # Determine the measure (string-last) rule from the RESOLVED original order —
    # on resume that is the checkpoint's original, not the reordered live cube,
    # whose last dim need not be the measure.
    measure_dimension_only_numeric = is_dimension_only_numeric(tm1, initial_dimension_order[-1])

    with ram_source_ready(tm1, is_v12):
        try:
            # Benchmark original order (skip if resumed)
            if original_order_result is None:
                original_executor = OriginalOrderExecutor(
                    tm1, cube_name, view_names, process_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, initial_dimension_order, context,
                    checkpoint_manager=checkpoint_mgr, process_parameters=process_parameters,
                    cancel_event=cancel_event, is_v12=is_v12)
                permutation_results += original_executor.execute()
                original_order_result = permutation_results[0]

                # Save initial checkpoint with original order result
                checkpoint_mgr.save(
                    executor_type="OriginalOrderExecutor",
                    execution_context=context,
                    initial_dimension_order=initial_dimension_order,
                    last_applied_order=initial_dimension_order,
                    original_order_result=original_order_result,
                    completed_results=[])

            # Run iterations: targeted, predefined, or greedy algorithm
            if optimize_position is not None:
                resolved_pos = resolve_position(optimize_position, len(displayed_dimension_order))
                logging.info(f"Optimizing position {resolved_pos + 1} (0-based: {resolved_pos}) "
                             f"for cube '{cube_name}'")
                executor = PositionOptimizerExecutor(
                    tm1, cube_name, view_names, process_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, resolved_pos, context, dimensions_to_exclude,
                    checkpoint_manager=checkpoint_mgr, process_parameters=process_parameters,
                    cancel_event=cancel_event, is_v12=is_v12)
            elif optimize_dimension:
                if optimize_dimension not in displayed_dimension_order:
                    raise ValueError(
                        f"Dimension '{optimize_dimension}' not found in cube '{cube_name}'. "
                        f"Available: {displayed_dimension_order}")
                logging.info(f"Optimizing dimension '{optimize_dimension}' for cube '{cube_name}'")
                executor = DimensionOptimizerExecutor(
                    tm1, cube_name, view_names, process_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, optimize_dimension, context,
                    checkpoint_manager=checkpoint_mgr, process_parameters=process_parameters,
                    cancel_event=cancel_event, is_v12=is_v12)
            elif predefined_orders:
                executor = PredefinedOrderExecutor(
                    tm1, cube_name, view_names, process_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, predefined_orders, context,
                    checkpoint_manager=checkpoint_mgr, process_parameters=process_parameters,
                    cancel_event=cancel_event, is_v12=is_v12)
            else:
                dimensions_metadata = _collect_dimension_metadata(tm1, displayed_dimension_order)
                cardinality = {d["name"]: d["leaf_elements"] for d in dimensions_metadata}
                string_dims = [d["name"] for d in dimensions_metadata if d["has_strings"]]
                executor = MainExecutor(
                    tm1, cube_name, view_names, process_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, context, fast, dimensions_to_exclude, orders_to_ignore,
                    checkpoint_manager=checkpoint_mgr, process_parameters=process_parameters,
                    dimension_position_rules=dimension_position_rules, cancel_event=cancel_event,
                    is_v12=is_v12, cardinality=cardinality, string_dims=string_dims)

            # Set resume context on executor (arm the RAM re-anchor only on a real resume)
            executor.set_resume_context(initial_dimension_order, original_order_result,
                                        resumed_results, resuming=resume_state is not None)

            # Level 2: recover the single in-flight order recorded before the drop.
            # register_recovered appends it to `resumed_results` (same list object),
            # so it flows into the merged report below.
            pending = resume_state.get("pending") if resume_state else None
            if pending:
                _recover_pending_order(
                    tm1, cube_name, executor, pending, original_order_result,
                    resumed_results, is_v12)

            # Execute (with resume state if available)
            new_results = executor.execute(resume_state=resume_state)
            permutation_results += new_results

            # Combine resumed + new results for final analysis
            unique_results = _deduplicate_results(
                [original_order_result], resumed_results, permutation_results)

            optimus_result = OptimusResult(cube_name, unique_results, instance_name=instance_name)
            best_permutation = optimus_result.best_result
            logging.info(f"Completed analysis for cube '{cube_name}'")

            if not best_permutation:
                tm1.cubes.update_storage_dimension_order(cube_name, initial_dimension_order)
                logging.info(
                    f"No ideal dimension order found for cube '{cube_name}'. "
                    f"Restored original order to {initial_dimension_order}. "
                    f"Please pick manually based on results.")
            else:
                best_order = best_permutation.dimension_order
                if update:
                    tm1.cubes.update_storage_dimension_order(cube_name, best_order)
                    logging.info(f"Updated dimension order for cube '{cube_name}' to {best_order}")
                else:
                    logging.info(f"Best order for cube '{cube_name}': {best_order}")
                    tm1.cubes.update_storage_dimension_order(cube_name, initial_dimension_order)
                    logging.info(f"Restored original dimension order for cube '{cube_name}'")

            # Success — remove checkpoint
            checkpoint_mgr.remove()

        except OptimizationCancelled:
            # Best-effort: don't leave a non-resumed cube reordered (no-op if the
            # connection is already gone; resume recovers regardless).
            safe_restore_dimension_order(tm1, cube_name, initial_dimension_order)
            raise  # Let caller (JobManager) handle cancellation cleanly
        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
            safe_restore_dimension_order(tm1, cube_name, initial_dimension_order)
            logging.info("Re-run the same command to resume from checkpoint")
            return False

        finally:
            if not is_v12:
                with suppress(Exception):
                    write_vmm_vmt(tm1, cube_name, original_vmm, original_vmt)

            # Build results from whatever we have (resumed + new)
            unique_for_output = _deduplicate_results(
                [original_order_result], resumed_results, permutation_results)

            if unique_for_output:
                if optimus_result is None:
                    optimus_result = OptimusResult(cube_name, unique_for_output, instance_name=instance_name)
                else:
                    optimus_result.instance_name = instance_name
                file_base = RESULT_FILENAME.format(instance_name, cube_name, TIME_STAMP)
                instance_dir = RESULT_PATH / instance_name

                optimus_result.to_html(instance_dir / f"{file_base}.html", total_duration=context.elapsed)

                if output.upper() == "XLSX":
                    optimus_result.to_xlsx(instance_dir / f"{file_base}.xlsx")
                else:
                    optimus_result.to_csv(instance_dir / f"{file_base}.csv")

    return True


def _compute_nibble_depth(leaf_count: int) -> int:
    """MP-Trie depth: number of hex nibbles needed to index leaf_count elements."""
    if leaf_count <= 1:
        return 1
    return math.ceil(math.log(leaf_count, 16))


def _compute_suggested_order(dimensions_metadata: list) -> dict:
    """Generate a size-based suggested dimension order.

    Rules:
    1. If any dimension has strings, it stays last (TM1 constraint)
    2. Remaining dimensions sorted by leaf element count ascending (small to large)
    3. Confidence based on ratio of largest to second-largest leaf count
    """
    dims = list(dimensions_metadata)

    # Separate string-locked dims (must be last)
    string_dims = [d for d in dims if d["has_strings"]]
    non_string_dims = [d for d in dims if not d["has_strings"]]

    # Sort non-string dims by leaf count ascending
    non_string_dims.sort(key=lambda d: d["leaf_elements"])

    # Build suggested order: small to large, strings at end
    suggested = non_string_dims + string_dims
    suggested_order = [d["name"] for d in suggested]

    # Compute confidence
    if len(non_string_dims) >= 2:
        sorted_by_size = sorted(non_string_dims, key=lambda d: d["leaf_elements"], reverse=True)
        largest = sorted_by_size[0]["leaf_elements"]
        second = sorted_by_size[1]["leaf_elements"]
        ratio = largest / max(second, 1)
        if ratio >= 10:
            confidence = "high"
        elif ratio >= 3:
            confidence = "medium"
        else:
            confidence = "low"
    else:
        confidence = "high"

    # Notes
    notes = []
    if string_dims:
        names = ", ".join(d["name"] for d in string_dims)
        notes.append(f"{names} locked last (has string elements)")
    if confidence == "low":
        notes.append("Dimensions are similarly sized. Density matters more than size — run greedy benchmarking.")
    if confidence == "high" and len(non_string_dims) >= 2:
        last_candidate = suggested[-1 - len(string_dims)] if string_dims else suggested[-1]
        notes.append(f"{last_candidate['name']} is clearly the largest — strong last-position candidate")

    return {
        "order": suggested_order,
        "confidence": confidence,
        "notes": notes,
    }


def _collect_dimension_metadata(tm1: TM1Service, dimension_names: list) -> list:
    """Collect per-dimension metadata (leaf count, string flag, nibble depth)."""
    dimensions_metadata = []
    for dim_name in dimension_names:
        leaf_count = tm1.elements.get_number_of_leaf_elements(
            dimension_name=dim_name, hierarchy_name=dim_name)
        string_count = tm1.elements.get_number_of_string_elements(
            dimension_name=dim_name, hierarchy_name=dim_name)
        dimensions_metadata.append({
            "name": dim_name,
            "leaf_elements": leaf_count,
            "has_strings": string_count > 0,
            "string_elements": string_count,
            "nibble_depth": _compute_nibble_depth(leaf_count),
        })
    return dimensions_metadata


def _scan_to_data(tm1: TM1Service, instance_name: str, ram_threshold_pct: int = 60,
                   include_optimized: bool = False, is_v12: bool = False) -> dict:
    """Core scan logic — returns structured data. Used by both CLI and UI."""
    with ram_source_ready(tm1, is_v12):
        # Single round-trip: cube_memory_used (bytes) for all non-control cubes.
        # by_cube() already excludes }-control cubes and the synthetic 'Cubes Total'
        # row on both v11 and v12, and converts each value to bytes by its Unit —
        # so OptimusPy's old EXCEPT/TM1FILTERBYPATTERN("}*") and Cubes-Total skip
        # logic is no longer needed.
        ram_by_cube = memory_by_cube_bytes(tm1.metrics.by_cube())

        total_model_ram = sum(ram_by_cube.values())
        if total_model_ram <= 0:
            raise ValueError("No RAM data found for non-control cubes")

        logging.info(f"Total model RAM: {total_model_ram / (1024 ** 3):.2f} GB across "
                     f"{len(ram_by_cube)} non-control cubes")

        # Sort by RAM descending and take cubes that account for up to threshold % of total
        sorted_cubes = sorted(ram_by_cube.items(), key=lambda x: x[1], reverse=True)
        ram_target = total_model_ram * (ram_threshold_pct / 100)
        cumulative_ram = 0.0
        top_cubes = []
        for cube_name, ram_bytes in sorted_cubes:
            if cumulative_ram >= ram_target:
                break
            top_cubes.append((cube_name, ram_bytes))
            cumulative_ram += ram_bytes

        logging.info(f"Selected {len(top_cubes)} cubes accounting for up to "
                     f"{ram_threshold_pct}% of model RAM")

        # Filter out already-optimized cubes (visible order != storage order)
        candidates = []
        for cube_name, ram_bytes in top_cubes:
            visible_order = tm1.cubes.get_dimension_names(cube_name=cube_name)
            storage_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)

            already_optimized = list(visible_order) != list(storage_order)
            if already_optimized and not include_optimized:
                logging.info(f"Skipping '{cube_name}' — already optimized")
                continue

            # Collect per-dimension metadata for intelligence
            dimensions_metadata = _collect_dimension_metadata(tm1, visible_order)
            suggested = _compute_suggested_order(dimensions_metadata)

            candidates.append({
                "cube_name": cube_name,
                "dimension_order": list(visible_order),
                "storage_order": list(storage_order),
                "dim_count": len(visible_order),
                "ram_bytes": ram_bytes,
                "ram_gb": ram_bytes / (1024 ** 3),
                "pct_of_total": (ram_bytes / total_model_ram) * 100,
                "already_optimized": already_optimized,
                "dimensions_metadata": dimensions_metadata,
                "suggested_order": suggested,
            })

    return {
        "total_model_ram": total_model_ram,
        "total_model_ram_gb": total_model_ram / (1024 ** 3),
        "candidates": candidates,
    }


def _scan_to_data_light(tm1: TM1Service, instance_name: str, ram_threshold_pct: int = 60,
                        include_optimized: bool = False, is_v12: bool = False) -> dict:
    """Lightweight scan — RAM + dimension names + storage order + last-dim string check only.

    Skips the expensive per-dimension metadata collection (_collect_dimension_metadata).
    Per cube: get_dimension_names (1 call) + get_storage_dimension_order (1 call)
              + get_number_of_string_elements for last dim only (1 call) = 3 API calls.
    """
    with ram_source_ready(tm1, is_v12):
        # Single round-trip: cube_memory_used (bytes) for all non-control cubes.
        # by_cube() already excludes }-control cubes and the synthetic 'Cubes Total'
        # row on both v11 and v12, and converts each value to bytes by its Unit.
        ram_by_cube = memory_by_cube_bytes(tm1.metrics.by_cube())

        total_model_ram = sum(ram_by_cube.values())
        if total_model_ram <= 0:
            raise ValueError("No RAM data found for non-control cubes")

        logging.info(f"Total model RAM: {total_model_ram / (1024 ** 3):.2f} GB across "
                     f"{len(ram_by_cube)} non-control cubes")

        # Sort by RAM descending and take cubes up to threshold %
        sorted_cubes = sorted(ram_by_cube.items(), key=lambda x: x[1], reverse=True)
        ram_target = total_model_ram * (ram_threshold_pct / 100)
        cumulative_ram = 0.0
        top_cubes = []
        for cube_name, ram_bytes in sorted_cubes:
            if cumulative_ram >= ram_target:
                break
            top_cubes.append((cube_name, ram_bytes))
            cumulative_ram += ram_bytes

        logging.info(f"Selected {len(top_cubes)} cubes accounting for up to "
                     f"{ram_threshold_pct}% of model RAM")

        candidates = []
        for cube_name, ram_bytes in top_cubes:
            visible_order = tm1.cubes.get_dimension_names(cube_name=cube_name)
            storage_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)

            already_optimized = list(visible_order) != list(storage_order)
            if already_optimized and not include_optimized:
                logging.info(f"Skipping '{cube_name}' — already optimized")
                continue

            # Only check if the LAST dimension (measure) has string elements
            last_dim = list(storage_order)[-1] if storage_order else None
            last_dim_has_strings = False
            if last_dim:
                try:
                    string_count = tm1.elements.get_number_of_string_elements(
                        dimension_name=last_dim, hierarchy_name=last_dim)
                    last_dim_has_strings = string_count > 0
                except Exception:
                    pass

            candidates.append({
                "cube_name": cube_name,
                "dimension_order": list(visible_order),
                "storage_order": list(storage_order),
                "dim_count": len(visible_order),
                "ram_bytes": ram_bytes,
                "ram_gb": ram_bytes / (1024 ** 3),
                "pct_of_total": (ram_bytes / total_model_ram) * 100,
                "already_optimized": already_optimized,
                "last_dim_has_strings": last_dim_has_strings,
            })

    return {
        "total_model_ram": total_model_ram,
        "total_model_ram_gb": total_model_ram / (1024 ** 3),
        "candidates": candidates,
    }


def _execute_scan_mode(tm1: TM1Service, instance_name: str, ram_threshold_pct: int = 60,
                       output_dir: str = None) -> bool:
    logging.info(f"Scanning instance '{instance_name}' for optimization candidates...")

    is_v12 = detect_is_v12(tm1)

    try:
        data = _scan_to_data(tm1, instance_name, ram_threshold_pct, is_v12=is_v12)
    except ValueError as e:
        logging.error(str(e))
        return False
    except Exception as e:
        logging.error(f"Scan failed: {e}", exc_info=True)
        return False

    candidates = data["candidates"]
    total_model_ram = data["total_model_ram"]

    if not candidates:
        logging.info("No candidate cubes found (all top cubes already optimized)")
        return True

    # Print table
    total_ram_gb = total_model_ram / (1024 ** 3)
    candidate_ram = sum(c["ram_gb"] for c in candidates)
    candidate_pct = sum(c["pct_of_total"] for c in candidates)

    print(f"\nCubes accounting for up to {ram_threshold_pct}% of total model RAM "
          f"({total_ram_gb:.2f} GB), not yet optimized:\n")

    max_name = max(len(c["cube_name"]) for c in candidates)
    max_name = max(max_name, 9)

    header = (f"  {'#':>3}  {'Cube Name':<{max_name}}  {'Dims':>4}  "
              f"{'RAM (GB)':>9}  {'% of Total':>10}  Dimension Order")
    print(header)
    print(f"  {'─' * 3}  {'─' * max_name}  {'─' * 4}  {'─' * 9}  {'─' * 10}  {'─' * 30}")

    for i, c in enumerate(candidates, 1):
        dims_str = str(c["dimension_order"])
        if len(dims_str) > 50:
            dims_str = dims_str[:47] + "..."
        print(f"  {i:>3}  {c['cube_name']:<{max_name}}  {c['dim_count']:>4}  "
              f"{c['ram_gb']:>9.2f}  {c['pct_of_total']:>9.1f}%  {dims_str}")

    print(f"\n  Total: {len(candidates)} cubes, {candidate_ram:.2f} GB "
          f"({candidate_pct:.1f}% of model RAM)\n")

    # Generate JSON configs if output directory specified
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        for c in candidates:
            config_data = {
                "instance": instance_name,
                "cube": c["cube_name"],
                "views": [],
                "executions": 5,
                "output": "csv",
            }
            config_path = os.path.join(output_dir, f"{c['cube_name']}.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

        logging.info(f"Generated {len(candidates)} config files in {output_dir}/")
    else:
        print("  To generate config files: re-run with --output <directory>\n")

    return True
