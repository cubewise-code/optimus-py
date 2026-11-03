"""M5 — best-effort restore of a cube's storage dimension order.

On a crash or cancel the cube is left at the last-applied permutation. This
helper restores the true original order but must never raise: a dropped
connection (the common interruption cause) makes it a silent no-op, and resume
recovers regardless.
"""
from optimuspy.core import safe_restore_dimension_order


class _Cubes:
    def __init__(self, raises=False):
        self.raises = raises
        self.calls = []

    def update_storage_dimension_order(self, cube_name, order):
        self.calls.append((cube_name, list(order)))
        if self.raises:
            raise RuntimeError("connection dropped")


class _TM1:
    def __init__(self, raises=False):
        self.cubes = _Cubes(raises)


def test_restores_order_when_connection_alive():
    tm1 = _TM1()
    safe_restore_dimension_order(tm1, "C", ["A", "B", "C"])
    assert tm1.cubes.calls == [("C", ["A", "B", "C"])]


def test_suppresses_exception_on_dead_connection():
    tm1 = _TM1(raises=True)
    # must not raise
    safe_restore_dimension_order(tm1, "C", ["A", "B", "C"])
    assert tm1.cubes.calls == [("C", ["A", "B", "C"])]


def test_noop_when_order_missing():
    tm1 = _TM1()
    safe_restore_dimension_order(tm1, "C", None)
    assert tm1.cubes.calls == []
