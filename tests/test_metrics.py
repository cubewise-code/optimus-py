"""metrics.py — the half that needs no server.

metrics.py is the RAM truth source for both TM1 versions and had no tests at
all. Its row-reading functions are pure: they take what ``MetricService.by_cube``
returned and convert it. A unit the module does not know must fail loud, because
passing a raw number through unconverted corrupts every RAM comparison
OptimusPy makes and does so silently — the number still looks plausible.

The rest of the module — which unit each server actually reports, the v11 retry
and the v12 plateau — needs a real instance and lives in test_live_metrics.py.

Offline, no fake.
"""
import pytest

from optimuspy.metrics import (
    CUBE_MEMORY_METRIC, bytes_per_cell_is_implausible, cube_memory_used_bytes,
    memory_by_cube_bytes, populated_cell_count, unit_to_bytes)


def _row(cube, value, unit, metric=CUBE_MEMORY_METRIC):
    return {"CubeName": cube, "Metric": metric, "Value": value, "Unit": unit}


@pytest.mark.parametrize("value, unit, expected", [
    (1, "B", 1.0),
    (1, "KB", 1024.0),
    (1, "MB", 1024.0 ** 2),
    ("2048", "KB", 2048 * 1024.0),   # MetricService can report the value as text
    (0, "B", 0.0),
])
def test_a_known_unit_converts_to_bytes(value, unit, expected):
    assert unit_to_bytes(value, unit) == expected


@pytest.mark.parametrize("unit", ["GB", "b", "", None, "bytes"])
def test_an_unknown_unit_refuses_rather_than_guessing(unit):
    # v11 reports B and v12 reports KB, so a unit nobody wrote code for means the
    # server changed under us. Guessing x1024 would be wrong by 1024x in one
    # direction and right by accident in the other.
    with pytest.raises(RuntimeError) as excinfo:
        unit_to_bytes(1, unit)
    message = str(excinfo.value)
    assert CUBE_MEMORY_METRIC in message
    assert "B" in message and "KB" in message   # names what it does accept


def test_the_cube_memory_row_is_picked_out_of_the_others():
    rows = [_row("Sales", 5, "B", metric="cube_cell_count"),
            _row("Sales", 3, "KB"),
            _row("Sales", 9, "B", metric="cube_view_count")]
    assert cube_memory_used_bytes(rows) == 3 * 1024.0


def test_an_absent_metric_reads_as_none_not_zero():
    # None is "ask again" (v11 retries, v12 raises); 0.0 would be a cube that
    # genuinely occupies nothing, and the % chain would divide by it.
    assert cube_memory_used_bytes([_row("Sales", 5, "B", metric="cube_cell_count")]) is None
    assert cube_memory_used_bytes([]) is None


def test_a_present_metric_with_no_value_reads_as_none():
    assert cube_memory_used_bytes([_row("Sales", None, "B")]) is None


def test_by_cube_rows_pivot_to_bytes_per_cube():
    rows = [_row("Sales", 2, "KB"),
            _row("Sales", 40, "B", metric="cube_cell_count"),
            _row("Budget", 1, "MB")]
    assert memory_by_cube_bytes(rows) == {"Sales": 2 * 1024.0, "Budget": 1024.0 ** 2}


def test_the_pivot_drops_rows_it_cannot_place():
    rows = [_row("Sales", None, "KB"), _row(None, 2, "KB"), _row("", 2, "KB")]
    assert memory_by_cube_bytes(rows) == {}


def test_the_pivot_still_refuses_an_unknown_unit():
    # The per-cube pivot feeds the Optimize DB planner. Skipping a row it cannot
    # convert would quietly drop a cube from the plan instead of reporting why.
    with pytest.raises(RuntimeError):
        memory_by_cube_bytes([_row("Sales", 2, "GB")])


# --- the populated-cell cross-check ----------------------------------------
#
# A cube that is not resident reports a skeleton for cube_memory_used while the
# populated-cell counts in the very same by_cube() payload report the truth.
# 40,960 bytes against 300,000 populated cells is a density no storage engine
# can produce, and both numbers are already in hand, so nothing extra has to be
# asked of the server.

def _cells(numeric=None, string=None):
    rows = []
    if numeric is not None:
        rows.append(_row("Sales", numeric, "#", metric="cube_num_populated_numeric_cells"))
    if string is not None:
        rows.append(_row("Sales", string, "#", metric="cube_num_populated_string_cells"))
    return rows


def test_populated_cells_sums_numeric_and_string():
    assert populated_cell_count(_cells(numeric=300_000, string=1_000)) == 301_000


def test_populated_cells_is_none_when_the_server_reports_neither():
    assert populated_cell_count([_row("Sales", 5, "B")]) is None


def test_an_impossible_density_is_refused():
    # 40,960 B / 300,000 cells = 0.137 bytes/cell.
    reason = bytes_per_cell_is_implausible(40_960.0, _cells(numeric=300_000))
    assert reason is not None
    assert "0.1365" in reason and "300,000" in reason


def test_a_real_reading_on_the_same_cube_passes():
    # The same cube measured while resident: ~224 bytes/cell.
    assert bytes_per_cell_is_implausible(67_145_728.0, _cells(numeric=300_000)) is None


def test_an_empty_cube_is_not_accused():
    # No populated cells is a legitimate reason to cost almost nothing.
    assert bytes_per_cell_is_implausible(40_960.0, _cells(numeric=0)) is None


def test_no_cell_counts_means_no_verdict():
    # A server that does not report the counts gets silence, not a guess.
    assert bytes_per_cell_is_implausible(40_960.0, [_row("Sales", 40, "KB")]) is None
