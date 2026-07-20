from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext
from optimuspy.executors import MainExecutor


def make_main_executor(dims, cardinality, *, fast=False, string_dims=None,
                       view_names=None, process_names=None, measure_only_numeric=True):
    ex = object.__new__(MainExecutor)
    ex.context = ExecutionContext()
    ex.mode = ExecutionMode.ITERATIONS
    ex.cube_name = "C"
    ex.view_names = view_names or []
    ex.process_names = process_names or []
    ex.include_process = bool(ex.process_names)
    ex.dimensions = list(dims)
    ex.cube_dim_number = len(dims)
    ex.executions = 1
    ex.measure_dimension_only_numeric = measure_only_numeric
    ex.fast = fast
    ex.dimensions_to_exclude = []
    ex.orders_to_ignore = []
    ex.dimension_position_rules = []
    ex.cancel_event = ex.checkpoint_manager = None
    ex.cardinality = dict(cardinality)
    ex.string_dims = set(string_dims or [])
    ex._resumed_results = []
    ex._original_order_result = None
    ex._initial_dimension_order = None
    ex._reanchor_needed = False
    ex._last_checkpoint = None
    ex._recovered_results = {}
    return ex


def test_main_executor_stores_cardinality_and_string_dims():
    ex = make_main_executor(["A", "B"], {"A": 10, "B": 20}, string_dims=["B"])
    assert ex.cardinality == {"A": 10, "B": 20}
    assert ex.string_dims == {"B"}


def test_main_executor_constructor_accepts_cardinality_kwargs():
    ex = MainExecutor(
        tm1=None, cube_name="C", view_names=[], process_names=[],
        dimensions=["A", "B"], executions=1, measure_dimension_only_numeric=True,
        context=ExecutionContext(), cardinality={"A": 10, "B": 20}, string_dims=["B"])
    assert ex.cardinality == {"A": 10, "B": 20}
    assert ex.string_dims == {"B"}


def test_fold_a_pins_dominant_dim_to_back_with_one_reorder(scripted):
    # 4 sparse dims + numeric measure. Dim "Big" (50000) dominates all by >> τ.
    # measure_only_numeric=True keeps M fully in the swappable pool, so the true
    # back-most slot is index len(dims)-1 (not "just before" a fixed measure).
    dims = ["D1", "D2", "D3", "Big", "M"]
    card = {"D1": 100, "D2": 120, "D3": 150, "Big": 50000, "M": 3}
    ex = make_main_executor(dims, card, measure_only_numeric=True)
    log = []
    # RAM: reward putting Big at the back.
    def ram_of(o):
        return 100.0 - (10.0 if o.index("Big") >= 3 else 0.0)
    scripted(ex, ram_of, log)
    ex.context.set_initial_ram(100.0)

    ex._run_fold_a()
    # Back-most open position's frontier is just Big -> the very first (and only)
    # evaluated reorder at that position already places it in the back-most slot.
    assert log[0].index("Big") == len(dims) - 1
    # Big is never test-swapped into a front position (theory-condemned, pruned):
    assert all(o.index("Big") >= 2 for o in log)


