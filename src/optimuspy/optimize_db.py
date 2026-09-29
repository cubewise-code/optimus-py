"""Instance-wide heuristic dimension-order pass — "Optimize DB" mode.

What it is: a bulk `set` pass over every cube in an instance. Each cube gets the
cardinality heuristic applied once (leaf-count ascending, string dimensions
handled per policy), one cube at a time, under a wall-clock budget. Nothing is
benchmarked: no permutation is tested, and the only evidence of improvement is
the percentage `update_storage_dimension_order` returns.

Why it exists: running the measured optimizer (`optimize` mode) cube by cube
across a whole model is a multi-day exercise carried out at full memory
footprint. Applying the heuristic to the entire instance first, then restarting
the server, lowers the footprint enough to make the real exercise cheaper.
Smallest-to-largest is not a guaranteed optimal order, but it lands close on
most cubes.

Three artifacts, one job each:

* **plan**  (`optdb_plan_<plan_id>.json`) — what would run, in what order, with
  what target order, plus every skip reason and the chores that were active when
  the plan was built. Produced by `--dry-run`; contains no server writes.
* **run**   (`optdb_run_<plan_id>.json`) — live execution state: per-cube status,
  original order (for revert), pre-reorder RAM, measured `%`, durations, and the
  chore lifecycle state. Written after every transition, so it doubles as the
  resume point and the crash-time record of which chores are still disabled.
* **report** — the console summary rendered from the run.

The time budget is checked only *between* cubes. An in-flight
`tm1.ReorderDimensions` is a blocking server-side rebuild with no safe abort, so
the run can overshoot by the duration of whatever cube it last started. That is
by design: the budget exists to stop the sweep from running forever, not to
guarantee an end time.
"""
import fnmatch
import glob
import json
import logging
import math
import statistics
import time
from contextlib import suppress
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from optimuspy.core import RESULT_PATH, _dimension_metadata
from optimuspy.metrics import (detect_is_v12, memory_by_cube_bytes, ram_source_ready,
                               read_cube_memory_bytes)

PLAN_SCHEMA = 1
RUN_SCHEMA = 1

PLAN_PREFIX = "optdb_plan_"
RUN_PREFIX = "optdb_run_"

# Reconnect ladder for a dropped connection. Three attempts, then the run is
# failed — a server that is still unreachable after four minutes is down, and
# nothing further is safe to attempt against it.
RECONNECT_BACKOFF_SECONDS = (30, 60, 120)

# Throughput window for the "will the next cube fit?" estimate. A single sample
# (the previous cube) is what the model asks for, but one cube that hit lock
# contention would poison the next decision, so the median of the last few
# samples is used instead. Same model, less jitter.
THROUGHPUT_WINDOW = 3

DEFAULT_OPTIONS = {
    "time_limit_hours": 8.0,
    "order": "asc",
    "exclude_cubes": [],
    "min_cube_mb": 10.0,
    "string_policy": "skip_any",
    "include_optimized": False,
    "revert_on_regression": True,
    "disable_active_chores": False,
    "max_consecutive_failures": 3,
}

STRING_POLICIES = ("skip_any", "pin_last")
CUBE_ORDERS = ("asc", "desc")

SKIP_LABELS = {
    "excluded": "excluded by instructions",
    "empty": "no memory in use",
    "below_min_ram": "below minimum cube size",
    "too_few_dimensions": "fewer than 3 dimensions",
    "already_optimized": "already optimized",
    "string_elements": "has string elements",
    "multiple_string_dims": "more than one dimension with strings",
    "already_in_target_order": "already in target order",
}


class OptimizeDbAborted(RuntimeError):
    """The run cannot continue (server unreachable, or too many failures)."""


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

def validate_db_config(config: dict):
    """Validate an Optimize DB instructions document.

    Instance-scoped, deliberately not the per-cube schema: `cube`, `executions`
    and `output` have no meaning for a whole-instance sweep.
    """
    if not isinstance(config, dict):
        raise ValueError("Instructions must be a JSON object")
    if not config.get("instance"):
        raise ValueError("Missing required field 'instance' in optimize-db instructions")

    limit = config.get("time_limit_hours", DEFAULT_OPTIONS["time_limit_hours"])
    if not isinstance(limit, (int, float)) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("'time_limit_hours' must be a positive number")

    order = config.get("order", DEFAULT_OPTIONS["order"])
    if order not in CUBE_ORDERS:
        raise ValueError(f"'order' must be one of {list(CUBE_ORDERS)}")

    policy = config.get("string_policy", DEFAULT_OPTIONS["string_policy"])
    if policy not in STRING_POLICIES:
        raise ValueError(f"'string_policy' must be one of {list(STRING_POLICIES)}")

    excluded = config.get("exclude_cubes", [])
    if not isinstance(excluded, list) or any(not isinstance(c, str) for c in excluded):
        raise ValueError("'exclude_cubes' must be a list of cube names")

    min_mb = config.get("min_cube_mb", DEFAULT_OPTIONS["min_cube_mb"])
    if not isinstance(min_mb, (int, float)) or isinstance(min_mb, bool) or min_mb < 0:
        raise ValueError("'min_cube_mb' must be a non-negative number")

    failures = config.get("max_consecutive_failures", DEFAULT_OPTIONS["max_consecutive_failures"])
    if not isinstance(failures, int) or isinstance(failures, bool) or failures < 1:
        raise ValueError("'max_consecutive_failures' must be an integer >= 1")

    for flag in ("include_optimized", "revert_on_regression", "disable_active_chores"):
        if flag in config and not isinstance(config[flag], bool):
            raise ValueError(f"'{flag}' must be true or false")


