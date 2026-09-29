"""`dimension_position_rules`: pre-application and startup validation.

Pre-application — seat the named dimensions and search what is left — is
implemented *in the frame*, so a pinned dimension is simply another immovable
one alongside the locked and the excluded dims; there is no second list
anywhere. Validation turns every invalid rule into the error the documentation
promises.

Offline, no fake.
"""
import pytest

from optimuspy.core import _validate_position_rules
from optimuspy.order_frame import OrderFrame, REASON_POSITION_RULE
from tests.conftest import install_offline_measurements
from tests.test_fold_a import make_main_executor

STORAGE = ["Year", "Region", "Product", "Account", "Measure"]
CARD = {"Year": 12, "Region": 80, "Product": 5000, "Account": 900, "Measure": 4}


def frame(rules, **kwargs):
    locked = kwargs.pop("last_slot_locked", False)
    return OrderFrame(STORAGE, locked, position_rules=rules, **kwargs)


# --- pre-application -------------------------------------------------------

def test_a_pinned_dimension_is_seated_at_its_slot():
    f = frame([{"dimension": "Product", "position": 0}])
    assert f.pre_applied_order() == ["Product", "Year", "Region", "Account", "Measure"]


def test_the_unpinned_dimensions_keep_their_storage_sequence():
    # Pre-application is not a reordering of everything: it moves what the rules
    # name and leaves the rest in the order the cube already had, so the greedy
    # starts from the cube rather than from an arbitrary permutation.
    f = frame([{"dimension": "Account", "position": 1}])
    assert f.pre_applied_order() == ["Year", "Account", "Region", "Product", "Measure"]


def test_several_rules_are_all_seated():
    f = frame([{"dimension": "Product", "position": 0},
               {"dimension": "Year", "position": 2}])
    assert f.pre_applied_order() == ["Product", "Region", "Year", "Account", "Measure"]


def test_no_rules_leaves_the_storage_order_untouched():
    assert frame([]).pre_applied_order() == STORAGE


def test_first_and_last_are_accepted_as_slots():
    f = frame([{"dimension": "Account", "position": "first"}])
    assert f.pre_applied_order()[0] == "Account"


def test_an_unresolvable_rule_seats_nothing():
    # It must not silently reserve a slot: a reserved slot nobody asked for
    # can narrow the search to zero orders and still report success.
    f = frame([{"dimension": "Nope", "position": 0},
               {"dimension": "Year", "position": "middle"}])
    assert f.pinned_positions == {}
    assert f.pre_applied_order() == STORAGE
    assert f.reserved_positions() == set()


# --- one fact, one place ---------------------------------------------------

def test_a_pinned_dimension_is_not_movable():
    f = frame([{"dimension": "Product", "position": 0}])
    assert "Product" not in f.movable_dimensions()


def test_a_pinned_slot_is_reserved():
    f = frame([{"dimension": "Product", "position": 0}])
    assert 0 in f.reserved_positions()


def test_pinned_locked_and_excluded_are_all_just_immovable():
    f = frame([{"dimension": "Product", "position": 0}],
              last_slot_locked=True, dimensions_to_exclude=["Region"])
    # Pre-applied: Product, Year, Region, Account, Measure
    assert f.pre_applied_order() == ["Product", "Year", "Region", "Account", "Measure"]
    assert f.movable_dimensions() == ["Year", "Account"]
    assert f.reserved_positions() == {0, 2, 4}


def test_reserved_positions_locate_the_excluded_dim_in_the_pre_applied_order():
    # Region sits at index 1 in storage and index 2 once Product is seated at 0.
    # The search runs over the pre-applied order, so that is the index that must
    # be reserved — reserving 1 would freeze the wrong slot.
    f = frame([{"dimension": "Product", "position": 0}], dimensions_to_exclude=["Region"])
    assert f.pre_applied_order().index("Region") == 2
    assert 2 in f.reserved_positions()


def test_admits_still_refuses_an_order_that_moves_a_pinned_dim():
    f = frame([{"dimension": "Product", "position": 0}])
    verdict = f.admits(["Year", "Product", "Region", "Account", "Measure"])
    assert not verdict.admissible
    assert verdict.code == REASON_POSITION_RULE
    assert "must be at position 0" in verdict.reason


# --- the folds start from the pre-applied order ----------------------------

