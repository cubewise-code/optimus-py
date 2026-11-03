import pytest

from optimuspy import search
from optimuspy.order_frame import OrderFrame
from optimuspy.results import ExecutionContext
from optimuspy.executors import MainExecutor
from tests.conftest import offline_executor


def make_main_executor(dims, *, fast=False,
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
        fast=fast)


def spy_sweeps(ex):
    """Record (target_position, candidates) for every slot the search sweeps."""
    sweeps = []
    real = ex._sweep_into_position

    def spy(current_order, target_position, candidate_dims, *a, **k):
        sweeps.append((target_position, list(candidate_dims)))
        return real(current_order, target_position, candidate_dims, *a, **k)

    ex._sweep_into_position = spy
    return sweeps


def test_main_executor_constructor_takes_its_frame():
    frame = OrderFrame(["A", "B"], True)
    ex = MainExecutor(
        tm1=None, cube_name="C", view_names=[], process_names=[],
        dimensions=["A", "B"], executions=1, last_slot_locked=True,
        context=ExecutionContext(), order_frame=frame)
    assert ex.order_frame is frame
    assert ex.order_frame.locked_dimension == "B"


# --- the regression this search exists for -----------------------------------

# A production planning cube as it was found in the field. The time dimension
# has a handful of leaves but is dense: nearly every SKU and plant has data in
# every month, so it belongs in the last slot. A search that only tried the
# dimensions with the most leaves in the last slot never measured it there and
# reported -2% where -78% was available.
FIELD_ORDER = ["PLANT_Line_Plan", "VERS_All", "TIME_Months", "CURR_Plan", "ADJ_Task_Oth",
               "MU_DemandingCountry", "PDT_ProductionSKU", "CostComponent_Plan",
               "VAR_Product_View", "VAR_COMM_Measure", "VAR_SITE_COMM_Measure", "VAR_Value"]


def field_ram(order):
    """Measured shape: TIME_Months last is worth ~78%, SKU last ~1%."""
    last = order[-1]
    return {"TIME_Months": 30.8, "PDT_ProductionSKU": 136.8}.get(last, 138.4)


@pytest.mark.parametrize("fast", [False, True])
def test_the_dense_small_dimension_is_measured_in_the_last_slot_and_wins(fast, measure_orders):
    ex = make_main_executor(FIELD_ORDER, fast=fast)
    log = []
    measure_orders(ex, field_ram, log)
    ex._original_order_result = ex._evaluate_permutation(
        list(FIELD_ORDER), retrieve_ram=True, is_original_order=True)
    log.clear()

    results = ex.execute()

    assert any(o[-1] == "TIME_Months" for o in log), \
        "TIME_Months was never measured in the last slot"
    best = min(results, key=lambda r: r.ram_usage)
    assert best.dimension_order[-1] == "TIME_Months"
    assert best.ram_usage == pytest.approx(30.8)


# --- what each slot measures ---------------------------------------------------

def test_every_unplaced_dimension_is_measured_at_every_slot(measure_orders):
    dims = ["A", "B", "C", "D", "M"]
    ex = make_main_executor(dims)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    sweeps = spy_sweeps(ex)

    ex.execute()

    # Outside in, up to the midpoint (5 // 2 == 2): last, first, second-to-last, second.
    assert [p for p, _ in sweeps] == [4, 0, 3, 1]
    # Every slot sees every dimension not yet placed, bar the one already there.
    assert [len(c) for _, c in sweeps] == [4, 3, 2, 1]
    assert len(log) == search.planned_evaluations(len(dims), 4) == 10


def test_fast_sweeps_the_last_and_the_first_slot_only(measure_orders):
    dims = ["A", "B", "C", "D", "M"]
    ex = make_main_executor(dims, fast=True)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    sweeps = spy_sweeps(ex)

    ex.execute()

    assert [p for p, _ in sweeps] == [4, 0]
    assert sorted(sweeps[0][1]) == ["A", "B", "C", "D"]  # everyone tries the last slot
    assert len(log) == 4 + 3


