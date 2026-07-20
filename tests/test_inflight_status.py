"""M4 — in-flight status: `submitted` before the reorder, `received` after.

_evaluate_permutation writes a checkpoint marking the order `pending`
(submitted) BEFORE sending the reorder to TM1; the normal post-evaluation
checkpoint clears `pending` and records the finished result (received). So
completed_results only ever holds fully-measured orders, and a crash between the
reorder and the received write leaves exactly the one in-flight order in
`pending`.
"""
import types

import pytest

from optimuspy.execution_mode import ExecutionMode
from optimuspy.executors import PredefinedOrderExecutor
from optimuspy.results import ExecutionContext, PermutationResult


class RecordingAllSaves:
    """checkpoint_manager fake that records every save() call's kwargs."""

    def __init__(self):
        self.saves = []

    def save(self, **kwargs):
        self.saves.append(kwargs)


class _FakeCubes:
    def __init__(self, raise_on_reorder=False):
        self.raise_on_reorder = raise_on_reorder

    def update_storage_dimension_order(self, cube_name, order):
        if self.raise_on_reorder:
            raise RuntimeError("connection dropped")
        return 0.0


class _FakeTM1:
    def __init__(self, raise_on_reorder=False):
        self.cubes = _FakeCubes(raise_on_reorder)


def _original(dims):
    return PermutationResult(
        ExecutionContext(), ExecutionMode.ORIGINAL_ORDER, "C", [], [],
        list(dims), {}, None, ram_usage=1000.0, ram_percentage_change=None,
        reorder_duration=0.0)


def _make_executor(orders, cm, *, raise_on_reorder=False):
    ex = PredefinedOrderExecutor(
        tm1=_FakeTM1(raise_on_reorder), cube_name="C", view_names=[], process_names=[],
        dimensions=["A", "B"], executions=1, measure_dimension_only_numeric=True,
        predefined_orders=orders, context=ExecutionContext(), checkpoint_manager=cm)
    ex._retrieve_ram_usage = types.MethodType(lambda self: 1000.0, ex)
    ex.context.set_initial_ram(1000.0)  # baseline as restored from a checkpoint
    ex.set_resume_context(["A", "B"], _original(["A", "B"]), [])
    return ex


def test_submitted_then_received_sequence():
    cm = RecordingAllSaves()
    ex = _make_executor([["B", "A"]], cm)
    ex.execute()

    # first save marks the order submitted (pending set) with no completed work yet
    submitted = cm.saves[0]
    assert submitted["pending"] == {"dimension_order": ["B", "A"]}
    assert submitted["completed_results"] == []

    # last save is the received promotion: pending cleared, order now completed
    received = cm.saves[-1]
    assert received["pending"] is None
    assert [list(r.dimension_order) for r in received["completed_results"]] == [["B", "A"]]


def test_crash_before_received_leaves_pending():
    cm = RecordingAllSaves()
    ex = _make_executor([["B", "A"]], cm, raise_on_reorder=True)
    with pytest.raises(RuntimeError):
        ex.execute()

    # only the submitted write landed; the in-flight order survives in pending
    assert len(cm.saves) == 1
    assert cm.saves[-1]["pending"] == {"dimension_order": ["B", "A"]}
