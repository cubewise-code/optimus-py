"""The three tiers of admissibility, on the two entry points that take an
explicitly named order: set mode and predefined orders.

Offline, no fake. Set mode's tier-1 and tier-2 paths both return before any TM1
call, so they are driven with tm1=None: if either ever reached the server, these
tests would fail rather than pass quietly.
"""
import logging

import pytest

from optimuspy.core import (_execute_set_mode, _validate_predefined_orders,
                            validate_cube_config)
from optimuspy.executors import PredefinedOrderExecutor
from optimuspy.order_frame import OrderFrame, REASON_LOCKED_SLOT
from tests.conftest import offline_executor

STORAGE = ["Year", "Region", "Product", "Measure"]
LOCKED = OrderFrame(STORAGE, True)
UNLOCKED = OrderFrame(STORAGE, False)


# --- set mode --------------------------------------------------------------

def test_set_mode_tier2_skips_the_reorder_and_exits_zero(caplog):
    # Decision 6: a locked-slot violation warns, skips, and never fails the
    # process — a TI process must not see a non-zero exit for a constraint TM1
    # would have enforced anyway.
    moves_locked = ["Measure", "Year", "Region", "Product"]
    with caplog.at_level(logging.WARNING):
        applied = _execute_set_mode(None, "Sales", moves_locked, False, LOCKED)

    assert applied is True  # -> exit 0
    warning = "\n".join(r.message for r in caplog.records if r.levelno == logging.WARNING)
    # The log line is the only channel a TI caller has, so it must name the
    # dimension, say the cube is unchanged, and say the exit code means nothing
    # was applied.
    assert "REORDER SKIPPED" in warning
    assert "Measure" in warning
    assert "unchanged" in warning
    assert "Exiting 0" in warning


def test_set_mode_tier1_fails_the_process(caplog):
    # Decision 12: a malformed order is a config error, not a constraint
    # collision. Set mode is the one place that exits non-zero, because a TI
    # process must not see success after a typo silently did nothing.
    typo = ["Year", "Region", "Prodcut", "Measure"]
    with caplog.at_level(logging.ERROR):
        applied = _execute_set_mode(None, "Sales", typo, False, LOCKED)

    assert applied is False  # -> exit 1
    error = "\n".join(r.message for r in caplog.records if r.levelno == logging.ERROR)
    assert "Prodcut" in error
    assert "No reorder was applied" in error


def test_set_mode_tier1_outranks_tier2():
    # An order that is both malformed AND moves the locked dim fails, rather
    # than being courteously skipped: there is nothing coherent to be courteous
    # about.
    both = ["Measure", "Year", "Region", "Nonsense"]
    assert _execute_set_mode(None, "Sales", both, False, LOCKED) is False


def test_set_mode_applies_an_admissible_order():
    class _TM1:
        def __init__(self):
            self.applied = []
            self.cubes = self
            self.metrics = self

        def update_storage_dimension_order(self, cube_name, order):
            self.applied.append((cube_name, list(order)))
            return -5.0

        def by_cube(self, cube=None):
            raise RuntimeError("RAM logging is best-effort and suppressed")

    tm1 = _TM1()
    good = ["Region", "Year", "Product", "Measure"]
    assert _execute_set_mode(tm1, "Sales", good, False, LOCKED) is True
    assert tm1.applied == [("Sales", good)]


def test_set_mode_has_no_lock_when_the_last_dim_is_numeric():
    class _TM1:
        def __init__(self):
            self.applied = []
            self.cubes = self
            self.metrics = self

        def update_storage_dimension_order(self, cube_name, order):
            self.applied.append(list(order))
            return -1.0

        def by_cube(self, cube=None):
            raise RuntimeError("suppressed")

    tm1 = _TM1()
    moves_last = ["Measure", "Year", "Region", "Product"]
    assert _execute_set_mode(tm1, "Sales", moves_last, False, UNLOCKED) is True
    assert tm1.applied == [moves_last]


# --- predefined orders -----------------------------------------------------

def test_predefined_tier1_is_rejected_before_any_reorder():
    # The whole config is refused up front, so a typo cannot fail the run
    # half-way with cubes already modified.
    orders = [["Year", "Region", "Product", "Measure"],
              ["Year", "Region", "Prodcut", "Measure"]]
    with pytest.raises(ValueError) as excinfo:
        _validate_predefined_orders(orders, LOCKED, "Sales")
    assert "predefined_orders[1]" in str(excinfo.value)
    assert "Prodcut" in str(excinfo.value)


def test_predefined_tier1_reports_every_bad_entry_not_just_the_first():
    orders = [["Year", "Region", "Prodcut", "Measure"],
              ["Year", "Region", "Product", "Measure"],
              ["Year", "Region", "Product"]]
    with pytest.raises(ValueError) as excinfo:
        _validate_predefined_orders(orders, LOCKED, "Sales")
    message = str(excinfo.value)
    assert "predefined_orders[0]" in message
    assert "predefined_orders[2]" in message
    assert "predefined_orders[1]" not in message


def test_predefined_tier2_is_not_a_tier1_failure():
    # An order that merely moves the locked dim is well-formed: it passes the
    # up-front check and is skipped later, per order.
    orders = [["Measure", "Year", "Region", "Product"]]
    _validate_predefined_orders(orders, LOCKED, "Sales")  # does not raise


def _make_predefined(orders, frame):
    return offline_executor(PredefinedOrderExecutor, STORAGE, cube_name="Sales",
                            order_frame=frame, predefined_orders=orders)


def test_predefined_tier2_skips_the_order_and_keeps_going(measure_orders):
    good_first = ["Region", "Year", "Product", "Measure"]
    moves_locked = ["Measure", "Year", "Region", "Product"]
    good_last = ["Product", "Region", "Year", "Measure"]
    ex = _make_predefined([good_first, moves_locked, good_last], LOCKED)
    log = []
    measure_orders(ex, lambda o: 100.0 - len(log), log)
    ex.context.set_initial_ram(100.0)

    results = ex.execute()

    # The violating order is skipped; the run does not fail and does not stop.
    assert [list(r.dimension_order) for r in results] == [good_first, good_last]
    assert moves_locked not in log
    assert ex.skipped_orders == {REASON_LOCKED_SLOT: 1}


def test_predefined_evaluates_everything_when_there_is_no_lock(measure_orders):
    moves_last = ["Measure", "Year", "Region", "Product"]
    ex = _make_predefined([moves_last], UNLOCKED)
    log = []
    measure_orders(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)

    results = ex.execute()

    assert [list(r.dimension_order) for r in results] == [moves_last]
    assert ex.skipped_orders == {}


# --- what validate_cube_config can settle without a server -----------------

@pytest.mark.parametrize("orders, fragment", [
    ([[]], "is empty"),
    ([["Year", "Year", "Region", "Measure"]], "repeats"),
    ([["Year", 3, "Region", "Measure"]], "non-empty dimension names"),
    ([["Year", "  ", "Region", "Measure"]], "non-empty dimension names"),
])
def test_config_validation_catches_malformed_orders_offline(orders, fragment):
    config = {"instance": "tm1srv01", "cube": "Sales", "executions": 1,
              "output": "csv", "predefined_orders": orders}
    with pytest.raises(ValueError) as excinfo:
        validate_cube_config(config, "optimize")
    assert fragment in str(excinfo.value)


def test_config_validation_accepts_a_well_shaped_order():
    config = {"instance": "tm1srv01", "cube": "Sales", "executions": 1,
              "output": "csv", "predefined_orders": [list(STORAGE)]}
    validate_cube_config(config, "optimize")  # does not raise
