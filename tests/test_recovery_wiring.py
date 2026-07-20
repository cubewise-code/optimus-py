"""M6 (executor layer) — a recovered order is never physically re-applied.

register_recovered records the Level-2 recovered in-flight order; every
evaluation path (the shared sweep primitives and the predefined loop) then
injects its stored result instead of re-sending the reorder, so it still
competes in the greedy pick and appears in the report but is measured only once.
"""
from optimuspy.execution_mode import ExecutionMode
from optimuspy.executors import PredefinedOrderExecutor
from optimuspy.results import ExecutionContext, PermutationResult
from tests.test_fold_a import make_main_executor


def _result(dims, context, ram_pct):
    return PermutationResult(
        context, ExecutionMode.ITERATIONS, "C", [], [], list(dims), {}, None,
        ram_usage=None, ram_percentage_change=ram_pct, reorder_duration=0.0)


def test_register_recovered_stores_and_disarms_reanchor():
    ex = make_main_executor(["A", "B"], {"A": 1, "B": 2})
    ex.context.set_initial_ram(100.0)
    ex.set_resume_context(["A", "B"], None, [])
    assert ex._reanchor_needed is True

    rec = _result(["B", "A"], ex.context, 0.0)
    ex.register_recovered(rec)

    assert ex._recovered_results[("B", "A")] is rec
    assert rec in ex._resumed_results
    # recovery already did the one absolute read; the executor must not re-anchor
    assert ex._reanchor_needed is False


def test_sweep_injects_recovered_without_reapplying(scripted):
    dims = ["A", "B", "C", "M"]
    card = {"A": 10, "B": 20, "C": 30, "M": 1}
    ex = make_main_executor(dims, card)
    log = []
    ram_of = lambda o: 100.0 - list(o).index("C")  # arbitrary, deterministic
    scripted(ex, ram_of, log)
    ex.context.set_initial_ram(ram_of(tuple(dims)))

    # candidate sweep at position 0 over dims B and C:
    #   dim B -> swap(0, idx B) -> ["B","A","C","M"]  (evaluated)
    #   dim C -> swap(0, idx C) -> ["C","B","A","M"]  (recovered -> injected)
    recovered_order = ["C", "B", "A", "M"]
    rec = _result(recovered_order, ex.context, -5.0)
    ex.register_recovered(rec)

    results = ex._sweep_into_position(list(dims), 0, ["B", "C"], None)

    orders = [list(r.dimension_order) for r in results]
    assert ["B", "A", "C", "M"] in orders          # normal candidate evaluated
    assert recovered_order in orders                # recovered candidate present
    assert rec in results                           # ... as the injected result
    assert recovered_order not in log               # ... but never re-applied
    assert ["B", "A", "C", "M"] in log


def test_predefined_injects_recovered_without_reapplying(scripted):
    orders = [["A", "B"], ["B", "A"]]
    ex = PredefinedOrderExecutor(
        tm1=None, cube_name="C", view_names=[], process_names=[],
        dimensions=["A", "B"], executions=1, measure_dimension_only_numeric=True,
        predefined_orders=orders, context=ExecutionContext())
    log = []
    ram_of = lambda o: 100.0
    scripted(ex, ram_of, log)
    ex.context.set_initial_ram(100.0)

    rec = _result(["B", "A"], ex.context, 0.0)
    ex.register_recovered(rec)

    results = ex.execute()

    result_orders = [list(r.dimension_order) for r in results]
    assert result_orders == [["A", "B"], ["B", "A"]]  # both present, order kept
    assert rec in results                              # recovered injected
    assert ["A", "B"] in log                           # first order evaluated
    assert ["B", "A"] not in log                       # recovered not re-applied


def test_measure_recovered_landed_reanchors_and_records_pct():
    ex = make_main_executor(["A", "B"], {"A": 1, "B": 2})
    ex.context.set_initial_ram(1000.0)
    ex.context.current_ram = 800.0  # stale

    result = ex.measure_recovered_landed(["B", "A"], abs_ram=900.0, pct=-10.0)

    assert result.ram_usage == 900.0
    assert ex.context.current_ram == 900.0      # re-anchored to the absolute read
    assert ex.context.original_ram == 1000.0    # baseline preserved
    assert result.ram_percentage_change == -10.0
