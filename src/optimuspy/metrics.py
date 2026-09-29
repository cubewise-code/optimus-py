"""Version-agnostic per-cube RAM source backed by TM1py's MetricService.

OptimusPy reads a cube's memory (the ``cube_memory_used`` metric) from
``tm1.metrics`` (TM1py >= 2.3.0) on both TM1 v11 and v12, replacing the
v11-only ``}StatsByCube`` control-cube MDX lookups.

MetricService normalises metric *names* across versions but **not** their
units: ``cube_memory_used`` is reported in ``B`` on v11 and ``KB`` on v12.
Every value is converted to bytes at this read boundary so all downstream
``/ 1024 ** 3`` GB math is unchanged. An unknown unit fails loud — the raw
number is never passed through, because a silent unit change would corrupt
every RAM comparison OptimusPy makes.
"""
import logging
import time
from contextlib import contextmanager, suppress

# Canonical MetricService metric name for a cube's total memory (both versions).
CUBE_MEMORY_METRIC = "cube_memory_used"

# Populated-cell counts, from the same by_cube() payload as the memory metric.
# They are the cross-check on it: they have been observed reporting correctly on
# a cube whose cube_memory_used was still a skeleton.
_POPULATED_CELL_METRICS = (
    "cube_num_populated_numeric_cells",
    "cube_num_populated_string_cells",
)

# Floor for bytes-per-populated-cell. Set far below any real density (a small
# numeric cube measures in the low hundreds of bytes per cell) so that only
# arithmetically impossible readings trip it.
_MIN_BYTES_PER_POPULATED_CELL = 1.0

# MetricService 'Unit' tag -> multiplier to bytes. Do not "simplify" this to a
# hardcoded x1024: the whole point of reading Unit is to stay correct when the
# server reports a different unit (B on v11, KB on v12, and so on).
_UNIT_TO_BYTES = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
}

# v11 read-retry loop: the Performance Monitor samples on an interval, so the
# metric can be empty for a short window right after activation. v11 behaviour is
# frozen — this retry-on-empty is unchanged from the }StatsByCube era.
_V11_RETRY_ATTEMPTS = 4
_V11_RETRY_WAIT_SECONDS = 15

# v12 stabilization: poll cube_memory_used until it plateaus — a re-read no
# longer materially larger than the largest seen. That is sound against a gauge
# still RISING, which is what the loop was written for. In practice v12 has been
# measured tracking a reorder to the byte within about a second, so it normally
# returns on the second read.
#
# What it CANNOT detect is a gauge flat at the wrong value. Two equal reads are
# the same observation whether the cube has settled at its true size or is
# reporting an unmaterialised skeleton, and the loop returns either way.
#
# That case is not a gauge defect, and it is not version-specific. A cube whose
# data is not resident genuinely costs the same in every order, so a skeletal
# reading is TRUTHFUL — and so is the 0% that every reorder then returns. This
# is the point that matters: those two failures are not independent. They are
# one cause seen twice, so the %-chain cannot be relied on to route around a
# skeletal baseline; when the baseline is skeletal the percentages are dead too.
# bytes_per_cell_is_implausible() below refuses such a reading outright, using
# populated-cell counts that arrive in the same by_cube() payload and report
# correctly even while cube_memory_used does not.
_V12_STABILIZE_ATTEMPTS = 6
_V12_STABILIZE_WAIT_SECONDS = 10
_V12_STABILIZE_TOLERANCE = 0.01  # 1% — a read within this of the max is "plateaued"


def detect_is_v12(tm1) -> bool:
    """Return True if the connected TM1 server is v12+.

    Parse this once per connection and thread the boolean down; it gates the
    Performance Monitor lifecycle and the read-retry behaviour.
    """
    version = tm1.server.get_product_version()
    major = int(str(version).split(".")[0])
    return major >= 12


def unit_to_bytes(value, unit) -> float:
    """Convert a MetricService memory value to bytes using its reported Unit.

    Fails loud on an unknown unit — never passes the raw number through.
    """
    try:
        multiplier = _UNIT_TO_BYTES[unit]
    except KeyError:
        raise RuntimeError(
            f"Unknown Unit '{unit}' for {CUBE_MEMORY_METRIC}; "
            f"expected one of {sorted(_UNIT_TO_BYTES)}. Refusing to pass the "
            f"value through unconverted.")
    return float(value) * multiplier


def cube_memory_used_bytes(rows) -> float:
    """Pick the cube_memory_used row from a single-cube ``by_cube()`` result, in bytes.

    Returns None if the metric is absent or has no value, so the caller can
    decide whether that is a hard error (v12) or retry-worthy (v11).
    """
    for row in rows:
        if row.get("Metric") != CUBE_MEMORY_METRIC:
            continue
        value = row.get("Value")
        if value is None:
            return None
        return unit_to_bytes(value, row.get("Unit"))
    return None


def memory_by_cube_bytes(rows) -> dict:
    """Pivot unfiltered ``by_cube()`` rows to ``{cube_name: bytes}`` for cube_memory_used.

    ``by_cube()`` already excludes ``}``-control cubes and the synthetic
    ``Cubes Total`` row on both versions, so no manual filtering is needed.
    """
    result = {}
    for row in rows:
        if row.get("Metric") != CUBE_MEMORY_METRIC:
            continue
        value = row.get("Value")
        if value is None:
            continue
        cube = row.get("CubeName")
        if not cube:
            continue
        result[cube] = unit_to_bytes(value, row.get("Unit"))
    return result