def test_fold_a_measures_near_tied_cluster_in_full(scripted):
    dims = ["A", "B", "C", "M"]
    card = {"A": 180, "B": 205, "C": 240, "M": 3}  # A,B,C all within 4x -> nothing decided
    ex = make_main_executor(dims, card)
    log = []
    scripted(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    # Undecided cluster -> at the first (back-most, target_position=len(dims)-1)
    # position, all of A,B,C are swept in as candidates.
    first_back_orders = log[:3]
    placed_last_nonmeasure = {o[len(dims) - 1] for o in first_back_orders}
    assert placed_last_nonmeasure == {"A", "B", "C"}


def test_fold_a_freezes_string_dim_last_even_when_not_presentation_last(scripted):
    # Hardening (#2): Fold A must lock the *string* dim (authoritative
    # self.string_dims) to the last slot, NOT presentation-order [-1]. Here the
    # string dim "S" sits at presentation index 1 and the presentation-last dim
    # "D" is numeric (an already-optimized cube whose build order != storage order).
    # Before the fix, Fold A froze "D" and left "S" in the movable pool, sweeping it
    # into non-last positions -> a CellPutS-breaking order. The fix moves "S" last
    # and freezes it there.
    dims = ["A", "S", "B", "C", "D"]
    card = {"A": 100, "S": 50, "B": 110, "C": 120, "D": 130}
    ex = make_main_executor(dims, card, string_dims=["S"], measure_only_numeric=False)
    log = []
    scripted(ex, lambda o: 100.0, log)  # ties -> exercise sweeps, no acceptance noise
    ex.context.set_initial_ram(100.0)

    swept = []
    orig = ex._sweep_into_position

    def spy(current_order, target_position, candidate_dims, *a, **k):
        swept.extend(candidate_dims)
        return orig(current_order, target_position, candidate_dims, *a, **k)

    ex._sweep_into_position = spy
    ex._run_fold_a()

    assert log, "fold A evaluated nothing"
    # The string dim is last in EVERY evaluated order (the TM1 CellPutS invariant).
    assert all(o[-1] == "S" for o in log), \
        f"string dim left the last slot: {[o for o in log if o[-1] != 'S']}"
    # Refinement ran on the numeric dims, but "S" is frozen -> never a swap candidate.
    assert swept and "S" not in swept
    assert set(swept) <= {"A", "B", "C", "D"}


def test_fold_a_query_front_uses_looser_tau(scripted):
    # With a view, front (query-ranked) positions prune with tau_query (10x), not
    # tau_ram (4x). dims = [A, B, C, M], card = {A:10, B:18, C:5000, M:3}; mid=2.
    # The walk visits back position 3 (RAM-ranked) then front position 0
    # (query-ranked), then breaks at mid. At position 3, C (5000) dominates
    # everything else by >>4x -> back_frontier is just [C], so C is pinned to the
    # back-most slot. At position 0, the remaining pool is {A:10, B:18, M:3}:
    # front_frontier under tau_query=10 keeps all three (B/M = 18/3 = 6 < 10), but
    # under tau_ram=4 it would exclude B (6 >= 4). So B reaching the front sweep
    # at all is only possible under tau_query.
    dims = ["A", "B", "C", "M"]
    card = {"A": 10, "B": 18, "C": 5000, "M": 3}
    ex = make_main_executor(dims, card, view_names=["V"])
    log = []
    scripted(ex, lambda o: 100.0, log, query_of=lambda o: 1.0 + o.index("A") * 0.01)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    # B is swapped into the front position (index 0) only when tau_query (not
    # tau_ram) keeps it as a candidate at that position.
    assert any(o[0] == "B" for o in log)
    # The back position was pinned to the dominant dim C.
    assert any(o[3] == "C" for o in log)


def test_fold_a_process_front_not_pruned(scripted):
    # Process-ranked front positions must NOT be tau-pruned: tau_for_position
    # returns None for "process" (cardinality cannot predict process time), so
    # fold_a_candidates returns every unplaced dim regardless of tau.
    dims = ["A", "B", "C", "M"]
    card = {"A": 10, "B": 100, "C": 5000, "M": 3}
    ex = make_main_executor(dims, card, process_names=["P"])
    log = []
    scripted(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    # B (100/3 ~= 33x M) would be excluded from a RAM-ranked front frontier at
    # tau_ram=4, yet reaches the process-ranked front position (index 0),
    # proving candidate selection there is unpruned.
    assert any(o[0] == "B" for o in log)
    # The back position is still pinned to the dominant dim C.
    assert any(o[3] == "C" for o in log)


def test_fold_a_freezes_excluded_dim(scripted):
    # "Excl" is pinned via dimensions_to_exclude at its original index (0).
    # dimension_pool already omits it from candidacy (pre-existing behaviour),
    # but WITHOUT the occupant guard, nothing stops another candidate from
    # being swept INTO position 0 (Excl's home), displacing it there.
    # D3 dominates everything (>>4x) -> pinned to the back-most slot first;
    # the pool remaining afterward (D1/D2/M, all mutually within tau of the
    # smallest, M=3) makes position 0 (front, mid=2) a genuine multi-candidate
    # sweep -- exactly the kind of sweep that would otherwise swap into Excl's
    # frozen slot.
    dims = ["Excl", "D1", "D2", "D3", "M"]
    card = {"D1": 10, "D2": 12, "D3": 5000, "M": 3}
    ex = make_main_executor(dims, card, measure_only_numeric=True)
    ex.dimensions_to_exclude = ["Excl"]
    log = []
    scripted(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)

    ex._run_fold_a()

    # (a) Excl never moves from its original index in ANY evaluated order.
    assert all(o.index("Excl") == 0 for o in log)
    # (b) Excl never appears anywhere other than its frozen slot -- i.e. it is
    # never the dim newly swept into a target position.
    assert all(o[0] == "Excl" for o in log)


def test_fold_a_does_not_re_measure_the_occupant(scripted):
    # The dim already sitting at a target position must NOT be re-swept into its
    # own slot (a redundant no-op reorder that duplicates the current order in the
    # report). Its "keep it here" value is carried by the current-order result.
    from optimuspy.results import OptimusResult
    from optimuspy.core import _deduplicate_results
    dims = ["A", "B", "C", "M"]
    card = {"A": 10, "B": 11, "C": 12, "M": 9}  # all within tau -> full frontiers
    ex = make_main_executor(dims, card)
    log = []
    # Original order is uniquely lowest, so "keep" should win outright.
    scripted(ex, lambda o: 90.0 if o == list(dims) else 100.0, log)
    # Mirror production: core measures the original order once and hands it in.
    ex._original_order_result = ex._evaluate_permutation(list(dims), is_original_order=True)
    log.clear()
    results = ex._run_fold_a()

    # (a) The occupant is never re-measured -> the current order never reappears
    #     as a redundant no-op reorder in the evaluated log.
    assert list(dims) not in log
    # (b) "Keep it here" is still available: the uniquely-lowest original order is
    #     selected as best rather than being forced out.
    unique = _deduplicate_results([ex._original_order_result], results)
    best = OptimusResult("C", unique).best_result
    assert list(best.dimension_order) == list(dims)