def resolve_options(config: dict) -> dict:
    """Merge instructions over the defaults into a complete option set."""
    options = dict(DEFAULT_OPTIONS)
    for key in DEFAULT_OPTIONS:
        if key in config:
            options[key] = config[key]
    options["exclude_cubes"] = list(options["exclude_cubes"])
    options["time_limit_hours"] = float(options["time_limit_hours"])
    options["min_cube_mb"] = float(options["min_cube_mb"])
    return options


# ---------------------------------------------------------------------------
# Planner — pure, no TM1
# ---------------------------------------------------------------------------

def _is_excluded(cube_name: str, patterns: List[str]) -> bool:
    """TM1 object names are case-insensitive; `*`/`?` wildcards are supported."""
    name = cube_name.casefold()
    return any(fnmatch.fnmatch(name, p.casefold()) for p in patterns)


def cheap_skip_reason(cube_name: str, ram_bytes: float, options: dict) -> Optional[str]:
    """Skip rules decidable from the RAM snapshot alone — no per-cube API calls.

    Applied by the collector to avoid fetching metadata for cubes that can never
    run, and re-applied by `resolve_target_order` so the planner stays the single
    authority on what is skipped and why.
    """
    if _is_excluded(cube_name, options["exclude_cubes"]):
        return "excluded"
    if ram_bytes <= 0:
        return "empty"
    if ram_bytes < options["min_cube_mb"] * 1024 ** 2:
        return "below_min_ram"
    return None


def resolve_target_order(record: dict, options: dict) -> Tuple[Optional[List[str]], Optional[str]]:
    """Return `(target_order, None)` for a cube worth reordering, else `(None, reason)`.

    The target order is always leaf-count ascending — that is the heuristic. The
    `order` option controls the order cubes are *processed* in, not the order
    dimensions are placed in.
    """
    reason = cheap_skip_reason(record["cube"], record["ram_bytes"], options)
    if reason:
        return None, reason

    dimensions = list(record.get("storage_order") or [])
    if len(dimensions) < 3:
        return None, "too_few_dimensions"

    # A storage order that differs from the presentation order was set on
    # purpose, often by a measured optimization; the heuristic would overwrite it.
    visible = record.get("visible_order")
    if not options["include_optimized"] and visible is not None and list(visible) != dimensions:
        return None, "already_optimized"

    meta = record.get("dimensions") or {}
    string_dims = [d for d in dimensions if meta.get(d, {}).get("has_strings")]

    if string_dims and options["string_policy"] == "skip_any":
        return None, "string_elements"
    if len(string_dims) > 1:
        # TM1 keeps string values in the last dimension; with two string
        # dimensions there is no safe placement, and it needs separate analysis.
        return None, "multiple_string_dims"

    numeric = [d for d in dimensions if d not in string_dims]
    numeric.sort(key=lambda d: (meta.get(d, {}).get("leaf_elements", 0), d))
    target = numeric + string_dims

    if target == dimensions:
        return None, "already_in_target_order"
    return target, None


def build_plan(instance: str, plan_id: str, options: dict, cube_records: List[dict],
               total_model_ram: float, active_chores: List[str],
               created_at: float = None) -> dict:
    """Turn collected cube records into an ordered plan plus a skip ledger.

    Pure: every TM1 read has already happened. `cube_records` entries carry
    `cube`, `ram_bytes`, `storage_order`, `visible_order` (the presentation
    order, None when it wasn't read) and `dimensions`
    (`{name: {leaf_elements, has_strings, ...}}`).
    """
    queue, skipped = [], []
    for record in cube_records:
        target, reason = resolve_target_order(record, options)
        if reason:
            skipped.append({
                "cube": record["cube"],
                "ram_bytes": record["ram_bytes"],
                "reason": reason,
            })
            continue
        queue.append({
            "cube": record["cube"],
            "ram_bytes": record["ram_bytes"],
            "current_order": list(record["storage_order"]),
            "target_order": target,
        })

    queue.sort(key=lambda c: (c["ram_bytes"], c["cube"]), reverse=options["order"] == "desc")
    skipped.sort(key=lambda c: (-c["ram_bytes"], c["cube"]))

    planned_ram = sum(c["ram_bytes"] for c in queue)
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": plan_id,
        "instance": instance,
        "created_at": created_at if created_at is not None else time.time(),
        "options": options,
        "total_model_ram_bytes": total_model_ram,
        "planned_ram_bytes": planned_ram,
        "coverage_pct": (planned_ram / total_model_ram * 100) if total_model_ram else 0.0,
        "active_chores": list(active_chores),
        "cubes": queue,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