def populated_cell_count(rows):
    """Total populated cells (numeric + string) from a single-cube ``by_cube()`` result.

    Returns None when the server reported neither count, so a caller can tell
    "no cells" apart from "no answer".
    """
    total = None
    for row in rows:
        if row.get("Metric") not in _POPULATED_CELL_METRICS:
            continue
        value = row.get("Value")
        if value is None:
            continue
        total = (total or 0) + int(value)
    return total


def bytes_per_cell_is_implausible(ram_bytes, rows):
    """Reason string if this RAM reading is too small for the cells reported, else None.

    A cube that is not resident reports a skeleton for ``cube_memory_used``
    while ``cube_num_populated_*_cells`` in the very same payload reports the
    truth. That pairing is the tell, and it is arithmetic rather than a guess:
    40,960 B against 300,000 populated cells is 0.137 bytes per cell, which no
    storage engine can produce — a real reading on a cube that size is about
    224 B/cell. Optimising against such a baseline
    is worse than not running, because every order costs the same and the search
    returns a confident tie-break.

    The floor is deliberately far below any plausible real density. This is a
    check for readings that are impossible, not readings that are surprising;
    anything near the boundary is left alone rather than second-guessed.

    Silent (returns None) when the counts are absent or zero — an empty cube
    legitimately costs almost nothing, and a server that does not report cell
    counts gets no verdict rather than a fabricated one.
    """
    cells = populated_cell_count(rows)
    if not cells or not ram_bytes:
        return None
    density = float(ram_bytes) / cells
    if density >= _MIN_BYTES_PER_POPULATED_CELL:
        return None
    return (f"{ram_bytes:,.0f} bytes for {cells:,} populated cells is "
            f"{density:.4f} bytes/cell, below the {_MIN_BYTES_PER_POPULATED_CELL} "
            f"bytes/cell floor")


def _checked(ram_bytes, rows, cube_name):
    """Return the reading, or refuse it when the cell counts say it cannot be real."""
    reason = bytes_per_cell_is_implausible(ram_bytes, rows)
    if reason:
        raise RuntimeError(
            f"Refusing the {CUBE_MEMORY_METRIC} reading for cube '{cube_name}': "
            f"{reason}. The cube's data is almost certainly not resident yet — "
            f"an unmaterialised cube costs the same in every order, so this run "
            f"would measure nothing and still report a winner. Let the load "
            f"settle and re-run.")
    return ram_bytes


def read_cube_memory_bytes(tm1, cube_name: str, is_v12: bool) -> float:
    """Read one cube's RAM baseline in bytes via MetricService.

    v11: retry the read (the Performance Monitor populates on an interval), then
    fail with the historical "Performance Monitor must be activated" message.
    v12: an absent metric is a hard error, but a present value is read until it
    plateaus. A plateau is weaker evidence than it sounds — see the stabilization
    note above for what that does and does not rule out.

    Both paths then put the reading past ``bytes_per_cell_is_implausible``, which
    is the part that catches what a plateau cannot.
    """
    if is_v12:
        best = None
        for attempt in range(_V12_STABILIZE_ATTEMPTS):
            rows = tm1.metrics.by_cube(cube=cube_name)
            ram = cube_memory_used_bytes(rows)
            if ram is None:
                raise RuntimeError(
                    f"No {CUBE_MEMORY_METRIC} reported for cube '{cube_name}' — "
                    f"metric unavailable or cube not yet populated.")
            # Plateaued: this read is not materially larger than the largest seen.
            if best is not None and ram <= best * (1 + _V12_STABILIZE_TOLERANCE):
                return _checked(max(best, ram), rows, cube_name)
            best = ram if best is None else max(best, ram)
            if attempt < _V12_STABILIZE_ATTEMPTS - 1:
                logging.info("v12 cube_memory_used still rising; waiting for it to settle")
                time.sleep(_V12_STABILIZE_WAIT_SECONDS)
        return _checked(best, rows, cube_name)

    for attempt in range(_V11_RETRY_ATTEMPTS):
        rows = tm1.metrics.by_cube(cube=cube_name)
        ram = cube_memory_used_bytes(rows)
        if ram:
            return _checked(ram, rows, cube_name)

        logging.info("Failed to retrieve RAM consumption. Waiting 15s before retry")
        if attempt < _V11_RETRY_ATTEMPTS - 1:
            time.sleep(_V11_RETRY_WAIT_SECONDS)

    raise RuntimeError("Performance Monitor must be activated")


@contextmanager
def ram_source_ready(tm1, is_v12: bool):
    """Ensure cube_memory_used is readable for the duration of the block.

    v11: capture the Performance Monitor's prior state, activate it if it was
    off, and restore the prior state on exit (via the v11-only ``tm1.metrics``
    lifecycle methods).
    v12: no-op — the metric is always available and those lifecycle methods
    raise on v12.
    """
    prior_state = None
    if not is_v12:
        prior_state = tm1.metrics.get_performance_monitor_state()
        if not prior_state:
            tm1.metrics.start_performance_monitor()
    try:
        yield
    finally:
        if not is_v12 and prior_state is not None and not prior_state:
            with suppress(Exception):
                tm1.metrics.stop_performance_monitor()
