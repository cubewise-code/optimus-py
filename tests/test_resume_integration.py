"""M6 — cross-mode resume integration through a connection drop.

Drives real executors + a real CheckpointManager (local file) + real
_evaluate_permutation against a FakeTM1 that models per-order RAM and can drop
the connection mid-reorder. Mirrors core's resume orchestration (validate by
set, source the original from the checkpoint, run ResumeRecovery for the
in-flight order) and proves the shared-layer fix covers greedy Fold A and a
targeted mode (predefined), plus the landed recovery branch and original-order
preservation.
"""
import pytest

from optimuspy.checkpoint import CheckpointManager
from optimuspy.core import _recover_pending_order
from optimuspy.execution_mode import ExecutionMode
from optimuspy.executors import MainExecutor, OriginalOrderExecutor, PredefinedOrderExecutor
from optimuspy.results import ExecutionContext, OptimusResult


# --------------------------------------------------------------------------- #
# FakeTM1 — models cube RAM as a function of the current storage order and can
# simulate a dropped connection on the Nth reorder.
# --------------------------------------------------------------------------- #
class _FakeCubes:
    def __init__(self, tm1):
        self.tm1 = tm1

    def update_storage_dimension_order(self, cube_name, order):
        return self.tm1._apply(order)

    def get_storage_dimension_order(self, cube_name=None):
        return list(self.tm1._order)

    def get_dimension_names(self, cube_name=None):
        return list(self.tm1._displayed)


class _FakeMetrics:
    def __init__(self, tm1):
        self.tm1 = tm1

    def by_cube(self, cube=None):
        return [{"Metric": "cube_memory_used", "Value": self.tm1.current_ram,
                 "Unit": "B", "CubeName": cube or "C"}]


class FakeTM1:
    def __init__(self, ram_of, initial_order, displayed=None, fail_after=None):
        self.ram_of = ram_of
        self._order = list(initial_order)
        self._displayed = list(displayed or initial_order)
        self.fail_after = fail_after
        self.reorder_calls = 0
        self.applied = []          # every order actually applied (landed)
        self.cubes = _FakeCubes(self)
        self.metrics = _FakeMetrics(self)

    @property
    def current_ram(self):
        return float(self.ram_of(tuple(self._order)))

    def _apply(self, order):
        self.reorder_calls += 1
        if self.fail_after is not None and self.reorder_calls > self.fail_after:
            raise RuntimeError("connection dropped")  # reorder never lands
        prev = self.current_ram
        self._order = list(order)
        self.applied.append(list(order))
        return (self.current_ram / prev - 1.0) * 100.0


# --------------------------------------------------------------------------- #
# Harness mirroring core's original-order + iterate + resume flow.
# --------------------------------------------------------------------------- #
def _run_original(tm1, mgr, initial, displayed, context, measure_numeric):
    orig_ex = OriginalOrderExecutor(
        tm1, "C", [], [], displayed, 1, measure_numeric, initial, context,
        checkpoint_manager=mgr)
    original = orig_ex.execute()[0]
    mgr.save(executor_type="OriginalOrderExecutor", execution_context=context,
             initial_dimension_order=initial, last_applied_order=initial,
             original_order_result=original, completed_results=[])
    return original


def _resume(factory, tm1, mgr, current_dims):
    assert mgr.validate(current_dims) is True
    data = mgr.load()
    initial = data["initial_dimension_order"]
    context = ExecutionContext()
    CheckpointManager.restore_execution_context(context, data)
    original = CheckpointManager.deserialize_result(data["original_order_result"])
    resumed = [CheckpointManager.deserialize_result(r) for r in data["completed_results"]]
    ex = factory(context)
    ex.set_resume_context(initial, original, resumed, resuming=True)
    pending = data.get("pending")
    if pending:
        _recover_pending_order(tm1, "C", ex, pending, original, resumed, is_v12=False)
    new = ex.execute(resume_state=data)
    return {"initial": initial, "original": original, "resumed": resumed, "new": new,
            "pending": pending}


