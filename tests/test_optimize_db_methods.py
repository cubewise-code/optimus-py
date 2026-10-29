"""Optimize DB's per-cube method: leaf count by default, last slot only on request.

Leaf count applies the leaf-count-ascending order in one unmeasured reorder.
Last slot only measures every dimension in the last free slot and keeps the
winner — the case where the densest dimension is not the largest. The
measurement itself is the single-cube optimizer's job and is stood in for here
by `_optimize_last_slot`; what is under test is how Optimize DB plans, runs,
records and resumes such a cube.
"""
import json

import pytest

from optimuspy import optimize_db as odb
from optimuspy.executors import OptimizationCancelled
from tests.test_optimize_db_executor import (  # noqa: F401 — fixtures
    GB, fast_reconnect, frozen_clock, make_plan, run, three_cube_server)
from tests.test_optimize_db_planner import cube, options


# --- planning ------------------------------------------------------------------

def test_every_cube_defaults_to_leaf_count():
    plan = odb.build_plan("srv", "p1", options(), [cube("Sales", 1, ["A", "B", "C"],
                                                        leaves={"A": 300, "B": 20, "C": 5})],
                          1 * GB, [])
    assert [c["method"] for c in plan["cubes"]] == ["leaf_count"]


def test_last_slot_cubes_picks_the_method_by_name_or_pattern():
    records = [cube(name, 1, ["A", "B", "C"], leaves={"A": 300, "B": 20, "C": 5})
               for name in ("SITE.2150.Total", "Sales", "Other")]
    plan = odb.build_plan("srv", "p1", options(last_slot_cubes=["site.*", "Sales"]),
                          records, 3 * GB, [])
    assert {c["cube"]: c["method"] for c in plan["cubes"]} == {
        "SITE.2150.Total": "last_slot", "Sales": "last_slot", "Other": "leaf_count"}
    # The leaf-count order is kept, so the choice can be switched back.
    assert all(c["target_order"] == ["C", "B", "A"] for c in plan["cubes"])


def test_a_cube_already_in_leaf_count_order_still_measures_its_last_slot():
    # Being smallest-to-largest says nothing about which dimension is densest.
    record = cube("Sales", 1, ["C", "B", "A"], leaves={"A": 300, "B": 20, "C": 5})
    plain = odb.build_plan("srv", "p1", options(), [record], 1 * GB, [])
    asked = odb.build_plan("srv", "p1", options(last_slot_cubes=["Sales"]), [record], 1 * GB, [])
    assert plain["cubes"] == [] and plain["skipped"][0]["reason"] == "already_in_target_order"
    assert [c["method"] for c in asked["cubes"]] == ["last_slot"]


def test_last_slot_cubes_must_be_a_list_of_names():
    with pytest.raises(ValueError, match="last_slot_cubes"):
        odb.validate_db_config({"instance": "srv", "last_slot_cubes": "Sales"})


def test_the_operators_choice_is_applied_to_the_plan():
    plan = {"plan_id": "p1", "cubes": [{"cube": "Sales", "method": "leaf_count"},
                                       {"cube": "Costs", "method": "leaf_count"}]}
    odb.apply_methods(plan, {"Sales": "last_slot"})
    assert [c["method"] for c in plan["cubes"]] == ["last_slot", "leaf_count"]


@pytest.mark.parametrize("methods, fragment", [
    ({"Nope": "last_slot"}, "is not a cube in plan"),
    ({"Sales": "fast"}, "is not a method"),
])
def test_a_choice_the_plan_cannot_take_is_refused(methods, fragment):
    plan = {"plan_id": "p1", "cubes": [{"cube": "Sales", "method": "leaf_count"}]}
    with pytest.raises(ValueError, match=fragment):
        odb.apply_methods(plan, methods)


def test_a_plan_written_before_methods_reorders_by_leaf_count():
    assert odb.plan_method({"cube": "Sales", "target_order": ["A"]}) == "leaf_count"


# --- the call into the single-cube optimizer ------------------------------------

@pytest.mark.parametrize("locked, slot", [(False, 3), (True, 2)])
def test_the_optimizer_is_pointed_at_the_last_free_slot(monkeypatch, locked, slot):
    # `optimize_position` is 1-based; a 0-based index here measured the slot
    # before the last on a live server.
    order = ["A", "B", "C", "M"]
    seen = {}

    class Cubes:
        def get_storage_dimension_order(self, cube_name):
            return list(order)

    class Tm1:
        cubes = Cubes()

    def fake_optimize(tm1, cube_name, instance, *args, **kwargs):
        seen.update(kwargs)
        kwargs["outcome"].update(applied_order=list(order))
        return True

    monkeypatch.setattr(odb.core, "is_dimension_only_numeric", lambda tm1, dim: not locked)
    monkeypatch.setattr(odb.core, "_execute_optimize_mode", fake_optimize)

    assert odb._optimize_last_slot(Tm1(), "srv", "Sales", None, False) is not None
    assert odb.core.resolve_position(seen["optimize_position"], len(order)) == slot
    assert seen["cube_config"]["optimize_position"] == seen["optimize_position"]


# --- running -------------------------------------------------------------------

def _last_slot_plan(server, cubes=("Medium",)):
    plan = make_plan(server)
    odb.apply_methods(plan, {c: "last_slot" for c in cubes})
    return plan


