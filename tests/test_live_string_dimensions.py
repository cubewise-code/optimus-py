"""A cube with string dimensions away from the last slot optimizes cleanly (#141).

The Revenue cube in #141 had a numeric last dimension and two dimensions with
string elements in the middle. The greedy swept the free last slot, tried one of
the string dimensions there, and TM1 refused the reorder ("Last dimension has
strings and cannot be repositioned"), which ended the run. Both v11 and v12
refuse it, so this runs against each:

    pytest -m live tests/test_live_string_dimensions.py --instance tm1srv01   # v11
    pytest -m live tests/test_live_string_dimensions.py --instance tm1srv02   # v12

The fixture cube is small and built fresh, then removed.
"""
import logging

import pytest
from TM1py import Cube, Dimension, Element, Hierarchy

from optimuspy import core

pytestmark = pytest.mark.live

CUBE = "OptimusPy_StringDims_Test"
# Storage order mirrors #141: string dimensions mid-order, a numeric one last.
DIMENSIONS = {
    f"{CUBE}_Org": (10, 0),
    f"{CUBE}_Month": (15, 2),     # 15 numeric elements + 2 string elements
    f"{CUBE}_Year": (5, 0),
    f"{CUBE}_Version": (20, 1),
    f"{CUBE}_Value": (6, 0),
}
STRING_DIMS = [f"{CUBE}_Month", f"{CUBE}_Version"]


def _build(tm1):
    for name, (numeric, strings) in DIMENSIONS.items():
        elements = [Element(f"N{i}", "Numeric") for i in range(numeric)]
        elements += [Element(f"S{i}", "String") for i in range(strings)]
        tm1.dimensions.update_or_create(Dimension(name, [Hierarchy(name, name, elements=elements)]))
    tm1.cubes.update_or_create(Cube(CUBE, list(DIMENSIONS)))
    # A skewed numeric fill, so orders differ in RAM and a winner emerges.
    cells = {}
    for i in range(3000):
        cells[(f"N{i % 10}", f"N{(i * 7) % 15}", f"N{(i // 3) % 5}",
               f"N{(i * 13) % 20}", f"N{i % 6}")] = i % 97 + 1
    tm1.cells.write_values(CUBE, cells)


def _teardown(tm1):
    if tm1.cubes.exists(CUBE):
        tm1.cubes.delete(CUBE)
    for name in DIMENSIONS:
        if tm1.dimensions.exists(name):
            tm1.dimensions.delete(name)


@pytest.fixture
def string_cube(tm1):
    _teardown(tm1)
    try:
        _build(tm1)
        yield list(tm1.cubes.get_storage_dimension_order(cube_name=CUBE))
    finally:
        _teardown(tm1)


class _Reorders:
    """Every order the run sends to the cube, in order."""

    def __init__(self, monkeypatch):
        from TM1py.Services.CubeService import CubeService
        original = CubeService.update_storage_dimension_order
        self.sent = []

        def recording(cube_self, cube_name, dimension_names, *args, **kwargs):
            self.sent.append(list(dimension_names))
            return original(cube_self, cube_name, dimension_names, *args, **kwargs)

        monkeypatch.setattr(CubeService, "update_storage_dimension_order", recording)


def test_string_dimensions_never_go_last_and_the_run_completes(
        string_cube, live_instance, tm1_config_path, tm1, monkeypatch, caplog):
    assert string_cube[-1] == f"{CUBE}_Value"   # the last slot is free
    reorders = _Reorders(monkeypatch)
    config = {"instance": live_instance, "cube": CUBE, "views": [], "executions": 1,
              "output": "csv"}

    with caplog.at_level(logging.INFO):
        ok = core.main("optimize", config, tm1_config_path, no_resume=True)

    assert ok, "the optimization did not complete:\n" + "\n".join(
        m for m in caplog.messages if "error" in m.lower())[-2000:]
    tried_last = {order[-1] for order in reorders.sent}
    assert not tried_last & set(STRING_DIMS), f"a string dimension was sent last: {tried_last}"
    # the free last slot was still swept, with every dimension allowed there
    assert tried_last >= {f"{CUBE}_Org", f"{CUBE}_Year", f"{CUBE}_Value"}
    assert any("Never tried in the last slot" in m for m in caplog.messages)
    numbered = [m.split(" - ")[0].split() for m in caplog.messages
                if m.startswith("Iteration ") and " of " in m.split(" - ")[0]]
    last, total = int(numbered[-1][1]), int(numbered[-1][3])
    assert last == total, f"ended on Iteration {last} of {total}"
    # the cube is back in the order it started in
    assert list(tm1.cubes.get_storage_dimension_order(cube_name=CUBE)) == string_cube