def test_fast_with_a_locked_last_slot_sweeps_the_last_free_slot(measure_orders):
    dims = ["A", "B", "C", "D", "M"]
    ex = make_main_executor(dims, fast=True, last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    sweeps = spy_sweeps(ex)

    ex.execute()

    assert [p for p, _ in sweeps] == [0, 3]


def test_the_back_half_keeps_the_lowest_ram_and_the_front_the_fastest_query(measure_orders):
    # RAM rewards C last and penalises B first; query time rewards B first. With
    # a view the first slot is query-ranked, so B wins it although it costs RAM.
    # Slots: 5 (RAM), 0 (query), 4 (RAM), 1 (query). Every order measured after
    # the first two sweeps stands on their winners.
    dims = ["A", "B", "C", "D", "E", "M"]
    ex = make_main_executor(dims, view_names=["V"])
    log = []
    measure_orders(
        ex,
        lambda o: 100.0 - (20.0 if o[-1] == "C" else 0.0) + (5.0 if o[0] == "B" else 0.0),
        log,
        query_of=lambda o: 1.0 if o[0] == "B" else 2.0)
    ex._original_order_result = ex._evaluate_permutation(
        list(dims), retrieve_ram=True, is_original_order=True)
    log.clear()

    ex.execute()

    later = log[5 + 4:]
    assert later, "the search stopped after two slots"
    assert all(o[-1] == "C" for o in later)
    assert all(o[0] == "B" for o in later)


# --- constraints the search honours ------------------------------------------

@pytest.mark.parametrize("fast", [False, True])
def test_the_locked_dimension_never_moves(fast, measure_orders):
    dims = ["A", "S", "B", "C", "M"]
    ex = make_main_executor(dims, fast=fast, last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    sweeps = spy_sweeps(ex)

    ex.execute()

    assert log, "the search evaluated nothing"
    assert all(o[-1] == "M" for o in log), \
        f"locked dim left the last slot: {[o for o in log if o[-1] != 'M']}"
    assert all("M" not in candidates for _, candidates in sweeps)


def test_a_non_last_string_dimension_is_swept_like_any_other(measure_orders):
    # Dimensions are shared between cubes, so "S" can carry string elements from
    # another cube's use while not being this cube's measure. Only the last slot
    # is locked; S moves like anything else.
    dims = ["A", "S", "B", "C", "M"]
    ex = make_main_executor(dims, last_slot_locked=True)
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    sweeps = spy_sweeps(ex)

    ex.execute()

    assert any("S" in candidates for _, candidates in sweeps)
    assert any(o.index("S") != dims.index("S") for o in log)


@pytest.mark.parametrize("fast", [False, True])
def test_an_excluded_dimension_stays_where_it_is(fast, measure_orders):
    dims = ["Excl", "D1", "D2", "D3", "M"]
    ex = make_main_executor(dims, fast=fast, exclude=["Excl"])
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    sweeps = spy_sweeps(ex)

    ex.execute()

    assert log
    assert all(o[0] == "Excl" for o in log)
    assert all("Excl" not in candidates for _, candidates in sweeps)
    assert 0 not in [p for p, _ in sweeps]


def test_the_occupant_is_not_re_measured(measure_orders):
    # The dim already sitting at a target position must NOT be re-swept into its
    # own slot (a redundant no-op reorder that duplicates the current order in the
    # report). Its "keep it here" value is carried by the current-order result.
    from optimuspy.results import OptimusResult
    from optimuspy.core import _deduplicate_results
    dims = ["A", "B", "C", "M"]
    ex = make_main_executor(dims)
    log = []
    # Original order is uniquely lowest, so "keep" should win outright.
    measure_orders(ex, lambda o: 90.0 if o == tuple(dims) else 100.0, log)
    # Mirror production: core measures the original order once and hands it in.
    ex._original_order_result = ex._evaluate_permutation(
        list(dims), retrieve_ram=True, is_original_order=True)
    log.clear()
    results = ex.execute()

    # (a) The current order never reappears as a redundant no-op reorder.
    assert list(dims) not in log
    # (b) "Keep it here" is still available: the uniquely-lowest original order is
    #     selected as best rather than being forced out.
    unique = _deduplicate_results([ex._original_order_result], results)
    best = OptimusResult("C", unique).best_result
    assert list(best.dimension_order) == list(dims)


def test_progress_reports_the_planned_total(measure_orders, caplog):
    dims = ["A", "B", "C", "D", "M"]
    ex = make_main_executor(dims)
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    # The original order is measured first in production and is never an iteration.
    ex._original_order_result = ex._evaluate_permutation(
        list(dims), retrieve_ram=True, is_original_order=True)

    with caplog.at_level("INFO"):
        ex.execute()

    assert "up to 10 order(s) to measure" in caplog.text
    assert "Iteration 10 of 10" in caplog.text