def _stand_in(monkeypatch, server, *, outcome=None, raises=None):
    """Replace the single-cube optimizer; record which cubes it was asked to run."""
    calls = []

    def fake(tm1, instance, cube_name, cancel_event, is_v12):
        calls.append(cube_name)
        if raises:
            raise raises
        if outcome is None:
            return None
        server.orders[cube_name] = list(outcome["applied_order"])
        return dict(outcome)

    monkeypatch.setattr(odb, "_optimize_last_slot", fake)
    return calls


MEASURED = {"original_order": ["A", "B", "C"], "original_ram": 10 * GB,
            "applied_order": ["C", "A", "B"], "applied_ram": 2.2 * GB,
            "measured": 2, "report": "srv/srv_Medium_2026-10-14_10-00-00.html"}


def test_a_last_slot_cube_is_measured_and_its_winner_recorded(tmp_path, frozen_clock, monkeypatch):
    server = three_cube_server()
    frozen_clock["server"] = server
    calls = _stand_in(monkeypatch, server, outcome=MEASURED)

    result, _ = run(server, _last_slot_plan(server), tmp_path)

    assert calls == ["Medium"]
    # The other cubes still get their one leaf-count reorder; Medium gets none from it.
    assert [c for c, _ in server.reorders] == ["Small", "Big"]
    medium = result["cubes"]["Medium"]
    assert medium["status"] == "done"
    assert medium["method"] == "last_slot"
    assert medium["pct_change"] == pytest.approx(-78.0)
    assert medium["target_order"] == ["C", "A", "B"]
    assert medium["report"] == MEASURED["report"]
    assert result["totals"]["bytes_saved"] == pytest.approx(0.1 * 1 * GB + 0.78 * 10 * GB + 0.1 * 100 * GB)


def test_a_last_slot_cube_does_not_feed_the_throughput_estimate(tmp_path, frozen_clock, monkeypatch):
    # The estimate times one reorder per cube; a last-slot cube runs one per dimension.
    server = three_cube_server()
    frozen_clock["server"] = server
    _stand_in(monkeypatch, server, outcome=MEASURED)

    result, _ = run(server, _last_slot_plan(server), tmp_path)

    assert [b for b, _ in result["samples"]] == [1 * GB, 100 * GB]


def test_a_last_slot_cube_that_does_not_finish_is_failed_and_the_run_goes_on(tmp_path, frozen_clock, monkeypatch):
    server = three_cube_server()
    frozen_clock["server"] = server
    _stand_in(monkeypatch, server, outcome=None)

    result, _ = run(server, _last_slot_plan(server), tmp_path)

    assert result["cubes"]["Medium"]["status"] == "failed"
    assert result["cubes"]["Big"]["status"] == "done"
    assert result["status"] == "completed"


def test_stopping_during_a_last_slot_cube_leaves_it_pending(tmp_path, frozen_clock, monkeypatch):
    server = three_cube_server()
    frozen_clock["server"] = server
    _stand_in(monkeypatch, server, raises=OptimizationCancelled("stop"))

    result, _ = run(server, _last_slot_plan(server), tmp_path)

    assert result["status"] == "cancelled"
    assert result["cubes"]["Medium"]["status"] == "pending"
    assert result["cubes"]["Big"]["status"] == "pending"
    assert "Big" not in [c for c, _ in server.reorders]


def test_a_new_run_records_the_method_and_no_target_for_a_last_slot_cube(tmp_path, frozen_clock):
    server = three_cube_server()
    state = odb.new_run(_last_slot_plan(server), tmp_path)
    assert state["cubes"]["Medium"]["method"] == "last_slot"
    assert state["cubes"]["Medium"]["target_order"] is None
    assert state["cubes"]["Small"]["method"] == "leaf_count"
    assert state["cubes"]["Small"]["target_order"] == ["C", "B", "A"]


# --- resuming ------------------------------------------------------------------

def test_resume_continues_a_last_slot_cube_that_was_interrupted(tmp_path, frozen_clock):
    # Its sweep keeps its own checkpoint, so it is requeued, never "recovered"
    # against a leaf-count target it was not heading for.
    server = three_cube_server()
    plan = _last_slot_plan(server)
    state = odb.new_run(plan, tmp_path)
    state["cubes"]["Medium"].update(status="in_flight", original_order=["A", "B", "C"])
    server.orders["Medium"] = list(plan["cubes"][1]["target_order"])

    assert odb.prepare_resume(server.connect(), plan, state) == 1
    assert state["cubes"]["Medium"]["status"] == "pending"


def test_resume_checks_a_finished_last_slot_cube_against_the_order_it_applied(tmp_path, frozen_clock):
    server = three_cube_server()
    plan = _last_slot_plan(server)
    state = odb.new_run(plan, tmp_path)
    state["cubes"]["Medium"].update(status="done", pct_change=-78.0, target_order=["C", "A", "B"])
    server.orders["Medium"] = ["C", "A", "B"]

    assert odb.prepare_resume(server.connect(), plan, state) == 0
    assert state["cubes"]["Medium"]["status"] == "done"


# --- reporting -----------------------------------------------------------------

def test_the_plan_and_the_report_name_the_method(tmp_path, frozen_clock, monkeypatch):
    server = three_cube_server()
    frozen_clock["server"] = server
    _stand_in(monkeypatch, server, outcome=MEASURED)
    plan = _last_slot_plan(server)

    text = odb.format_plan(plan)
    assert "Last slot only" in text and "Leaf count" in text

    result, _ = run(server, plan, tmp_path)
    report = tmp_path / "report.html"
    odb.write_report(plan, result, report)
    page = report.read_text(encoding="utf-8")
    assert '"method": "Last slot only"' in page
    assert json.dumps(MEASURED["report"]) in page