def estimate_seconds(ram_bytes: float, samples: List[List[float]]) -> Optional[float]:
    """Estimate a cube's reorder duration from observed throughput.

    `samples` are `[bytes, seconds]` pairs from completed reorders. Returns None
    when there is nothing to extrapolate from (the first cube of a run always
    runs). Equivalent to scaling the previous duration by the RAM ratio, but
    taken over the last few cubes so one outlier cannot decide the next stop.
    """
    rates = [b / s for b, s in samples[-THROUGHPUT_WINDOW:] if s > 0 and b > 0]
    if not rates:
        return None
    return ram_bytes / statistics.median(rates)


def fits_in_budget(ram_bytes: float, samples: List[List[float]], now: float,
                   deadline: float) -> Tuple[bool, Optional[float]]:
    """Decide whether to start the next cube. Returns `(fits, estimate_seconds)`."""
    if now >= deadline:
        return False, estimate_seconds(ram_bytes, samples)
    estimate = estimate_seconds(ram_bytes, samples)
    if estimate is None:
        return True, None
    return (now + estimate) <= deadline, estimate


def format_duration(seconds: float) -> str:
    if seconds is None:
        return "n/a"
    seconds = max(0.0, float(seconds))
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.2f}h"


def _gb(value: float) -> float:
    return (value or 0.0) / 1024 ** 3


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect_cube_records(tm1, ram_by_cube: dict, options: dict) -> List[dict]:
    """Read storage order and dimension shape for every cube worth planning.

    One `get_storage_dimension_order` per surviving cube (plus one
    `get_dimension_names` unless `include_optimized` is set), and two element reads
    per *unique* dimension — dimensions are shared across cubes, so the cache is
    what keeps an instance-wide sweep to minutes.
    """
    dim_cache = {}
    records = []
    total = len(ram_by_cube)
    for index, (cube_name, ram_bytes) in enumerate(ram_by_cube.items(), 1):
        if cheap_skip_reason(cube_name, ram_bytes, options):
            records.append({"cube": cube_name, "ram_bytes": ram_bytes,
                            "storage_order": None, "visible_order": None, "dimensions": {}})
            continue
        try:
            storage_order = list(tm1.cubes.get_storage_dimension_order(cube_name=cube_name))
            # Only needed to skip cubes that are already optimized.
            visible_order = (None if options["include_optimized"]
                             else list(tm1.cubes.get_dimension_names(cube_name=cube_name)))
            dimensions = {d: _cached_dimension(tm1, d, dim_cache) for d in storage_order}
        except Exception as e:
            logging.warning(f"Could not inspect cube '{cube_name}', excluding from plan: {e}")
            continue
        records.append({"cube": cube_name, "ram_bytes": ram_bytes,
                        "storage_order": storage_order, "visible_order": visible_order,
                        "dimensions": dimensions})
        if index % 25 == 0:
            logging.info(f"Planning: inspected {index} of {total} cubes")
    return records


def _cached_dimension(tm1, dim_name: str, cache: dict) -> dict:
    if dim_name not in cache:
        cache[dim_name] = _dimension_metadata(tm1, dim_name)
    return cache[dim_name]


def list_active_chores(tm1) -> List[str]:
    """Names of every chore currently active. One call."""
    return sorted(chore.name for chore in tm1.chores.get_all() if chore.active)


def create_plan(tm1, instance: str, options: dict, is_v12: bool = False,
                plan_id: str = None) -> dict:
    """Build a plan. Read-only: no reorder, no chore change, no server write."""
    plan_id = plan_id or new_plan_id(instance)
    logging.info(f"Building Optimize DB plan '{plan_id}' for instance '{instance}'")

    with ram_source_ready(tm1, is_v12):
        ram_by_cube = memory_by_cube_bytes(tm1.metrics.by_cube())
    total_model_ram = sum(ram_by_cube.values())
    if total_model_ram <= 0:
        raise ValueError("No RAM data found for non-control cubes")
    logging.info(f"Total model RAM: {_gb(total_model_ram):.2f} GB across {len(ram_by_cube)} cubes")

    records = collect_cube_records(tm1, ram_by_cube, options)

    active_chores = []
    try:
        active_chores = list_active_chores(tm1)
    except Exception as e:
        logging.warning(f"Could not read chores: {e}")
    if active_chores:
        logging.info(f"{len(active_chores)} chore(s) currently active")

    plan = build_plan(instance, plan_id, options, records, total_model_ram, active_chores)
    logging.info(f"Plan '{plan_id}': {len(plan['cubes'])} cubes to reorder "
                 f"({_gb(plan['planned_ram_bytes']):.2f} GB, {plan['coverage_pct']:.1f}% of model RAM), "
                 f"{len(plan['skipped'])} skipped")
    return plan


