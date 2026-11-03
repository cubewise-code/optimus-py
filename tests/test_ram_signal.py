"""The post-run check that notices a run had no RAM signal at all.

OptimusPy measures RAM through exactly one channel: the percentage
``update_storage_dimension_order`` returns. When that channel reports 0.00% for
every candidate, the %-chain never moves and every row in the report carries the
same RAM figure — but a winner is still picked, by whatever broke the tie, and
the output reads exactly like a successful search. This is the detector that
makes the difference visible, over data the run already holds.

Observed on TM1 v12 against a cube whose ``cube_memory_used`` gauge was still
reporting the pre-load skeleton: fifteen permutations, one distinct RAM value.
"""
from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext, PermutationResult, ram_signal_is_dead


def _chain(percentages, anchor=1_000_000.0):
    """Build a run's results: the original order, then one per percentage."""
    context = ExecutionContext()
    results = [PermutationResult(
        context, ExecutionMode.ORIGINAL_ORDER, "C", [], [], ["A", "B"], {}, None,
        ram_usage=anchor)]
    for pct in percentages:
        results.append(PermutationResult(
            context, ExecutionMode.ITERATIONS, "C", [], [], ["B", "A"], {}, None,
            ram_usage=None, ram_percentage_change=pct, reorder_duration=0.0))
    return context, results


def test_every_order_reporting_zero_percent_is_a_dead_signal():
    _, results = _chain([0.0] * 14)

    assert len({r.ram_usage for r in results}) == 1
    assert ram_signal_is_dead(results) is True


def test_one_order_that_moved_the_chain_is_enough_to_call_it_alive():
    # The failure being detected is total: any real measurement anywhere in the
    # run means the channel was working and the ranking stands.
    _, results = _chain([0.0] * 13 + [-0.02])

    assert ram_signal_is_dead(results) is False


def test_a_normal_run_is_not_flagged():
    _, results = _chain([-5.0, 2.0, -11.25, 0.0])

    assert ram_signal_is_dead(results) is False


def test_the_original_order_alone_is_an_empty_signal_not_a_dead_one():
    # Nothing was compared, so there is nothing to warn about. The original
    # order's own percentage is 0 by construction (it is an absolute read), and
    # must not be mistaken for a candidate that measured flat.
    _, results = _chain([])

    assert len(results) == 1
    assert results[0].ram_percentage_change == 0
    assert ram_signal_is_dead(results) is False


def test_a_resume_reanchor_is_not_reported_as_a_dead_signal():
    # A resumed run takes one absolute read to re-anchor the stale chain. That
    # run can show 0% on every order and still carry two distinct RAM values —
    # a different situation, and not the one this check is for.
    context, results = _chain([0.0, 0.0])
    results.append(PermutationResult(
        context, ExecutionMode.ITERATIONS, "C", [], [], ["A", "B"], {}, None,
        ram_usage=930_000.0, ram_percentage_change=0.0, reorder_duration=0.0,
        reanchor=True))

    assert all(r.ram_percentage_change == 0 for r in results)
    assert len({r.ram_usage for r in results}) == 2
    assert ram_signal_is_dead(results) is False
