from optimuspy.order_frame import OrderFrame
from optimuspy.results import ExecutionContext
from optimuspy.executors import MainExecutor
from tests.conftest import offline_executor


def make_main_executor(dims, cardinality, *, fast=False,
                       view_names=None, process_names=None, last_slot_locked=False,
                       exclude=None, orders_to_ignore=None, position_rules=None):
    return offline_executor(
        MainExecutor, dims,
        view_names=view_names, process_names=process_names,
        last_slot_locked=last_slot_locked,
        order_frame=OrderFrame(
            dims, last_slot_locked,
            dimensions_to_exclude=exclude,
            orders_to_ignore=orders_to_ignore,
            position_rules=position_rules),
        fast=fast, cardinality=cardinality)


def test_main_executor_stores_cardinality_and_its_frame():
    ex = make_main_executor(["A", "B"], {"A": 10, "B": 20}, last_slot_locked=True)
    assert ex.cardinality == {"A": 10, "B": 20}
    assert ex.order_frame.locked_dimension == "B"


def test_main_executor_constructor_accepts_cardinality_and_frame():
    frame = OrderFrame(["A", "B"], True)
    ex = MainExecutor(
        tm1=None, cube_name="C", view_names=[], process_names=[],
        dimensions=["A", "B"], executions=1, last_slot_locked=True,
        context=ExecutionContext(), cardinality={"A": 10, "B": 20}, order_frame=frame)
    assert ex.cardinality == {"A": 10, "B": 20}
    assert ex.order_frame is frame


def test_fold_a_pins_dominant_dim_to_back_with_one_reorder(measure_orders):
    # 4 sparse dims + numeric measure. Dim "Big" (50000) dominates all by >> τ.
    # last_slot_locked=False keeps M fully in the swappable pool, so the true
    # back-most slot is index len(dims)-1 (not "just before" a fixed measure).
    dims = ["D1", "D2", "D3", "Big", "M"]
    card = {"D1": 100, "D2": 120, "D3": 150, "Big": 50000, "M": 3}
    ex = make_main_executor(dims, card, last_slot_locked=False)
    log = []
    # RAM: reward putting Big at the back.
    def ram_of(o):
        return 100.0 - (10.0 if o.index("Big") >= 3 else 0.0)
    measure_orders(ex, ram_of, log)
    ex.context.set_initial_ram(100.0)

    ex._run_fold_a()
    # Back-most open position's frontier is just Big -> the very first (and only)
    # evaluated reorder at that position already places it in the back-most slot.
    assert log[0].index("Big") == len(dims) - 1
    # Big is never test-swapped into a front position (theory-condemned, pruned):
    assert all(o.index("Big") >= 2 for o in log)


def test_fold_a_measures_near_tied_cluster_in_full(measure_orders):
    dims = ["A", "B", "C", "M"]
    card = {"A": 180, "B": 205, "C": 240, "M": 3}  # A,B,C all within 4x -> nothing decided
    ex = make_main_executor(dims, card)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    # Undecided cluster -> at the first (back-most, target_position=len(dims)-1)
    # position, all of A,B,C are swept in as candidates.
    first_back_orders = log[:3]
    placed_last_nonmeasure = {o[len(dims) - 1] for o in first_back_orders}
    assert placed_last_nonmeasure == {"A", "B", "C"}


def test_fold_a_never_moves_the_locked_dimension(measure_orders):
    # The storage-last dim carries string elements, so its slot is locked: no
    # evaluated order may move it, and it is never a swap candidate.
    dims = ["A", "S", "B", "C", "M"]
    card = {"A": 100, "S": 50, "B": 110, "C": 120, "M": 130}
    ex = make_main_executor(dims, card, last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0, log)  # ties -> exercise sweeps, no acceptance noise
    ex.context.set_initial_ram(100.0)

    swept = []
    orig = ex._sweep_into_position

    def spy(current_order, target_position, candidate_dims, *a, **k):
        swept.extend(candidate_dims)
        return orig(current_order, target_position, candidate_dims, *a, **k)

    ex._sweep_into_position = spy
    ex._run_fold_a()

    assert log, "fold A evaluated nothing"
    assert all(o[-1] == "M" for o in log), \
        f"locked dim left the last slot: {[o for o in log if o[-1] != 'M']}"
    assert swept and "M" not in swept
    assert set(swept) <= {"A", "S", "B", "C"}