def new_plan_id(instance: str) -> str:
    return f"{instance}_{time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())}"


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def plan_path(plan_id: str, instance: str, result_path: Path = RESULT_PATH) -> Path:
    return Path(result_path) / instance / f"{PLAN_PREFIX}{plan_id}.json"


def run_path(plan_id: str, instance: str, result_path: Path = RESULT_PATH) -> Path:
    return Path(result_path) / instance / f"{RUN_PREFIX}{plan_id}.json"


def write_json(path: Path, payload: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def read_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def find_run(plan_id: str, result_path: Path = RESULT_PATH) -> Tuple[Path, dict]:
    """Locate a run artifact by plan id, without needing the instance name."""
    matches = sorted(Path(result_path).glob(f"*/{RUN_PREFIX}{glob.escape(plan_id)}.json"))
    if not matches:
        raise FileNotFoundError(f"No Optimize DB run found for plan id '{plan_id}'")
    return matches[0], read_json(matches[0])


def list_runs(result_path: Path = RESULT_PATH) -> List[dict]:
    """Summaries of every run on disk, newest first — powers the UI recovery list."""
    summaries = []
    for path in Path(result_path).glob(f"*/{RUN_PREFIX}*.json"):
        try:
            run = read_json(path)
        except Exception as e:
            logging.warning(f"Skipping unreadable run file '{path}': {e}")
            continue
        summaries.append({
            "plan_id": run.get("plan_id"),
            "instance": run.get("instance"),
            "status": run.get("status"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "chores_state": run.get("chores", {}).get("state"),
            "chores_pending_restore": run.get("chores", {}).get("state") == "disabled",
            "cubes_total": len(run.get("cubes", {})),
            "cubes_done": sum(1 for c in run.get("cubes", {}).values()
                              if c.get("status") in ("done", "reverted")),
        })
    return sorted(summaries, key=lambda r: r.get("started_at") or 0, reverse=True)


def new_run(plan: dict, result_path: Path = RESULT_PATH) -> dict:
    started_at = time.time()
    return {
        "schema": RUN_SCHEMA,
        "plan_id": plan["plan_id"],
        "instance": plan["instance"],
        "options": plan["options"],
        "started_at": started_at,
        # The deadline is absolute and anchored to the original start: people
        # come back to work at a fixed hour regardless of what the run did
        # overnight, so a resume inherits the deadline rather than restarting it.
        "deadline_at": started_at + plan["options"]["time_limit_hours"] * 3600,
        "finished_at": None,
        "status": "running",
        "chores": {"state": "untouched", "deactivated": []},
        "cubes": {c["cube"]: {"status": "pending", "ram_before": c["ram_bytes"],
                              "original_order": c["current_order"],
                              "target_order": c["target_order"],
                              "pct_change": None, "derived": False,
                              "duration_s": None, "error": None}
                  for c in plan["cubes"]},
        "samples": [],
        "plan_path": str(plan_path(plan["plan_id"], plan["instance"], result_path)),
    }


# ---------------------------------------------------------------------------
# Chore lifecycle
# ---------------------------------------------------------------------------

def _chores_to_disable(tm1, plan: dict) -> List[str]:
    """Chores to deactivate for this run — read live, not from the plan.

    The plan's `active_chores` snapshot is what the operator reviewed, but a
    saved plan can be executed days later. Deactivating from the live state
    keeps the lifecycle symmetric: the run only ever re-activates chores it
    actually turned off, so a chore an operator disabled in the meantime stays
    disabled. Falls back to the snapshot if the chores cannot be read.
    """
    try:
        return list_active_chores(tm1)
    except Exception as e:
        logging.warning(f"Could not read live chore state, falling back to the plan: {e}")
        return list(plan.get("active_chores", []))


def disable_chores(tm1, run: dict, chore_names: List[str], save: Callable[[], None]):
    """Deactivate the given chores, recording them *before* the first call.

    Order matters: if the process dies mid-loop, the run artifact must already
    name every chore that could have been deactivated, because that file is the
    only route back to the original state.
    """
    if not chore_names:
        return
    run["chores"] = {"state": "disabled", "deactivated": list(chore_names)}
    save()
    for name in chore_names:
        try:
            tm1.chores.deactivate(name)
            logging.info(f"Deactivated chore '{name}'")
        except Exception as e:
            logging.error(f"Could not deactivate chore '{name}': {e}")


def restore_chores(tm1, run: dict, save: Callable[[], None]) -> List[str]:
    """Re-activate exactly the chores this run deactivated. Idempotent."""
    chores = run.get("chores", {})
    if chores.get("state") != "disabled":
        return []
    restored, failed = [], []
    for name in chores.get("deactivated", []):
        try:
            tm1.chores.activate(name)
            restored.append(name)
            logging.info(f"Re-activated chore '{name}'")
        except Exception as e:
            failed.append(name)
            logging.error(f"Could not re-activate chore '{name}': {e}")
    chores["state"] = "disabled" if failed else "restored"
    chores["failed"] = failed
    chores["restored_at"] = time.time()
    save()
    return restored


def restore_chores_for_plan(connect: Callable[[], object], plan_id: str,
                            result_path: Path = RESULT_PATH) -> List[str]:
    """Recovery entry point: re-enable the chores a crashed run left disabled."""
    path, run = find_run(plan_id, result_path)
    if run.get("chores", {}).get("state") != "disabled":
        logging.info(f"Run '{plan_id}' has no chores pending restore")
        return []
    with connect() as tm1:
        return restore_chores(tm1, run, lambda: write_json(path, run))


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _reconnect(connect: Callable[[], object]):
    """Reconnect after a dropped connection. Raises OptimizeDbAborted if down."""
    for attempt, wait in enumerate(RECONNECT_BACKOFF_SECONDS, 1):
        logging.warning(f"Connection lost — reconnect attempt {attempt} of "
                        f"{len(RECONNECT_BACKOFF_SECONDS)} in {wait}s")
        time.sleep(wait)
        try:
            return connect()
        except Exception as e:
            logging.warning(f"Reconnect attempt {attempt} failed: {e}")
    raise OptimizeDbAborted(
        "TM1 instance unreachable after "
        f"{len(RECONNECT_BACKOFF_SECONDS)} reconnect attempts")


def execute_plan(connect: Callable[[], object], plan: dict, run: dict,
                 save: Callable[[], None], cancel_event=None,
                 is_v12: bool = False) -> dict:
    """Run the plan cube by cube. Returns the run artifact.

    `connect` must build a fresh TM1 service; it is called again after a dropped
    connection. The caller owns persistence through `save`.
    """
    options = run["options"]
    deadline = run["deadline_at"]
    tm1 = None
    consecutive_failures = 0
    # Pessimistic by design: only the `for…else` below may say "completed". An
    # unexpected error re-raised out of the `except Exception` never touches
    # `status`, and the `finally` would otherwise persist a stale success into
    # the run artifact — making a half-finished sweep unresumable.
    status = "failed"
    try:
        # Inside the try so an instance that is already down is recorded as a
        # failed run rather than raised at an unattended operator.
        tm1 = connect()

        if options["disable_active_chores"]:
            disable_chores(tm1, run, _chores_to_disable(tm1, plan), save)

        for entry in plan["cubes"]:
            cube = entry["cube"]
            state = run["cubes"].setdefault(cube, {"status": "pending"})
            if state["status"] in ("done", "reverted", "skipped"):
                continue

            if cancel_event is not None and cancel_event.is_set():
                status = "cancelled"
                logging.info("Optimize DB stopped — no further cube will be started")
                break

            now = time.time()
            fits, estimate = fits_in_budget(entry["ram_bytes"], run["samples"], now, deadline)
            elapsed = now - run["started_at"]
            expected = "no estimate yet" if estimate is None else f"about {format_duration(estimate)}"
            decision = (f"'{cube}' ({_gb(entry['ram_bytes']):.2f} GB, {expected}) — "
                        f"{format_duration(elapsed)} of the {options['time_limit_hours']:.2f}h limit used")
            if not fits:
                logging.info(f"Not starting {decision}: it would run past the limit")
                status = "stopped_time_limit"
                break
            logging.info(f"Starting {decision}")

            try:
                tm1, outcome = _reorder_cube(tm1, connect, cube, entry, state,
                                             options, is_v12, save)
            except OptimizeDbAborted:
                status = "failed"
                save()
                raise
            finally:
                save()

            if outcome == "failed":
                consecutive_failures += 1
                if consecutive_failures >= options["max_consecutive_failures"]:
                    logging.error(f"{consecutive_failures} consecutive failures — aborting run")
                    status = "failed"
                    break
            else:
                consecutive_failures = 0
                if state.get("duration_s") and not state.get("derived"):
                    run["samples"].append([entry["ram_bytes"], state["duration_s"]])
        else:
            status = "completed"
    except OptimizeDbAborted as e:
        logging.error(str(e))
        run["error"] = str(e)
        status = "failed"
    except Exception as e:
        if tm1 is not None:
            raise
        logging.error(f"Could not connect to instance '{run['instance']}': {e}")
        run["error"] = str(e)
        status = "failed"
    finally:
        run["status"] = status
        run["finished_at"] = time.time()
        _finalize_totals(run)
        save()
        # Chores come back on every exit path — success, time limit, cancel, or
        # failure. When the instance itself is gone this cannot run, which is
        # what `--restore-chores <plan-id>` is for.
        if tm1 is not None:
            with suppress(Exception):
                restore_chores(tm1, run, save)
            with suppress(Exception):
                tm1.logout()

    return run


def _reorder_cube(tm1, connect, cube: str, entry: dict, state: dict,
                  options: dict, is_v12: bool, save: Callable[[], None]):
    """Apply one cube's target order. Returns `(service, outcome)`.

    Outcomes: `done`, `reverted`, `skipped`, `failed`. The service is returned
    because a dropped connection replaces it mid-cube.
    """
    target = entry["target_order"]

    current = list(tm1.cubes.get_storage_dimension_order(cube_name=cube))
    if current == target:
        state.update(status="skipped", reason="already_in_target_order")
        logging.info(f"'{cube}' already in target order — skipped")
        return tm1, "skipped"

    # Persisted before the rebuild is sent: if the process dies mid-reorder, the
    # artifact names the cube that was in flight, which is what lets `--resume`
    # find it and recover the `%` the dropped response took with it.
    state.update(status="in_flight", original_order=current, started_at=time.time())
    save()

    started = time.time()
    try:
        pct = tm1.cubes.update_storage_dimension_order(cube, target)
        duration = time.time() - started
        derived = False
    except Exception as e:
        duration = time.time() - started
        logging.warning(f"Reorder of '{cube}' did not return a result: {e}")
        tm1 = _reconnect(connect)
        pct, derived = _recover_outcome(tm1, cube, target, state, is_v12)
        if pct is None:
            state.update(status="failed", error=str(e), duration_s=duration)
            logging.error(f"'{cube}' failed and was left in its original order")
            return tm1, "failed"

    state.update(status="done", pct_change=pct, derived=derived,
                 duration_s=duration, error=None)
    verdict = "derived" if derived else "reported"
    logging.info(f"'{cube}' reordered in {format_duration(duration)} — "
                 f"{pct:+.2f}% RAM ({verdict})")

    if pct > 0 and options["revert_on_regression"]:
        revert_started = time.time()
        try:
            back = tm1.cubes.update_storage_dimension_order(cube, state["original_order"])
            state.update(status="reverted", revert_pct_change=back,
                         revert_duration_s=time.time() - revert_started)
            logging.info(f"'{cube}' got worse ({pct:+.2f}%) — reverted to its original order")
            return tm1, "reverted"
        except Exception as e:
            state.update(status="done", revert_error=str(e))
            logging.error(f"Could not revert '{cube}' after a {pct:+.2f}% regression: {e}")

    return tm1, "done"


def _recover_outcome(tm1, cube: str, target: List[str], state: dict, is_v12: bool):
    """Work out what happened to a reorder whose response was lost.

    `tm1.ReorderDimensions` is atomic, so the cube sits at either the original or
    the target order. When it landed, the returned `%` is gone for good — it is
    nowhere on the server — so the saving is derived from an absolute RAM read
    against the pre-reorder figure the run recorded. Derived values are tagged as
    such: they are a measurement, not the server's own arithmetic.
    """
    actual = list(tm1.cubes.get_storage_dimension_order(cube_name=cube))
    if actual != target:
        return None, False

    ram_before = state.get("ram_before")
    try:
        with ram_source_ready(tm1, is_v12):
            ram_after = read_cube_memory_bytes(tm1, cube, is_v12)
    except Exception as e:
        logging.warning(f"'{cube}' was reordered but its RAM could not be re-read: {e}")
        return math.nan, True

    if not ram_before or not ram_after:
        return math.nan, True
    return (ram_after / ram_before - 1.0) * 100.0, True


def _finalize_totals(run: dict):
    done = [c for c in run["cubes"].values() if c["status"] == "done"]
    measured = [c["pct_change"] for c in done
                if c["pct_change"] is not None and not math.isnan(c["pct_change"])]
    saved_bytes = sum((c["ram_before"] or 0) * (-c["pct_change"] / 100.0)
                      for c in done
                      if c["pct_change"] is not None and not math.isnan(c["pct_change"]))
    run["totals"] = {
        "cubes_reordered": len(done),
        "cubes_reverted": sum(1 for c in run["cubes"].values() if c["status"] == "reverted"),
        "cubes_failed": sum(1 for c in run["cubes"].values() if c["status"] == "failed"),
        "cubes_skipped": sum(1 for c in run["cubes"].values() if c["status"] == "skipped"),
        "cubes_pending": sum(1 for c in run["cubes"].values() if c["status"] == "pending"),
        "bytes_saved": saved_bytes,
        "mean_pct_change": statistics.mean(measured) if measured else None,
        "elapsed_s": (run.get("finished_at") or time.time()) - run["started_at"],
    }


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def prepare_resume(tm1, plan: dict, run: dict, is_v12: bool = False) -> int:
    """Reconcile the run artifact with the server before continuing.

    Two jobs, one storage-order read per cube — cheap next to a rebuild:

    * A cube recorded as finished that the server no longer reflects (an
      in-memory reorder lost to a hard stop, a manual change since) goes back to
      `pending` and is redone rather than being reported as a saving that is not
      there.
    * A cube left `in_flight` is the dropped-connection case. The reorder is
      atomic, so it either landed or it did not; when it landed, the `%` went
      with the lost response and the saving is re-derived from an absolute RAM
      read against the pre-reorder figure.

    Returns the number of cubes requeued.
    """
    reset = 0
    for entry in plan["cubes"]:
        cube = entry["cube"]
        state = run["cubes"].get(cube)
        if not state or state["status"] not in ("done", "reverted", "in_flight"):
            continue
        try:
            actual = list(tm1.cubes.get_storage_dimension_order(cube_name=cube))
        except Exception as e:
            logging.warning(f"Could not verify '{cube}' on resume: {e}")
            continue

        if state["status"] == "in_flight":
            pct, derived = _recover_outcome(tm1, cube, entry["target_order"], state, is_v12)
            if pct is None:
                logging.info(f"'{cube}' was interrupted before its reorder landed — will redo")
                state.update(status="pending", pct_change=None, duration_s=None, derived=False)
                reset += 1
            else:
                state.update(status="done", pct_change=pct, derived=derived)
                logging.info(f"'{cube}' was reordered before the interruption — "
                             f"{pct:+.2f}% RAM (derived)")
            continue

        expected = entry["target_order"] if state["status"] == "done" else state.get("original_order")
        if expected and actual != expected:
            logging.info(f"'{cube}' no longer matches its recorded order — will redo")
            state.update(status="pending", pct_change=None, duration_s=None, derived=False)
            reset += 1
    # `run["samples"]` deliberately survives the resume. Throughput measured on
    # this instance is still broadly valid, and wiping it would make
    # `fits_in_budget` return `(True, None)` for the first cube after every
    # resume — starting an unabortable six-hour rebuild minutes before the
    # inherited deadline.
    return reset


# ---------------------------------------------------------------------------
# Entry point — shared by the CLI verb and the UI job
# ---------------------------------------------------------------------------

def optimize_db(connect: Callable[[], object], config: dict = None, plan: dict = None,
                dry_run: bool = False, resume_plan_id: str = None,
                result_path: Path = RESULT_PATH, cancel_event=None) -> dict:
    """Plan and/or execute an Optimize DB sweep.

    Exactly one of `config` (fresh instructions), `plan` (a plan already on
    disk) or `resume_plan_id` drives the call. Returns the plan on `dry_run`,
    otherwise the run artifact.
    """
    if resume_plan_id:
        path, run = find_run(resume_plan_id, result_path)
        plan = read_json(run["plan_path"])
        if run["status"] == "completed":
            logging.info(f"Run '{resume_plan_id}' already completed — nothing to resume")
            return run
        logging.info(f"Resuming run '{resume_plan_id}' — "
                     f"{format_duration(run['deadline_at'] - time.time())} left of its original time limit")
        with connect() as tm1:
            reset = prepare_resume(tm1, plan, run, run.get("is_v12", False))
        if reset:
            logging.info(f"{reset} cube(s) no longer matched their recorded order and were requeued")
        run["status"] = "running"
        save = _saver(path, run)
        save()
        return execute_plan(connect, plan, run, save, cancel_event=cancel_event,
                            is_v12=run.get("is_v12", False))

    if plan is None:
        validate_db_config(config)
        options = resolve_options(config)
        instance = config["instance"]
        with connect() as tm1:
            is_v12 = detect_is_v12(tm1)
            plan = create_plan(tm1, instance, options, is_v12)
        plan["is_v12"] = is_v12
        write_json(plan_path(plan["plan_id"], instance, result_path), plan)
        logging.info(f"Plan written to {plan_path(plan['plan_id'], instance, result_path)}")

    if dry_run:
        return plan

    if not plan["cubes"]:
        logging.info("Plan contains no cubes to reorder — nothing to do")
        return plan

    run = new_run(plan, result_path)
    run["is_v12"] = plan.get("is_v12", False)
    path = run_path(plan["plan_id"], plan["instance"], result_path)
    save = _saver(path, run)
    save()
    logging.info(f"Optimize DB run '{plan['plan_id']}' started — "
                 f"{len(plan['cubes'])} cubes, {run['options']['time_limit_hours']:.2f}h limit, "
                 f"state in {path}")
    return execute_plan(connect, plan, run, save, cancel_event=cancel_event,
                        is_v12=run["is_v12"])


def _saver(path: Path, run: dict) -> Callable[[], None]:
    def save():
        write_json(path, run)
    return save


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_plan(plan: dict) -> str:
    """Console rendering of a plan — what `--dry-run` prints."""
    options = plan["options"]
    lines = [
        "",
        f"Optimize DB plan {plan['plan_id']}",
        f"  Instance          : {plan['instance']}",
        f"  Cube order        : {'smallest to largest' if options['order'] == 'asc' else 'largest to smallest'}",
        f"  Time limit        : {options['time_limit_hours']:.2f} h (checked between cubes only)",
        f"  String policy     : {options['string_policy']}",
        f"  Include optimized : {'yes' if options['include_optimized'] else 'no'}",
        f"  Revert regressions: {'yes' if options['revert_on_regression'] else 'no'}",
        f"  Disable chores    : {'yes' if options['disable_active_chores'] else 'no'}",
        f"  Model RAM         : {_gb(plan['total_model_ram_bytes']):.2f} GB",
        f"  Plan covers       : {_gb(plan['planned_ram_bytes']):.2f} GB "
        f"({plan['coverage_pct']:.1f}% of model RAM) across {len(plan['cubes'])} cubes",
        "",
    ]

    if plan["cubes"]:
        width = max(max(len(c["cube"]) for c in plan["cubes"]), 9)
        lines.append(f"  {'#':>3}  {'Cube Name':<{width}}  {'RAM (GB)':>9}  Target Order")
        lines.append(f"  {'─' * 3}  {'─' * width}  {'─' * 9}  {'─' * 40}")
        for i, c in enumerate(plan["cubes"], 1):
            order = " › ".join(c["target_order"])
            if len(order) > 60:
                order = order[:57] + "..."
            lines.append(f"  {i:>3}  {c['cube']:<{width}}  {_gb(c['ram_bytes']):>9.2f}  {order}")
        lines.append("")

    if plan["skipped"]:
        by_reason = {}
        for s in plan["skipped"]:
            bucket = by_reason.setdefault(s["reason"], {"count": 0, "bytes": 0.0})
            bucket["count"] += 1
            bucket["bytes"] += s["ram_bytes"]
        lines.append(f"  Skipped: {len(plan['skipped'])} cubes")
        for reason, bucket in sorted(by_reason.items(), key=lambda kv: -kv[1]["bytes"]):
            lines.append(f"    {SKIP_LABELS.get(reason, reason):<40} "
                         f"{bucket['count']:>4} cubes  {_gb(bucket['bytes']):>8.2f} GB")
        lines.append("")

    if plan["active_chores"]:
        lines.append(f"  Active chores ({len(plan['active_chores'])}): "
                     f"{', '.join(plan['active_chores'])}")
        if options["disable_active_chores"]:
            lines.append("  These will be deactivated for the run and re-activated afterwards.")
            lines.append(f"  After a crash, restore them with: "
                         f"optimuspy optimize-db --restore-chores {plan['plan_id']}")
        lines.append("")

    return "\n".join(lines)


def format_run_summary(run: dict) -> str:
    totals = run.get("totals") or {}
    status_label = {
        "completed": "completed",
        "stopped_time_limit": "stopped — time limit reached",
        "cancelled": "cancelled",
        "failed": "failed",
        "running": "running",
    }.get(run.get("status"), run.get("status"))

    lines = [
        "",
        f"Optimize DB run {run['plan_id']} — {status_label}",
        f"  Elapsed        : {format_duration(totals.get('elapsed_s'))}",
        f"  Reordered      : {totals.get('cubes_reordered', 0)} cubes",
        f"  Reverted       : {totals.get('cubes_reverted', 0)} (they used more memory after the reorder)",
        f"  Skipped        : {totals.get('cubes_skipped', 0)}",
        f"  Failed         : {totals.get('cubes_failed', 0)}",
        f"  Not started    : {totals.get('cubes_pending', 0)}",
        f"  Expected saving: {_gb(totals.get('bytes_saved', 0)):.2f} GB (visible after a restart)",
    ]
    chores = run.get("chores", {})
    if chores.get("state") == "restored":
        lines.append(f"  Chores         : {len(chores.get('deactivated', []))} re-activated")
    elif chores.get("state") == "disabled":
        lines.append(f"  Chores         : STILL DISABLED — run "
                     f"'optimuspy optimize-db --restore-chores {run['plan_id']}'")
    lines.append("")
    return "\n".join(lines)
