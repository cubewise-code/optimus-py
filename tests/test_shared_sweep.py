"""The sweep primitives and the specialist executors, driven offline.

No fake TM1: `offline_executor` builds the production classes with `tm1=None`
and `install_offline_measurements` supplies what the server would have reported.
Everything between those two points — the %-chain, the run artifact, the
progress label, the frame's refusals — is the code under test.
"""
from optimuspy.execution_mode import ExecutionMode
from optimuspy.order_frame import REASON_LOCKED_SLOT
from optimuspy.executors import (
    DimensionOptimizerExecutor, OptipyzerExecutor, PositionOptimizerExecutor)
from tests.conftest import offline_executor


def _bare_executor(view_names=None, process_names=None):
    # The base class is abstract about mode — every subclass sets its own — so
    # the sweep primitives are exercised under the mode the folds run in.
    ex = offline_executor(OptipyzerExecutor, ["A", "B", "C", "M"],
                          view_names=view_names, process_names=process_names)
    ex.mode = ExecutionMode.ITERATIONS
    return ex


def test_the_percent_chain_derives_ram_from_the_servers_percentage(measure_orders):
    # The server reports a percentage per reorder; only the first reading is
    # absolute. Turning that chain back into RAM figures is production's job
    # (PermutationResult -> ExecutionContext.update_ram), and this is the test
    # that it survives a reorder sequence.
    ex = _bare_executor()
    ram = {("A", "B"): 100.0, ("B", "A"): 80.0}
    log = []
    measure_orders(ex, lambda o: ram[o], log)

    first = ex._evaluate_permutation(["A", "B"], retrieve_ram=True, is_original_order=True)
    second = ex._evaluate_permutation(["B", "A"])

    assert first.ram_usage == 100.0                     # absolute read
    assert round(second.ram_percentage_change, 6) == -20.0
    assert round(second.ram_usage, 6) == 80.0           # derived via the % chain
    assert log == [["A", "B"], ["B", "A"]]


def test_sweep_into_position_evaluates_each_candidate_by_swapping(measure_orders):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    ram = {tuple(order): 100.0}
    # swapping D into last non-measure position 2:
    ram[("A", "C", "B", "M")] = 90.0   # B->C swap
    ram[("A", "B", "C", "M")] = 100.0
    log = []
    measure_orders(ex, lambda o: ram.get(o, 100.0), log)
    ex.context.set_initial_ram(100.0)

    results = ex._sweep_into_position(order, target_position=1, candidate_dims=["B", "C"],
                                      total_permutations=2)
    assert [r.dimension_order for r in results] == [["A", "B", "C", "M"], ["A", "C", "B", "M"]]


def test_sweep_into_position_honours_skip_candidate(measure_orders):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    ex._sweep_into_position(order, 3, ["A", "B", "C"], total_permutations=3,
                            skip_candidate=lambda dim, pos: dim == "B")
    # B is skipped: it must never be the candidate swapped into target_position (index 3).
    assert not any(o[3] == "B" for o in log)
    # A and C are NOT skipped: they must genuinely have been swept into position 3.
    assert {o[3] for o in log} == {"A", "C"}


def test_sweep_across_positions_evaluates_each_position_by_swapping(measure_orders):
    ex = _bare_executor()
    order = ["A", "B", "C"]
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)

    results = ex._sweep_across_positions(order, target_dim="A", candidate_positions=[1, 2],
                                         total_permutations=2)
    assert [r.dimension_order.index("A") for r in results] == [1, 2]


def test_sweep_into_position_honours_skip_permutation(measure_orders):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)

    # Swapping C into position 1 yields this exact permutation; block it via skip_permutation.
    blocked = ["A", "C", "B", "M"]
    results = ex._sweep_into_position(order, target_position=1, candidate_dims=["B", "C"],
                                      total_permutations=2,
                                      skip_permutation=lambda perm: perm == blocked)

    assert blocked not in log
    assert all(r.dimension_order != blocked for r in results)
    # The non-blocked candidate (B, a no-op swap here) was still evaluated.
    assert ["A", "B", "C", "M"] in log


def test_sweep_into_position_checkpoint_cb_sees_last_applied_order(measure_orders):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)

    calls = []

    def checkpoint_cb(dim, results):
        calls.append((dim, list(results)))

    ex._sweep_into_position(order, target_position=1, candidate_dims=["B", "C"],
                            total_permutations=2, checkpoint_cb=checkpoint_cb)

    # checkpoint_cb fires once per evaluated candidate, in order.
    assert [dim for dim, _ in calls] == ["B", "C"]
    assert len(calls) == len(log) == 2
    # At each call, the last-applied order handed to the callback is exactly the
    # permutation that was just evaluated (the cube "sits at" that order).
    for i, (_, results) in enumerate(calls):
        assert results[-1].dimension_order == log[i]


def test_pick_best_ram(measure_orders):
    ex = _bare_executor()
    log = []
    ram = {("A", "B"): 100.0, ("B", "A"): 70.0}
    measure_orders(ex, lambda o: ram[o], log)
    ex.context.set_initial_ram(100.0)
    r1 = ex._evaluate_permutation(["A", "B"], is_original_order=True)
    r2 = ex._evaluate_permutation(["B", "A"])
    assert ex._pick_best([r1, r2], "ram").dimension_order == ["B", "A"]


