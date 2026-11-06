"""Which order Best Overall recommends.

With views or processes there is a trade-off, so the first order within
tolerance on every metric wins (docs/concepts/ram-vs-query-tradeoff.md). In a
RAM-only run there is nothing to trade against: the recommendation is the
lowest-RAM order, unless the original is within tolerance, in which case
reordering the cube is not worth it and the original stays.
"""
from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext, OptimusResult, PermutationResult


def _report(rams, query_times=None):
    context = ExecutionContext()
    context.set_initial_ram(rams[0])
    views = ["V"] if query_times else []
    results = []
    for i, ram in enumerate(rams):
        mode = ExecutionMode.ORIGINAL_ORDER if i == 0 else ExecutionMode.ITERATIONS
        results.append(PermutationResult(
            context, mode, "C", views, [], ["A", "B"] if i == 0 else ["B", "A"],
            {"V": [query_times[i]]} if query_times else {}, None,
            ram_usage=ram, ram_percentage_change=None, reorder_duration=0.0))
    return OptimusResult("C", results)


def test_ram_only_recommends_the_lowest_ram_order():
    # The reported run: #81 at 4120 MB came first and sat within 1% of the
    # range, but #95 at 4112 MB is lower and nothing else is being weighed.
    report = _report([6131.0, 5000.0, 4120.0, 4500.0, 4112.0, 4300.0])
    assert report.best_result.ram_usage == 4112.0
    assert report.best_result.iteration_number == 4


def test_ram_only_keeps_the_original_when_it_is_within_tolerance():
    # 1% of the 100 MB range is 1 MB: the original is 0.5 MB above the best,
    # so a reorder would buy nothing measurable.
    report = _report([1000.5, 1100.0, 1000.0])
    assert report.best_result.mode == ExecutionMode.ORIGINAL_ORDER


def test_with_views_the_first_order_within_tolerance_still_wins():
    # Both iterations are within tolerance on RAM and query time; the earlier
    # one wins, as documented for runs that trade RAM against query time.
    report = _report([2000.0, 1000.5, 1000.0], query_times=[2.0, 1.0, 1.0])
    assert report.best_result.iteration_number == 1
