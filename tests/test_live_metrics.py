"""metrics.py against a real server — the half no offline test can reach.

What unit each version reports, and whether the v12 gauge has settled, are facts
about the server. They are also the facts everything else rests on: every RAM
comparison OptimusPy makes is a ratio of two of these reads, and a silent 1024x
would still produce a plausible-looking report.

    pytest -m live --instance tm1srv01     # v11, expects Unit "B"
    pytest -m live --instance tm1srv02     # v12, expects Unit "KB"

The pure row-reading functions are covered offline in test_metrics.py.
"""
import pytest

from optimuspy.metrics import (
    CUBE_MEMORY_METRIC, _UNIT_TO_BYTES, cube_memory_used_bytes,
    memory_by_cube_bytes, ram_source_ready, read_cube_memory_bytes, unit_to_bytes)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def ram_readable(tm1, is_v12):
    """Hold the RAM source open, as a run does, for the whole module."""
    with ram_source_ready(tm1, is_v12):
        yield


@pytest.fixture(scope="module")
def a_cube(tm1, ram_readable):
    """Any real cube on the instance that reports a memory figure.

    Deliberately not a fixture cube: this asks what the server says about a cube
    it already has, so it holds on whatever the instance happens to be.
    """
    for name in tm1.cubes.get_all_names():
        if name.startswith("}"):
            continue
        if cube_memory_used_bytes(tm1.metrics.by_cube(cube=name)) is not None:
            return name
    pytest.skip("no cube on this instance reports cube_memory_used")


def test_detect_is_v12_agrees_with_the_server_version(tm1, is_v12):
    major = int(str(tm1.server.get_product_version()).split(".")[0])
    assert is_v12 == (major >= 12)


def test_the_reported_unit_is_one_the_conversion_table_knows(tm1, a_cube):
    # The failure this guards is a server upgrade that changes the unit. It is
    # caught here as a named unit rather than downstream as a cube that appears
    # to have grown a thousandfold.
    rows = [r for r in tm1.metrics.by_cube(cube=a_cube)
            if r.get("Metric") == CUBE_MEMORY_METRIC]
    assert rows, f"{CUBE_MEMORY_METRIC} not reported for '{a_cube}'"
    assert rows[0].get("Unit") in _UNIT_TO_BYTES, rows[0]


def test_v11_reports_bytes_and_v12_reports_kilobytes(tm1, a_cube, is_v12):
    # The documented difference, asserted rather than assumed. If this ever
    # flips, unit_to_bytes still converts correctly — but the module docstring
    # and everything written about it would be wrong.
    row = next(r for r in tm1.metrics.by_cube(cube=a_cube)
               if r.get("Metric") == CUBE_MEMORY_METRIC)
    assert row["Unit"] == ("KB" if is_v12 else "B")


def test_the_read_returns_the_row_converted_to_bytes(tm1, a_cube, is_v12):
    row = next(r for r in tm1.metrics.by_cube(cube=a_cube)
               if r.get("Metric") == CUBE_MEMORY_METRIC)
    expected = unit_to_bytes(row["Value"], row["Unit"])

    ram = read_cube_memory_bytes(tm1, a_cube, is_v12)

    assert ram > 0
    # v12 stabilises by polling for a plateau, so it may land on a later, larger
    # sample than the one read a moment ago; it never reports a smaller one.
    assert ram >= expected * 0.99


def test_a_settled_cube_reads_the_same_size_twice(tm1, a_cube, is_v12):
    # The v12 plateau loop exists because a cube still materialising reads small
    # and rising. On a cube nobody is loading, the second read must confirm the
    # first — otherwise every %-chain in a run is anchored to a moving number.
    first = read_cube_memory_bytes(tm1, a_cube, is_v12)
    second = read_cube_memory_bytes(tm1, a_cube, is_v12)
    assert second == pytest.approx(first, rel=0.01), (first, second)


def test_the_unfiltered_pivot_covers_the_instances_own_cubes(tm1, ram_readable, a_cube):
    by_cube = memory_by_cube_bytes(tm1.metrics.by_cube())

    assert a_cube in by_cube
    assert all(v > 0 for v in by_cube.values())
    # by_cube() already drops }-control cubes and the synthetic total row on both
    # versions, which is why the module does no filtering of its own.
    assert not [c for c in by_cube if c.startswith("}")]
    assert "Cubes Total" not in by_cube


def test_ram_source_ready_leaves_the_performance_monitor_as_it_found_it(tm1, is_v12):
    if is_v12:
        # The v11 lifecycle methods raise on v12; the context manager must be a
        # no-op there rather than reaching for them.
        with ram_source_ready(tm1, is_v12):
            pass
        return

    before = tm1.metrics.get_performance_monitor_state()
    with ram_source_ready(tm1, is_v12):
        assert tm1.metrics.get_performance_monitor_state()
    assert tm1.metrics.get_performance_monitor_state() == before