def _make_position_optimizer(target_position, dims, exclude=None, last_slot_locked=False):
    return offline_executor(PositionOptimizerExecutor, dims,
                            last_slot_locked=last_slot_locked,
                            target_position=target_position,
                            dimensions_to_exclude=exclude or [])


def test_position_optimizer_sweeps_all_other_dims(measure_orders):
    ex = _make_position_optimizer(0, ["A", "B", "C"])
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)  # strictly decreasing, deterministic
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    # position 0 currently holds A; candidates are B and C swapped into slot 0
    assert [r.dimension_order[0] for r in results] == ["B", "C"]


def test_position_optimizer_resume_skips_completed_dims(measure_orders):
    # "A" is already completed from a prior checkpoint and must not be re-swept.
    # The executor holds no TM1 handle, so this also pins the fact that the sweep
    # asks the server nothing at all: the lock was decided once, by the frame.
    ex = _make_position_optimizer(3, ["A", "B", "C", "D"])  # last position (index 3)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    resume_state = {"executor_state": {"position_state": {"completed_dimensions": ["A"]}}}
    results = ex.execute(resume_state)

    # "A" was already completed: it must never appear as a swept-in candidate.
    assert "A" not in [r.dimension_order[3] for r in results]
    assert "A" not in [o[3] for o in log]
    # The non-completed candidates (B, C) were genuinely swept.
    assert {r.dimension_order[3] for r in results} == {"B", "C"}


def test_position_optimizer_evaluates_nothing_when_targeting_the_locked_slot(measure_orders):
    # The last slot is locked, so nothing may be swept into it: every candidate
    # would move the locked dimension. The old code asked the server per candidate
    # whether IT had strings and let a numeric one through — which TM1 would then
    # have rejected, because the locked dim would have been displaced.
    ex = _make_position_optimizer(3, ["A", "B", "C", "D"], last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    results = ex.execute()

    assert results == []
    assert log == []
    assert ex.skipped_orders == {REASON_LOCKED_SLOT: 3}
    # "D" is still last, because nothing was ever evaluated.
    assert ex.dimensions[3] == "D"


def test_position_optimizer_works_normally_at_a_free_slot_on_a_locked_cube(measure_orders):
    # The lock closes one slot, not the search. Targeting any other position on
    # the same cube sweeps every candidate but the locked dimension.
    ex = _make_position_optimizer(0, ["A", "B", "C", "D"], last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    results = ex.execute()

    assert [r.dimension_order[0] for r in results] == ["B", "C"]
    assert all(o[-1] == "D" for o in log)
    assert ex.skipped_orders == {REASON_LOCKED_SLOT: 1}  # the D-into-slot-0 candidate


def _make_dimension_optimizer(target_dimension, dims, last_slot_locked=False):
    return offline_executor(DimensionOptimizerExecutor, dims,
                            last_slot_locked=last_slot_locked,
                            target_dimension=target_dimension)


def test_dimension_optimizer_sweeps_all_positions_except_current(measure_orders):
    ex = _make_dimension_optimizer("A", ["A", "B", "C"])  # A at idx 0
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    # A moved into positions 1 and 2
    assert [r.dimension_order.index("A") for r in results] == [1, 2]


def test_dimension_optimizer_never_targets_the_locked_slot(measure_orders):
    # "C" is locked last, so it is not a candidate position for anything —
    # whatever the moving dimension happens to contain.
    ex = _make_dimension_optimizer("A", ["A", "B", "C"], last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    assert [r.dimension_order.index("A") for r in results] == [1]
    assert all(o[-1] == "C" for o in log)


def test_dimension_optimizer_evaluates_nothing_for_the_locked_dimension(measure_orders):
    # Asking to optimize the locked dimension's position has one honest answer:
    # it has none. Every move of it is refused and nothing is evaluated.
    ex = _make_dimension_optimizer("C", ["A", "B", "C"], last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    assert results == []
    assert log == []


def test_dimension_optimizer_resume_skips_completed_position(measure_orders):
    # Position 1 is already completed from a prior checkpoint. On resume, the
    # target dim must never be re-swapped into that position — only the
    # remaining candidate position(s) get swept.
    ex = _make_dimension_optimizer("A", ["A", "B", "C"])  # A at idx 0
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    resume_state = {"executor_state": {"dimension_state": {"completed_positions": [1]}}}
    results = ex.execute(resume_state)

    # Position 1 was already completed: "A" must never land there again.
    assert 1 not in [r.dimension_order.index("A") for r in results]
    assert all(o[1] != "A" for o in log)
    # Position 2 (the only remaining candidate) was genuinely swept.
    assert [r.dimension_order.index("A") for r in results] == [2]


def test_progress_label_one_indexed_and_optional_total():
    # Label bug fix: 1-indexed (not "Iteration 0"), and no "of N" when the total
    # is unknown (folds), which avoids the misleading "of 14" upper bound.
    ex = _bare_executor()
    ex.context.counter = 2  # state right after the original-order eval
    assert ex._progress_label(True, None) == "Original Order"
    assert ex._progress_label(False, None) == "Iteration 1"
    assert ex._progress_label(False, 14) == "Iteration 1 of 14"
    ex.context.counter = 5
    assert ex._progress_label(False, None) == "Iteration 4"
