"""Offline tests for the order frame. No TM1, no fake — the module is pure."""
import itertools

import pytest

from optimuspy.order_frame import (
    OrderFrame,
    REASON_IGNORED_ORDER,
    REASON_LOCKED_SLOT,
    REASON_NOT_A_PERMUTATION,
    REASON_POSITION_RULE,
)

STORAGE = ["Year", "Region", "Product", "Account", "Measure"]


def frame(**kwargs):
    locked = kwargs.pop("last_slot_locked", False)
    return OrderFrame(STORAGE, locked, **kwargs)


# --- the locked slot -------------------------------------------------------

def test_no_lock_means_every_permutation_is_admissible():
    f = frame(last_slot_locked=False)
    moved = ["Measure", "Year", "Region", "Product", "Account"]
    assert f.admits(moved).admissible
    assert f.locked_dimension is None
    assert f.locked_position is None


def test_lock_admits_any_order_that_keeps_the_locked_dim_last():
    f = frame(last_slot_locked=True)
    assert f.admits(["Region", "Year", "Account", "Product", "Measure"]).admissible


def test_lock_refuses_an_order_that_moves_the_locked_dim():
    f = frame(last_slot_locked=True)
    verdict = f.admits(["Measure", "Year", "Region", "Product", "Account"])
    assert not verdict.admissible
    assert verdict.code == REASON_LOCKED_SLOT
    # The reason must name the dimension and where the order would put it —
    # it is the only channel a TI process calling set mode has.
    assert "Measure" in verdict.reason
    assert "position 0" in verdict.reason


def test_lock_keys_off_the_storage_last_dim_not_a_string_dim_elsewhere():
    # A dimension is shared across cubes, so one that is NOT storage-last may
    # still carry string elements. The lock ignores it: only the last slot binds.
    f = OrderFrame(["Year", "Notes", "Region", "Measure"], last_slot_locked=False)
    assert f.admits(["Notes", "Year", "Region", "Measure"]).admissible
    assert f.locked_dimension is None


def test_locked_position_is_the_last_index():
    assert frame(last_slot_locked=True).locked_position == len(STORAGE) - 1


# --- candidate sanity ------------------------------------------------------

def test_an_order_with_an_unknown_dimension_is_refused():
    f = frame()
    verdict = f.admits(["Year", "Region", "Product", "Account", "Typo"])
    assert not verdict.admissible
    assert verdict.code == REASON_NOT_A_PERMUTATION


def test_an_order_missing_a_dimension_is_refused():
    f = frame()
    verdict = f.admits(["Year", "Region", "Product", "Account"])
    assert not verdict.admissible
    assert verdict.code == REASON_NOT_A_PERMUTATION


def test_a_duplicated_dimension_is_refused():
    f = frame()
    verdict = f.admits(["Year", "Year", "Product", "Account", "Measure"])
    assert not verdict.admissible
    assert verdict.code == REASON_NOT_A_PERMUTATION


# --- user preferences (greedy-only) ---------------------------------------

def test_preferences_are_absent_unless_supplied():
    # A non-greedy caller supplies none, so an ignored order or a position rule
    # belonging to some other run can never affect it.
    f = OrderFrame(STORAGE, True)
    assert f.orders_to_ignore == []
    assert f.position_rules == []
    assert f.dimensions_to_exclude == []


def test_an_ignored_order_is_refused():
    ignored = ["Region", "Year", "Product", "Account", "Measure"]
    f = frame(orders_to_ignore=[ignored])
    verdict = f.admits(ignored)
    assert not verdict.admissible
    assert verdict.code == REASON_IGNORED_ORDER


def test_an_order_not_in_orders_to_ignore_is_admitted():
    f = frame(orders_to_ignore=[["Region", "Year", "Product", "Account", "Measure"]])
    assert f.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible


def test_the_lock_outranks_a_user_preference_in_the_reported_reason():
    # Both apply; the server constraint is the one the caller must be told about.
    moved = ["Measure", "Year", "Region", "Product", "Account"]
    f = frame(last_slot_locked=True, orders_to_ignore=[moved])
    assert f.admits(moved).code == REASON_LOCKED_SLOT


def test_a_rule_is_satisfied_when_the_dimension_is_at_the_named_position():
    f = frame(position_rules=[{"dimension": "Year", "position": 0}])
    assert f.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible


def test_a_rule_is_unsatisfied_when_the_dimension_is_elsewhere():
    f = frame(position_rules=[{"dimension": "Year", "position": 0}])
    verdict = f.admits(["Region", "Year", "Product", "Account", "Measure"])
    assert not verdict.admissible
    assert verdict.code == REASON_POSITION_RULE
    assert "must be at position 0" in verdict.reason
    assert "puts it at 1" in verdict.reason


def test_integer_positions_are_zero_based():
    # docs/advanced/dimension-position-rules.md: "position | integer | 0-based".
    # position 1 means index 1 — the second slot — not the first.
    f = frame(position_rules=[{"dimension": "Region", "position": 1}])
    assert f.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible
    assert not f.admits(["Region", "Year", "Product", "Account", "Measure"]).admissible