def _run(fast, rules, **kwargs):
    ex = make_main_executor(STORAGE, CARD, fast=fast, position_rules=rules, **kwargs)
    log = []
    install_offline_measurements(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    ex.execute()
    return ex, log


@pytest.mark.parametrize("fast", [False, True])
def test_no_evaluated_order_moves_a_pinned_dimension(fast):
    rules = [{"dimension": "Product", "position": 0}]
    ex, log = _run(fast, rules)
    assert log, "nothing was evaluated — the test would prove nothing"
    assert all(order[0] == "Product" for order in log)
    # Pre-application means the constraint is structural, not enforced by
    # refusing candidate after candidate.
    assert ex.skipped_orders.get(REASON_POSITION_RULE) is None


@pytest.mark.parametrize("fast", [False, True])
def test_a_rule_survives_a_lock_on_the_same_cube(fast):
    rules = [{"dimension": "Product", "position": 0}]
    ex, log = _run(fast, rules, last_slot_locked=True)
    assert log
    assert all(order[0] == "Product" and order[-1] == "Measure" for order in log)


def test_fold_a_measures_the_pre_applied_order_first():
    # The measured original order is no longer the order the fold stands on, so
    # every position's "keep what is here" option would otherwise carry a RAM
    # figure for a different order.
    rules = [{"dimension": "Product", "position": 0}]
    _, log = _run(False, rules)
    assert log[0] == ["Product", "Year", "Region", "Account", "Measure"]


def test_fold_a_does_not_re_measure_an_order_pre_application_did_not_change():
    # A rule naming where the dimension already sits seats nothing, so the fold
    # is standing on the order that was already measured. Re-applying it would
    # be a reorder that tests a permutation the report already has.
    rules = [{"dimension": "Year", "position": 0}]
    _, log = _run(False, rules)
    assert log[0] != STORAGE


def test_fold_b_seeds_the_pinned_dimension_at_its_slot():
    rules = [{"dimension": "Product", "position": 0}]
    _, log = _run(True, rules)
    assert log[0][0] == "Product"
    # The seed is still cardinality-ascending over the slots that are free.
    free = log[0][1:]
    assert free == sorted(free, key=lambda d: CARD[d])


# --- startup validation ----------------------------------------------------

@pytest.mark.parametrize("rule, fragment", [
    ({"dimension": "Yaer", "position": 0}, "is not a dimension of this cube"),
    ({"dimension": "Year", "position": "middle"}, "names no slot"),
    ({"dimension": "Year", "position": None}, "names no slot"),
    ({"dimension": "Year", "position": True}, "names no slot"),
    ({"dimension": "Year", "position": 2.7}, "names no slot"),
    ({"dimension": "Year", "position": 99}, "out of range"),
    ({"dimension": "Year", "position": -1}, "out of range"),
    ({"dimension": "Year", "position": "99"}, "out of range"),
])
def test_a_rule_that_names_no_layout_is_reported(rule, fragment):
    problems = frame([rule]).validate_position_rules()
    assert len(problems) == 1
    assert fragment in problems[0][1]


@pytest.mark.parametrize("position, intended", [("3", 3), (3.0, 3), ("0", 0)])
def test_a_type_slip_is_not_reported_as_a_typo(position, intended):
    # "3" and 3.0 name a slot unambiguously and are refused on a documentation
    # technicality. Telling the user their position is unreadable, at a value
    # they can plainly see is a number, reads as an accusation of a typo.
    problems = frame([{"dimension": "Year", "position": position}]).validate_position_rules()
    assert len(problems) == 1
    message = problems[0][1]
    assert f"write {intended}, not {position!r}" in message
    assert "names no slot" not in message


def test_two_rules_on_one_dimension_are_reported():
    problems = frame([{"dimension": "Year", "position": 0},
                      {"dimension": "Year", "position": 2}]).validate_position_rules()
    assert [index for index, _ in problems] == [1]
    assert "already has a rule" in problems[0][1]


def test_two_rules_on_one_position_are_reported():
    # docs: "Multiple rules may target different dimensions; they cannot target
    # the same position."
    problems = frame([{"dimension": "Year", "position": 0},
                      {"dimension": "Region", "position": 0}]).validate_position_rules()
    assert [index for index, _ in problems] == [1]
    assert "already taken by" in problems[0][1]


def test_a_dimension_cannot_be_both_pinned_and_excluded():
    problems = frame([{"dimension": "Region", "position": 0}],
                     dimensions_to_exclude=["Region"]).validate_position_rules()
    assert len(problems) == 1
    assert "dimensions_to_exclude" in problems[0][1]


def test_pinning_the_locked_dimension_elsewhere_is_reported():
    problems = frame([{"dimension": "Measure", "position": 1}],
                     last_slot_locked=True).validate_position_rules()
    assert len(problems) == 1
    assert "string elements" in problems[0][1]
    assert "locked to position 4" in problems[0][1]


def test_giving_the_locked_slot_to_another_dimension_is_reported():
    problems = frame([{"dimension": "Year", "position": 4}],
                     last_slot_locked=True).validate_position_rules()
    assert len(problems) == 1
    assert "'Measure'" in problems[0][1]
    assert "never moves" in problems[0][1]


def test_a_rule_on_the_last_slot_is_fine_without_a_lock():
    assert frame([{"dimension": "Year", "position": 4}]).validate_position_rules() == []


def test_a_satisfiable_rule_set_reports_nothing():
    assert frame([{"dimension": "Year", "position": 0},
                  {"dimension": "Measure", "position": "last"}],
                 last_slot_locked=True).validate_position_rules() == []


def test_every_problem_is_reported_not_just_the_first():
    problems = frame([{"dimension": "Yaer", "position": 0},
                      {"dimension": "Region", "position": 1},
                      {"dimension": "Year", "position": "middle"}]).validate_position_rules()
    assert [index for index, _ in problems] == [0, 2]


# --- what the operator sees ------------------------------------------------

def test_core_raises_naming_the_cube_and_every_bad_rule():
    f = frame([{"dimension": "Yaer", "position": 0},
               {"dimension": "Year", "position": 99}])
    with pytest.raises(ValueError) as excinfo:
        _validate_position_rules(f, "Sales")
    message = str(excinfo.value)
    assert "Sales" in message
    assert "dimension_position_rules[0]" in message
    assert "dimension_position_rules[1]" in message


def test_core_is_silent_when_the_rules_are_good():
    _validate_position_rules(frame([{"dimension": "Year", "position": 0}]), "Sales")