def _best_order(original, *result_lists):
    merged = [original]
    for rl in result_lists:
        merged.extend(rl)
    # dedup by permutation_id, mirroring core._deduplicate_results
    seen, unique = set(), []
    for r in merged:
        if r.permutation_id not in seen:
            seen.add(r.permutation_id)
            unique.append(r)
    return list(OptimusResult("C", unique).best_result.dimension_order)


# --------------------------------------------------------------------------- #
# Predefined mode — not-landed drop mid-run, then resume + recover.
# --------------------------------------------------------------------------- #
def test_predefined_resume_after_drop_completes_and_recovers(tmp_path):
    dims = ["A", "B", "C", "M"]
    orders = [["A", "C", "B", "M"], ["C", "A", "B", "M"], ["B", "A", "C", "M"]]
    # RAM uniquely minimised by orders[1] -> unambiguous best.
    target = ["C", "A", "B", "M"]
    ram_of = lambda o: 100.0 - sum(1 for i, d in enumerate(target) if list(o)[i] == d)

    def factory(context, tm1, mgr):
        return PredefinedOrderExecutor(
            tm1, "C", [], [], dims, 1, True, orders, context, checkpoint_manager=mgr)

    # 1) uninterrupted reference
    ctx = ExecutionContext()
    mgr = CheckpointManager("C", "inst", "fp", tmp_path / "ref")
    tm1 = FakeTM1(ram_of, dims)
    original = _run_original(tm1, mgr, dims, dims, ctx, True)
    ex = factory(ctx, tm1, mgr)
    ex.set_resume_context(dims, original, [], resuming=False)
    ref_results = ex.execute()
    ref_best = _best_order(original, ref_results)
    assert ref_best == target

    # 2) fresh run that drops on the 2nd predefined reorder (orders[1] never lands)
    #    reorders: #1 original, #2 orders[0], #3 orders[1] -> fail_after=2
    mgr2 = CheckpointManager("C", "inst", "fp", tmp_path / "run")
    tm1b = FakeTM1(ram_of, dims, fail_after=2)
    ctx2 = ExecutionContext()
    original2 = _run_original(tm1b, mgr2, dims, dims, ctx2, True)
    ex2 = factory(ctx2, tm1b, mgr2)
    ex2.set_resume_context(dims, original2, [], resuming=False)
    with pytest.raises(RuntimeError):
        ex2.execute()

    # checkpoint recorded the in-flight order as pending; the cube never moved to it
    data = mgr2.load()
    assert data["pending"] == {"dimension_order": orders[1]}
    assert list(tm1b._order) == orders[0]  # last landed order

    # 3) resume on a fresh connection (cube left at orders[0] — reordered, same set)
    tm1c = FakeTM1(ram_of, orders[0], fail_after=None)
    out = _resume(lambda c: factory(c, tm1c, mgr2), tm1c, mgr2, list(tm1c._order))

    # original preserved from the checkpoint, not the reordered live cube
    assert out["initial"] == dims
    # every predefined order ends up measured, best is unchanged from the reference
    resumed_best = _best_order(out["original"], out["resumed"], out["new"])
    assert resumed_best == target
    # the recovered in-flight order was applied exactly once on resume (not twice)
    assert tm1c.applied.count(orders[1]) == 1
    # the already-completed order is NOT re-applied on resume
    assert orders[0] not in tm1c.applied


# --------------------------------------------------------------------------- #
# Greedy Fold A — drop mid-fold, then resume; best is unchanged.
# --------------------------------------------------------------------------- #
def _fold_a_factory(dims, card, string_dims):
    def factory(context, tm1, mgr):
        return MainExecutor(
            tm1, "C", [], [], dims, 1, False, context, fast=False,
            checkpoint_manager=mgr, cardinality=card, string_dims=string_dims)
    return factory