def test_fold_a_places_a_non_last_string_dim_by_cardinality(measure_orders):
    # Dimensions are shared between cubes, so "S" can carry string elements from
    # another cube's use while not being this cube's measure. The old code
    # relocated EVERY string-bearing dim to the back; the locked-slot rule leaves
    # this one movable, so it is swept like any other dimension and placed by
    # cardinality. This is the one case where the old and new rules disagree.
    dims = ["A", "S", "B", "C", "M"]
    card = {"A": 100, "S": 50, "B": 110, "C": 120, "M": 130}
    ex = make_main_executor(dims, card, last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)

    swept = []
    orig = ex._sweep_into_position

    def spy(current_order, target_position, candidate_dims, *a, **k):
        swept.extend(candidate_dims)
        return orig(current_order, target_position, candidate_dims, *a, **k)

    ex._sweep_into_position = spy
    ex._run_fold_a()

    # "S" is a swap candidate — the old code would have frozen it at the back.
    assert "S" in swept
    # And it is genuinely evaluated somewhere other than where it started.
    assert any(o.index("S") != dims.index("S") for o in log), \
        "the non-last string dim was never moved"


def test_fold_a_query_front_uses_looser_tau(measure_orders):
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
    measure_orders(ex, lambda o: 100.0, log, query_of=lambda o: 1.0 + o.index("A") * 0.01)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    # B is swapped into the front position (index 0) only when tau_query (not
    # tau_ram) keeps it as a candidate at that position.
    assert any(o[0] == "B" for o in log)
    # The back position was pinned to the dominant dim C.
    assert any(o[3] == "C" for o in log)


def test_fold_a_process_front_not_pruned(measure_orders):
    # Process-ranked front positions must NOT be tau-pruned: tau_for_position
    # returns None for "process" (cardinality cannot predict process time), so
    # fold_a_candidates returns every unplaced dim regardless of tau.
    dims = ["A", "B", "C", "M"]
    card = {"A": 10, "B": 100, "C": 5000, "M": 3}
    ex = make_main_executor(dims, card, process_names=["P"])
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    # B (100/3 ~= 33x M) would be excluded from a RAM-ranked front frontier at
    # tau_ram=4, yet reaches the process-ranked front position (index 0),
    # proving candidate selection there is unpruned.
    assert any(o[0] == "B" for o in log)
    # The back position is still pinned to the dominant dim C.
    assert any(o[3] == "C" for o in log)


def test_fold_a_freezes_excluded_dim(measure_orders):
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
    # Excl sits inside the undecided cluster (10/11/12 vs M=3), so it is a
    # genuine sweep candidate on cardinality alone — the exclusion is the only
    # thing holding it. An Excl the tau frontier would have pruned anyway would
    # make this test pass with the exclusion removed.
    card = {"Excl": 11, "D1": 10, "D2": 12, "D3": 5000, "M": 3}
    ex = make_main_executor(dims, card, last_slot_locked=False, exclude=["Excl"])
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)

    ex._run_fold_a()

    # (a) Excl never moves from its original index in ANY evaluated order.
    assert all(o.index("Excl") == 0 for o in log)
    # (b) Excl never appears anywhere other than its frozen slot -- i.e. it is
    # never the dim newly swept into a target position.
    assert all(o[0] == "Excl" for o in log)


def test_fold_a_does_not_re_measure_the_occupant(measure_orders):
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
    measure_orders(ex, lambda o: 90.0 if o == list(dims) else 100.0, log)
    # Mirror production: core measures the original order once and hands it in.
    ex._original_order_result = ex._evaluate_permutation(
        list(dims), retrieve_ram=True, is_original_order=True)
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
