from optimuspy.results import ExecutionContext


def test_scripted_evaluator_reproduces_ram_through_the_percent_chain(scripted):
    # Build a bare object with just the attributes the scripted evaluator touches.
    import types
    from optimuspy.execution_mode import ExecutionMode

    class Dummy:
        pass

    d = Dummy()
    d.context = ExecutionContext()
    d.mode = ExecutionMode.ITERATIONS
    d.cube_name = "C"
    d.view_names = []
    d.process_names = []

    ram = {("A", "B"): 100.0, ("B", "A"): 80.0}
    log = []
    scripted(d, lambda o: ram[o], log)

    first = d._evaluate_permutation(["A", "B"], is_original_order=True)
    second = d._evaluate_permutation(["B", "A"])
    assert first.ram_usage == 100.0
    assert round(second.ram_usage, 6) == 80.0          # derived via % chain
    assert log == [["A", "B"], ["B", "A"]]


from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext
from optimuspy.executors import OptipyzerExecutor


def _bare_executor(view_names=None, process_names=None):
    ex = object.__new__(OptipyzerExecutor)
    ex.context = ExecutionContext()
    ex.mode = ExecutionMode.ITERATIONS
    ex.cube_name = "C"
    ex.view_names = view_names or []
    ex.process_names = process_names or []
    ex.cancel_event = None
    ex.checkpoint_manager = None
    ex._recovered_results = {}
    return ex


def test_sweep_into_position_evaluates_each_candidate_by_swapping(scripted):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    ram = {tuple(order): 100.0}
    # swapping D into last non-measure position 2:
    ram[("A", "C", "B", "M")] = 90.0   # B->C swap
    ram[("A", "B", "C", "M")] = 100.0
    log = []
    scripted(ex, lambda o: ram.get(o, 100.0), log)
    ex.context.set_initial_ram(100.0)

    results = ex._sweep_into_position(order, target_position=1, candidate_dims=["B", "C"],
                                      total_permutations=2)
    assert [r.dimension_order for r in results] == [["A", "B", "C", "M"], ["A", "C", "B", "M"]]