def test_fold_a_resume_after_drop_matches_uninterrupted_best(tmp_path):
    dims = ["A", "B", "C", "D", "E", "M"]
    card = {"A": 100, "B": 105, "C": 110, "D": 115, "E": 120, "M": 3}
    strings = ["M"]  # only a string dim is locked last
    ram_of = (lambda o: 100.0 - 10 * list(o).index("E")
              + list(o).index("M") + 0.5 * list(o).index("A"))
    factory = _fold_a_factory(dims, card, strings)

    # 1) uninterrupted reference
    ctx = ExecutionContext()
    mgr = CheckpointManager("C", "inst", "fp", tmp_path / "ref")
    tm1 = FakeTM1(ram_of, dims)
    original = _run_original(tm1, mgr, dims, dims, ctx, False)
    ex = factory(ctx, tm1, mgr)
    ex.set_resume_context(dims, original, [], resuming=False)
    ref_results = ex.execute()
    ref_best = _best_order(original, ref_results)

    # 2) fresh run that drops partway through the fold
    mgr2 = CheckpointManager("C", "inst", "fp", tmp_path / "run")
    tm1b = FakeTM1(ram_of, dims, fail_after=5)  # a handful of reorders in, then drop
    ctx2 = ExecutionContext()
    original2 = _run_original(tm1b, mgr2, dims, dims, ctx2, False)
    ex2 = factory(ctx2, tm1b, mgr2)
    ex2.set_resume_context(dims, original2, [], resuming=False)
    with pytest.raises(RuntimeError):
        ex2.execute()
    dropped_order = list(tm1b._order)  # cube left reordered by the fold

    # 3) resume on a fresh connection; validate accepts the reordered cube (same set)
    tm1c = FakeTM1(ram_of, dropped_order, fail_after=None)
    out = _resume(lambda c: factory(c, tm1c, mgr2), tm1c, mgr2, list(tm1c._order))

    assert out["initial"] == dims  # original preserved
    resumed_best = _best_order(out["original"], out["resumed"], out["new"])
    assert resumed_best == ref_best
    # a recovered pending order is never physically applied twice on resume
    if out["pending"]:
        po = out["pending"]["dimension_order"]
        assert tm1c.applied.count(po) <= 1


# --------------------------------------------------------------------------- #
# Landed recovery branch — cube already at the pending order on resume.
# --------------------------------------------------------------------------- #
def test_landed_recovery_does_not_reapply_and_backcalcs(tmp_path):
    dims = ["A", "B", "C", "M"]
    orders = [["A", "C", "B", "M"], ["C", "A", "B", "M"]]
    ram_of = lambda o: {("A", "B", "C", "M"): 100.0,
                        ("A", "C", "B", "M"): 90.0,
                        ("C", "A", "B", "M"): 80.0}.get(tuple(o), 100.0)

    def factory(context, tm1, mgr):
        return PredefinedOrderExecutor(
            tm1, "C", [], [], dims, 1, True, orders, context, checkpoint_manager=mgr)

    # Build a checkpoint: original + orders[0] completed, orders[1] pending.
    mgr = CheckpointManager("C", "inst", "fp", tmp_path / "run")
    tm1 = FakeTM1(ram_of, dims)
    ctx = ExecutionContext()
    original = _run_original(tm1, mgr, dims, dims, ctx, True)
    ex = factory(ctx, tm1, mgr)
    ex.set_resume_context(dims, original, [], resuming=False)
    # drive only orders[0] (received), then hand-write orders[1] as pending
    tm1.fail_after = 2  # #1 original, #2 orders[0] land; #3 would fail
    with pytest.raises(RuntimeError):
        ex.execute()
    data = mgr.load()
    assert data["pending"] == {"dimension_order": orders[1]}

    # Simulate that orders[1] DID land before the drop: put the cube there.
    tm1c = FakeTM1(ram_of, orders[1], fail_after=None)
    out = _resume(lambda c: factory(c, tm1c, mgr), tm1c, mgr, list(tm1c._order))

    # landed: the reorder is NOT repeated for the pending order
    assert orders[1] not in tm1c.applied
    # the recovered order carries the fresh absolute RAM (80.0) as its usage
    recovered = next(r for r in out["resumed"] if list(r.dimension_order) == orders[1])
    assert recovered.ram_usage == 80.0