def test_position_zero_means_the_first_slot():
    f = frame(position_rules=[{"dimension": "Region", "position": 0}])
    assert f.admits(["Region", "Year", "Product", "Account", "Measure"]).admissible
    assert not f.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible


def test_first_and_last_name_the_end_slots():
    first = frame(position_rules=[{"dimension": "Year", "position": "first"}])
    assert first.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible
    assert not first.admits(["Region", "Year", "Product", "Account", "Measure"]).admissible

    last = frame(position_rules=[{"dimension": "Measure", "position": "last"}])
    assert last.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible
    assert not last.admits(["Measure", "Year", "Region", "Product", "Account"]).admissible


def test_every_rule_must_hold():
    f = frame(position_rules=[{"dimension": "Year", "position": 0},
                              {"dimension": "Account", "position": 3}])
    assert f.admits(["Year", "Region", "Product", "Account", "Measure"]).admissible
    # First rule holds, second does not.
    verdict = f.admits(["Year", "Region", "Account", "Product", "Measure"])
    assert not verdict.admissible
    assert "Account" in verdict.reason


@pytest.mark.parametrize("rule", [
    {"dimension": "Yaer", "position": 0},      # typo'd dimension name
    {"dimension": "Year", "position": "middle"},  # not a keyword
    {"dimension": "Year", "position": 99},     # out of range
    {"dimension": "Year", "position": -1},     # negative
    {"dimension": "Year", "position": 2.7},    # float
    {"dimension": "Year", "position": 3.0},    # float that looks like an index
    {"dimension": "Year", "position": None},
])
def test_a_rule_naming_no_slot_is_left_to_startup_validation(rule):
    # A rule that names no real slot must not quietly refuse the entire search
    # space: that would leave the greedy with nothing to evaluate and the run
    # reporting success. It is ignored here and rejected at startup, where the
    # message can name the config field. Assert EVERY order is still admitted.
    f = frame(position_rules=[rule])
    every_order = list(itertools.permutations(STORAGE))
    assert all(f.admits(list(order)).admissible for order in every_order)
    assert len(every_order) == 120


def test_required_index_resolves_positions():
    assert OrderFrame.required_index(0, 5) == 0
    assert OrderFrame.required_index(3, 5) == 3
    assert OrderFrame.required_index(4, 5) == 4
    assert OrderFrame.required_index("first", 5) == 0
    assert OrderFrame.required_index("last", 5) == 4


def test_required_index_refuses_anything_that_names_no_slot():
    # Out of range, in both directions — the reason dimension_count is a parameter.
    assert OrderFrame.required_index(5, 5) is None
    assert OrderFrame.required_index(99, 5) is None
    assert OrderFrame.required_index(-1, 5) is None
    # Floats are refused rather than truncated: 2.7 is a malformed config, not
    # a request for slot 2.
    assert OrderFrame.required_index(2.7, 5) is None
    assert OrderFrame.required_index(3.0, 5) is None
    # bool is a subclass of int; True must not resolve to slot 1.
    assert OrderFrame.required_index(True, 5) is None
    assert OrderFrame.required_index(False, 5) is None
    assert OrderFrame.required_index("middle", 5) is None
    assert OrderFrame.required_index(None, 5) is None


# --- the shape of the search space ----------------------------------------

def test_movable_dimensions_drops_the_locked_dim():
    f = frame(last_slot_locked=True)
    assert f.movable_dimensions() == ["Year", "Region", "Product", "Account"]


def test_movable_dimensions_drops_excluded_dims():
    f = frame(dimensions_to_exclude=["Region"])
    assert f.movable_dimensions() == ["Year", "Product", "Account", "Measure"]


def test_movable_dimensions_drops_both():
    f = frame(last_slot_locked=True, dimensions_to_exclude=["Region"])
    assert f.movable_dimensions() == ["Year", "Product", "Account"]


def test_reserved_positions_covers_excluded_slots_and_the_locked_slot():
    f = frame(last_slot_locked=True, dimensions_to_exclude=["Region"])
    assert f.reserved_positions() == {1, 4}


def test_reserved_positions_is_empty_with_no_lock_and_no_exclusions():
    assert frame().reserved_positions() == set()


# --- purity ----------------------------------------------------------------

def test_frame_holds_no_tm1_handle():
    # The frame is constructed from data alone; it must stay offline-testable.
    f = frame(last_slot_locked=True)
    assert not any(hasattr(f, attr) for attr in ("tm1", "cube_name"))


def test_frame_copies_its_inputs():
    order = list(STORAGE)
    excluded = ["Region"]
    f = OrderFrame(order, True, dimensions_to_exclude=excluded)
    order.append("Mutated")
    excluded.append("Product")
    assert f.storage_order == STORAGE
    assert f.movable_dimensions() == ["Year", "Product", "Account"]