def test_sweep_into_position_honours_skip_candidate(scripted):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    log = []
    scripted(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    ex._sweep_into_position(order, 3, ["A", "B", "C"], total_permutations=3,
                            skip_candidate=lambda dim, pos: dim == "B")
    # B is skipped: it must never be the candidate swapped into target_position (index 3).
    assert not any(o[3] == "B" for o in log)
    # A and C are NOT skipped: they must genuinely have been swept into position 3.
    assert {o[3] for o in log} == {"A", "C"}


def test_sweep_across_positions_evaluates_each_position_by_swapping(scripted):
    ex = _bare_executor()
    order = ["A", "B", "C"]
    log = []
    scripted(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)

    results = ex._sweep_across_positions(order, target_dim="A", candidate_positions=[1, 2],
                                         total_permutations=2)
    assert [r.dimension_order.index("A") for r in results] == [1, 2]


def test_sweep_into_position_honours_skip_permutation(scripted):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    log = []
    scripted(ex, lambda o: 100.0, log)
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


def test_sweep_into_position_checkpoint_cb_sees_last_applied_order(scripted):
    ex = _bare_executor()
    order = ["A", "B", "C", "M"]
    log = []
    scripted(ex, lambda o: 100.0, log)
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


def test_pick_best_ram(scripted):
    ex = _bare_executor()
    log = []
    ram = {("A", "B"): 100.0, ("B", "A"): 70.0}
    scripted(ex, lambda o: ram[o], log)
    ex.context.set_initial_ram(100.0)
    r1 = ex._evaluate_permutation(["A", "B"], is_original_order=True)
    r2 = ex._evaluate_permutation(["B", "A"])
    assert ex._pick_best([r1, r2], "ram").dimension_order == ["B", "A"]


from optimuspy.executors import PositionOptimizerExecutor


def _make_position_optimizer(target_position, dims, exclude=None):
    ex = object.__new__(PositionOptimizerExecutor)
    ex.context = ExecutionContext()
    ex.mode = ExecutionMode.ITERATIONS
    ex.cube_name, ex.view_names, ex.process_names = "C", [], []
    ex.cancel_event = ex.checkpoint_manager = None
    ex.dimensions = list(dims)
    ex.target_position = target_position
    ex.dimensions_to_exclude = exclude or []
    ex._resumed_results = []
    ex._original_order_result = None
    ex._initial_dimension_order = None
    ex._recovered_results = {}
    # no string elements anywhere
    ex._has_string_elements = lambda name: False
    return ex


def test_position_optimizer_sweeps_all_other_dims(scripted):
    ex = _make_position_optimizer(0, ["A", "B", "C"])
    log = []
    scripted(ex, lambda o: 100.0 - len(log), log)  # strictly decreasing, deterministic
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    # position 0 currently holds A; candidates are B and C swapped into slot 0
    assert [r.dimension_order[0] for r in results] == ["B", "C"]


def test_position_optimizer_resume_never_requeries_completed_dims(scripted):
    # "A" is already completed from a prior checkpoint. On resume, the executor
    # must never call _has_string_elements("A") — completed dims are skipped
    # BEFORE the string check, exactly like the pre-refactor code did.
    ex = _make_position_optimizer(3, ["A", "B", "C", "D"])  # last position (index 3)
    string_calls = []

    def has_string_elements(name):
        string_calls.append(name)
        return False

    ex._has_string_elements = has_string_elements

    log = []
    scripted(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    resume_state = {"executor_state": {"position_state": {"completed_dimensions": ["A"]}}}
    results = ex.execute(resume_state)

    # "A" was already completed: it must never appear as a swept-in candidate.
    assert "A" not in [r.dimension_order[3] for r in results]
    assert "A" not in [o[3] for o in log]
    # "A" must never have been queried for string elements — it's completed,
    # so skip_candidate short-circuits before reaching the string check.
    assert "A" not in string_calls
    # The non-completed candidates (B, C) were genuinely swept.
    assert {r.dimension_order[3] for r in results} == {"B", "C"}
    # _has_string_elements called at most once per non-completed candidate (B, C).
    assert len(string_calls) <= 2


def test_position_optimizer_skips_string_candidate_at_last_position(scripted):
    # target_position is the last index; "B" has string elements and must never
    # be swept into the last slot. Non-string candidates must still be swept,
    # and _has_string_elements must be called at most once per non-completed
    # candidate (never twice for the same dim, never for completed dims).
    ex = _make_position_optimizer(3, ["A", "B", "C", "D"])  # last position (index 3)
    string_calls = []

    def has_string_elements(name):
        string_calls.append(name)
        return name == "B"

    ex._has_string_elements = has_string_elements

    log = []
    scripted(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    results = ex.execute()

    # "B" has strings and target position is last: it must never appear there.
    assert "B" not in [r.dimension_order[3] for r in results]
    assert "B" not in [o[3] for o in log]
    # Non-string candidates (A, C) were genuinely swept into the last slot.
    assert {r.dimension_order[3] for r in results} == {"A", "C"}
    # Candidates considered: A, B, C (D is the incumbent at position 3, excluded).
    non_completed_candidate_count = 3
    assert len(string_calls) <= non_completed_candidate_count
    # No candidate was queried more than once.
    from collections import Counter
    assert all(count == 1 for count in Counter(string_calls).values())


from optimuspy.executors import DimensionOptimizerExecutor


def _make_dimension_optimizer(target_dimension, dims, has_strings=False):
    ex = object.__new__(DimensionOptimizerExecutor)
    ex.context = ExecutionContext()
    ex.mode = ExecutionMode.ITERATIONS
    ex.cube_name, ex.view_names, ex.process_names = "C", [], []
    ex.cancel_event = ex.checkpoint_manager = None
    ex.dimensions = list(dims)
    ex.target_dimension = target_dimension
    ex._resumed_results = []
    ex._original_order_result = None
    ex._initial_dimension_order = None
    ex._recovered_results = {}
    ex._has_string_elements = lambda name: has_strings
    return ex


def test_dimension_optimizer_sweeps_all_positions_except_current(scripted):
    ex = _make_dimension_optimizer("A", ["A", "B", "C"])  # A at idx 0
    log = []
    scripted(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    # A moved into positions 1 and 2
    assert [r.dimension_order.index("A") for r in results] == [1, 2]


def test_dimension_optimizer_skips_last_position_for_string_dim(scripted):
    ex = _make_dimension_optimizer("A", ["A", "B", "C"], has_strings=True)
    log = []
    scripted(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)
    results = ex.execute()
    assert all(r.dimension_order[-1] != "A" for r in results)


def test_dimension_optimizer_resume_skips_completed_position(scripted):
    # Position 1 is already completed from a prior checkpoint. On resume, the
    # target dim must never be re-swapped into that position — only the
    # remaining candidate position(s) get swept.
    ex = _make_dimension_optimizer("A", ["A", "B", "C"])  # A at idx 0
    log = []
    scripted(ex, lambda o: 100.0 - len(log), log)
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
