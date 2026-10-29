"""Execution behaviour of Optimize DB against a scripted TM1 service.

Covers the paths that only appear at runtime: the wall-clock stop, reverting a
regression, the chore lifecycle, and recovering a reorder whose response was
lost to a dropped connection.
"""
import json
import logging
import re
import time
from pathlib import Path

import pytest

from optimuspy import optimize_db as odb

GB = 1024 ** 3


class FakeChore:
    def __init__(self, name, active):
        self.name = name
        self.active = active


class FakeChores:
    def __init__(self, chores):
        self._chores = chores
        self.calls = []

    def get_all(self):
        return list(self._chores)

    def activate(self, name):
        self.calls.append(("activate", name))

    def deactivate(self, name):
        self.calls.append(("deactivate", name))


class FakeCubes:
    def __init__(self, server):
        self.server = server

    def get_storage_dimension_order(self, cube_name):
        if self.server.dead:
            raise ConnectionError("connection dropped")
        behaviour = self.server.behaviour.get(cube_name, {})
        if behaviour.get("probe_raises_once"):
            # Something the module never anticipated — a TM1py payload change,
            # not a dropped connection. Nothing in `_reorder_cube` catches it.
            behaviour["probe_raises_once"] = False
            raise KeyError("unexpected TM1py response shape")
        return list(self.server.orders[cube_name])

    def update_storage_dimension_order(self, cube_name, order):
        self.server.reorders.append((cube_name, list(order)))
        behaviour = self.server.behaviour.get(cube_name, {})
        duration = behaviour.get("duration", 1.0)
        self.server.clock[0] += duration
        if behaviour.get("raise_once"):
            behaviour["raise_once"] = False
            if behaviour.get("applies_anyway"):
                self.server.orders[cube_name] = list(order)
            raise ConnectionError("connection dropped mid-reorder")
        if behaviour.get("fail"):
            raise RuntimeError("cube is locked")
        self.server.orders[cube_name] = list(order)
        return behaviour.get("pct", -10.0)


class FakeMetrics:
    def __init__(self, server):
        self.server = server

    def by_cube(self, cube=None):
        names = [cube] if cube else list(self.server.ram)
        return [{"Cube": n, "Metric": "cube_memory_used",
                 "Value": self.server.ram[n], "Unit": "B"} for n in names]

    def get_performance_monitor_state(self):
        return True


class FakeTM1:
    def __init__(self, server):
        self.server = server
        self.cubes = FakeCubes(server)
        self.metrics = FakeMetrics(server)
        self.chores = server.chores
        self.logged_out = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def logout(self):
        self.logged_out = True


class FakeServer:
    """Scripted TM1: per-cube orders, RAM, and reorder behaviour."""

    def __init__(self, orders, ram, behaviour=None, chores=()):
        self.orders = {k: list(v) for k, v in orders.items()}
        self.ram = dict(ram)
        self.behaviour = behaviour or {}
        self.chores = FakeChores(list(chores))
        self.reorders = []
        self.dead = False
        self.clock = [1_000_000.0]
        self.connections = 0

    def connect(self):
        self.connections += 1
        if self.dead:
            raise ConnectionError("instance unreachable")
        return FakeTM1(self)


@pytest.fixture(autouse=True)
def fast_reconnect(monkeypatch):
    monkeypatch.setattr(odb, "RECONNECT_BACKOFF_SECONDS", (0, 0, 0))


@pytest.fixture
def frozen_clock(monkeypatch):
    """A clock the fake server advances as reorders 'run'."""
    holder = {"server": None}

    def now():
        return holder["server"].clock[0] if holder["server"] else 1_000_000.0

    monkeypatch.setattr(odb.time, "time", now)
    monkeypatch.setattr(odb.time, "sleep", lambda s: None)
    return holder


def make_plan(server, order="asc", **option_overrides):
    options = odb.resolve_options({"instance": "srv", **option_overrides})
    options["order"] = order
    records = [
        {"cube": name, "ram_bytes": server.ram[name],
         "storage_order": list(server.orders[name]),
         "dimensions": {d: {"name": d, "leaf_elements": leaf, "has_strings": False}
                        for leaf, d in enumerate(reversed(server.orders[name]), 1)}}
        for name in server.orders
    ]
    return odb.build_plan("srv", "p1", options, records,
                          sum(server.ram.values()), server.chores and
                          [c.name for c in server.chores.get_all() if c.active])


def run(server, plan, tmp_path, **kwargs):
    run_state = odb.new_run(plan, tmp_path)
    run_state["is_v12"] = False
    path = tmp_path / f"{odb.RUN_PREFIX}{plan['plan_id']}.json"
    return odb.execute_plan(server.connect, plan, run_state,
                            lambda: odb.write_json(path, run_state), **kwargs), path


def three_cube_server(**behaviour):
    return FakeServer(
        orders={"Small": ["A", "B", "C"], "Medium": ["A", "B", "C"], "Big": ["A", "B", "C"]},
        ram={"Small": 1 * GB, "Medium": 10 * GB, "Big": 100 * GB},
        behaviour=behaviour,
    )


# --- happy path ------------------------------------------------------------

def test_every_cube_is_reordered_smallest_first(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    result, path = run(server, make_plan(server), tmp_path)

    assert [c for c, _ in server.reorders] == ["Small", "Medium", "Big"]
    assert result["status"] == "completed"
    assert result["totals"]["cubes_reordered"] == 3
    # -10% on each cube, against the plan-time RAM.
    assert result["totals"]["bytes_saved"] == pytest.approx(111 * GB * 0.1)
    assert json.loads(path.read_text())["status"] == "completed"


def test_target_order_is_applied(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    run(server, make_plan(server), tmp_path)
    # Leaf counts descend with position in the fixture, so C is the smallest.
    assert server.orders["Small"] == ["C", "B", "A"]


def test_cube_already_in_target_order_is_not_rebuilt(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    server.orders["Medium"] = list(plan["cubes"][1]["target_order"])

    result, _ = run(server, plan, tmp_path)
    assert "Medium" not in [c for c, _ in server.reorders]
    assert result["cubes"]["Medium"]["status"] == "skipped"


# --- budget ----------------------------------------------------------------

def test_run_stops_before_a_cube_that_would_overrun_the_deadline(tmp_path, frozen_clock):
    server = three_cube_server(
        Small={"duration": 100.0}, Medium={"duration": 1000.0}, Big={"duration": 10000.0})
    frozen_clock["server"] = server
    plan = make_plan(server)
    # 1100s of work fits; Big is predicted at 100 GB / (10 GB per 1000s) = 10000s.
    plan["options"]["time_limit_hours"] = 2000 / 3600

    result, _ = run(server, plan, tmp_path)
    assert [c for c, _ in server.reorders] == ["Small", "Medium"]
    assert result["status"] == "stopped_time_limit"
    assert result["cubes"]["Big"]["status"] == "pending"
    assert result["totals"]["cubes_pending"] == 1


def test_a_started_cube_is_allowed_to_overshoot_the_limit(tmp_path, frozen_clock):
    """The budget is a between-cubes gate; an in-flight rebuild cannot be aborted."""
    server = three_cube_server(Small={"duration": 100000.0})
    frozen_clock["server"] = server
    plan = make_plan(server)
    plan["options"]["time_limit_hours"] = 0.5

    result, _ = run(server, plan, tmp_path)
    assert server.reorders[0][0] == "Small"
    assert result["cubes"]["Small"]["status"] == "done"
    assert result["totals"]["elapsed_s"] > 0.5 * 3600
    assert result["status"] == "stopped_time_limit"


# --- regressions -----------------------------------------------------------

def test_a_cube_the_heuristic_made_worse_is_reverted(tmp_path, frozen_clock):
    server = three_cube_server(Medium={"pct": 4.2})
    frozen_clock["server"] = server
    original = list(server.orders["Medium"])

    result, _ = run(server, make_plan(server), tmp_path)
    assert server.orders["Medium"] == original
    assert result["cubes"]["Medium"]["status"] == "reverted"
    assert result["totals"]["cubes_reverted"] == 1
    # A reverted cube contributes nothing to the reported saving.
    assert result["totals"]["bytes_saved"] == pytest.approx(101 * GB * 0.1)


def test_regression_is_kept_when_reverting_is_switched_off(tmp_path, frozen_clock):
    server = three_cube_server(Medium={"pct": 4.2})
    frozen_clock["server"] = server
    plan = make_plan(server, revert_on_regression=False)

    result, _ = run(server, plan, tmp_path)
    assert result["cubes"]["Medium"]["status"] == "done"
    assert server.orders["Medium"] == plan["cubes"][1]["target_order"]


# --- dropped connection ----------------------------------------------------

def test_reorder_that_landed_but_lost_its_response_is_measured_instead(tmp_path, frozen_clock):
    server = three_cube_server(Medium={"raise_once": True, "applies_anyway": True})
    frozen_clock["server"] = server
    plan = make_plan(server)
    # The server-returned % is gone; the saving has to come from a RAM read.
    server.ram["Medium"] = 8 * GB

    result, _ = run(server, plan, tmp_path)
    state = result["cubes"]["Medium"]
    assert state["status"] == "done"
    assert state["derived"] is True
    assert state["pct_change"] == pytest.approx(-20.0)
    assert result["status"] == "completed"


def test_derived_result_does_not_pollute_the_throughput_model(tmp_path, frozen_clock):
    server = three_cube_server(Small={"raise_once": True, "applies_anyway": True})
    frozen_clock["server"] = server
    result, _ = run(server, make_plan(server), tmp_path)
    assert [s[0] for s in result["samples"]] == [10 * GB, 100 * GB]


def test_reorder_that_never_landed_is_recorded_as_failed(tmp_path, frozen_clock):
    server = three_cube_server(Medium={"raise_once": True, "applies_anyway": False})
    frozen_clock["server"] = server
    result, _ = run(server, make_plan(server), tmp_path)
    assert result["cubes"]["Medium"]["status"] == "failed"
    assert result["cubes"]["Big"]["status"] == "done"  # the run continues
    assert result["totals"]["cubes_failed"] == 1


def test_run_aborts_after_consecutive_failures(tmp_path, frozen_clock):
    server = FakeServer(
        orders={f"C{i}": ["A", "B", "C"] for i in range(5)},
        ram={f"C{i}": (i + 1) * GB for i in range(5)},
        behaviour={f"C{i}": {"fail": True} for i in range(5)},
    )
    frozen_clock["server"] = server
    plan = make_plan(server, max_consecutive_failures=2, min_cube_mb=0)

    result, _ = run(server, plan, tmp_path)
    assert result["status"] == "failed"
    assert result["totals"]["cubes_failed"] == 2
    assert result["totals"]["cubes_pending"] == 3


def test_unreachable_server_fails_the_run_rather_than_grinding_on(tmp_path, frozen_clock):
    server = three_cube_server(Small={"raise_once": True})
    frozen_clock["server"] = server

    def connect_then_die():
        if server.connections >= 1:
            server.dead = True
        return server.connect()

    server_connect = server.connect
    server.connect = lambda: connect_then_die() if server.connections else server_connect()

    result, _ = run(server, make_plan(server), tmp_path)
    assert result["status"] == "failed"
    assert "unreachable" in result["error"]


def test_instance_that_is_already_down_is_recorded_as_a_failed_run(tmp_path, frozen_clock):
    """An unattended sweep must leave an artifact, not a traceback."""
    server = three_cube_server()
    frozen_clock["server"] = server
    server.dead = True

    result, path = run(server, make_plan(server), tmp_path)
    assert result["status"] == "failed"
    assert "unreachable" in result["error"]
    assert json.loads(path.read_text())["status"] == "failed"
    assert server.reorders == []


# --- chores ----------------------------------------------------------------

def test_active_chores_are_disabled_and_restored(tmp_path, frozen_clock):
    server = three_cube_server()
    server.chores = FakeChores([FakeChore("Nightly", True), FakeChore("Off", False)])
    frozen_clock["server"] = server
    plan = make_plan(server, disable_active_chores=True)
    plan["active_chores"] = ["Nightly"]

    result, _ = run(server, plan, tmp_path)
    assert server.chores.calls == [("deactivate", "Nightly"), ("activate", "Nightly")]
    assert result["chores"]["state"] == "restored"


def test_chores_disabled_are_the_ones_active_now_not_the_ones_in_the_plan(tmp_path, frozen_clock):
    """A saved plan can run days later; a chore switched off since must stay off."""
    server = three_cube_server()
    server.chores = FakeChores([FakeChore("Still On", True), FakeChore("Since Disabled", False)])
    frozen_clock["server"] = server
    plan = make_plan(server, disable_active_chores=True)
    plan["active_chores"] = ["Still On", "Since Disabled"]

    result, _ = run(server, plan, tmp_path)
    assert result["chores"]["deactivated"] == ["Still On"]
    assert ("activate", "Since Disabled") not in server.chores.calls


def test_chores_are_restored_even_when_the_run_stops_early(tmp_path, frozen_clock):
    server = three_cube_server(Small={"duration": 100000.0})
    server.chores = FakeChores([FakeChore("Nightly", True)])
    frozen_clock["server"] = server
    plan = make_plan(server, disable_active_chores=True)
    plan["active_chores"] = ["Nightly"]
    plan["options"]["time_limit_hours"] = 0.5

    result, _ = run(server, plan, tmp_path)
    assert result["status"] == "stopped_time_limit"
    assert ("activate", "Nightly") in server.chores.calls


def test_disabled_chores_are_recorded_before_the_first_deactivate(tmp_path, frozen_clock):
    """The artifact is the only route back, so it must precede the side effect."""
    server = three_cube_server()
    server.chores = FakeChores([FakeChore("Nightly", True)])
    frozen_clock["server"] = server
    plan = make_plan(server, disable_active_chores=True)
    plan["active_chores"] = ["Nightly"]

    state = odb.new_run(plan, tmp_path)
    seen = []
    odb.disable_chores(server.connect(), state, ["Nightly"],
                       lambda: seen.append(json.loads(json.dumps(state["chores"]))))
    assert seen[0] == {"state": "disabled", "deactivated": ["Nightly"]}


def test_restore_chores_for_plan_recovers_a_crashed_run(tmp_path, frozen_clock):
    server = three_cube_server()
    server.chores = FakeChores([FakeChore("Nightly", True)])
    frozen_clock["server"] = server
    crashed = {"plan_id": "p1", "instance": "srv", "status": "running",
               "started_at": time.time(),
               "chores": {"state": "disabled", "deactivated": ["Nightly", "Weekly"]},
               "cubes": {}}
    path = tmp_path / "srv" / f"{odb.RUN_PREFIX}p1.json"
    odb.write_json(path, crashed)

    restored = odb.restore_chores_for_plan(server.connect, "p1", tmp_path)
    assert restored == ["Nightly", "Weekly"]
    assert json.loads(path.read_text())["chores"]["state"] == "restored"
    assert odb.list_runs(tmp_path)[0]["chores_pending_restore"] is False


def test_list_runs_flags_a_run_whose_chores_are_still_disabled(tmp_path):
    odb.write_json(tmp_path / "srv" / f"{odb.RUN_PREFIX}p9.json",
                   {"plan_id": "p9", "instance": "srv", "status": "failed",
                    "started_at": 1.0, "chores": {"state": "disabled", "deactivated": ["N"]},
                    "cubes": {}})
    assert odb.list_runs(tmp_path)[0]["chores_pending_restore"] is True


# --- cancel and resume -----------------------------------------------------

class Flag:
    def __init__(self):
        self.flag = False

    def is_set(self):
        return self.flag


def test_cancel_stops_at_the_next_cube_boundary(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    cancel = Flag()

    original = odb._reorder_cube

    def stop_after_first(*args, **kwargs):
        cancel.flag = True
        return original(*args, **kwargs)

    odb._reorder_cube = stop_after_first
    try:
        result, _ = run(server, make_plan(server), tmp_path, cancel_event=cancel)
    finally:
        odb._reorder_cube = original

    assert result["status"] == "cancelled"
    assert len(server.reorders) == 1


def test_resume_requeues_a_cube_the_server_no_longer_reflects(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    state = odb.new_run(plan, tmp_path)
    state["cubes"]["Small"].update(status="done", pct_change=-5.0)
    state["cubes"]["Medium"].update(status="done", pct_change=-5.0)
    server.orders["Small"] = list(plan["cubes"][0]["target_order"])  # really applied
    # 'Medium' was never persisted — the server still shows the original order.

    reset = odb.prepare_resume(server.connect(), plan, state)
    assert reset == 1
    assert state["cubes"]["Small"]["status"] == "done"
    assert state["cubes"]["Medium"]["status"] == "pending"


def test_cube_mid_rebuild_is_recorded_as_in_flight_before_the_reorder_is_sent(tmp_path, frozen_clock):
    """The artifact has to name the cube that was rebuilding when the lights went out."""
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    state = odb.new_run(plan, tmp_path)
    path = tmp_path / "run.json"
    snapshots = []

    def save():
        odb.write_json(path, state)
        snapshots.append(json.loads(path.read_text())["cubes"]["Small"]["status"])

    odb._reorder_cube(server.connect(), server.connect, "Small", plan["cubes"][0],
                      state["cubes"]["Small"], plan["options"], False, save)
    assert snapshots[0] == "in_flight"


def test_resume_derives_the_saving_for_a_reorder_that_landed_without_a_response(tmp_path, frozen_clock):
    """The dropped-connection case across a process death — the % is gone, so measure."""
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    state = odb.new_run(plan, tmp_path)
    entry = plan["cubes"][1]  # Medium: 10 GB before the reorder
    state["cubes"]["Medium"].update(status="in_flight",
                                    original_order=list(server.orders["Medium"]))
    server.orders["Medium"] = list(entry["target_order"])  # the reorder did land
    server.ram["Medium"] = 7 * GB

    assert odb.prepare_resume(server.connect(), plan, state, is_v12=False) == 0
    recovered = state["cubes"]["Medium"]
    assert recovered["status"] == "done"
    assert recovered["derived"] is True
    assert recovered["pct_change"] == pytest.approx(-30.0)


def test_resume_requeues_an_in_flight_cube_whose_reorder_never_landed(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    state = odb.new_run(plan, tmp_path)
    state["cubes"]["Medium"].update(status="in_flight",
                                    original_order=list(server.orders["Medium"]))

    assert odb.prepare_resume(server.connect(), plan, state) == 1
    assert state["cubes"]["Medium"]["status"] == "pending"



def test_resume_inherits_the_original_deadline(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    state = odb.new_run(plan, tmp_path)
    deadline = state["deadline_at"]
    server.clock[0] += 3600  # an hour of downtime before the resume

    result, _ = run(server, plan, tmp_path)
    assert state["deadline_at"] == deadline
    assert result["deadline_at"] == pytest.approx(result["started_at"]
                                                  + plan["options"]["time_limit_hours"] * 3600)


def test_a_run_killed_by_an_unexpected_error_is_not_recorded_as_completed(tmp_path, frozen_clock):
    """The headline promise: a sweep that dies at cube 2 of 3 can be resumed.

    Anything that is not `OptimizeDbAborted` is re-raised after the first
    successful connect, so only the initialiser decides what the `finally`
    persists. If it says `completed`, `optimize_db(resume_plan_id=…)` reports
    "already completed" and the remaining cubes are lost.
    """
    server = three_cube_server(Medium={"probe_raises_once": True})
    frozen_clock["server"] = server
    plan = make_plan(server)
    odb.write_json(odb.plan_path(plan["plan_id"], "srv", tmp_path), plan)

    with pytest.raises(KeyError):
        odb.optimize_db(server.connect, plan=plan, result_path=tmp_path)

    artifact = json.loads(odb.run_path(plan["plan_id"], "srv", tmp_path).read_text())
    assert artifact["status"] == "failed"
    assert artifact["cubes"]["Small"]["status"] == "done"
    assert artifact["cubes"]["Medium"]["status"] == "pending"
    assert artifact["cubes"]["Big"]["status"] == "pending"

    resumed = odb.optimize_db(server.connect, resume_plan_id=plan["plan_id"],
                              result_path=tmp_path)
    assert resumed["status"] == "completed"
    assert [c for c, _ in server.reorders] == ["Small", "Medium", "Big"]



def test_a_resume_keeps_the_throughput_it_already_measured(tmp_path, frozen_clock):
    """`prepare_resume` must not wipe `run["samples"]`.

    With the window gone `fits_in_budget` has nothing to extrapolate from and
    returns `(True, None)` — see
    `test_first_cube_always_runs_because_there_is_nothing_to_extrapolate_from`
    — so the first cube after every resume would start regardless of how
    little of the inherited deadline is left. A `ReorderDimensions` already
    under way cannot be aborted.
    """
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    # Under 500s of the inherited budget left; Medium is priced at 10 GB over
    # the retained 1 GB / 100s, i.e. 1000s.
    plan["options"]["time_limit_hours"] = 500 / 3600
    state = odb.new_run(plan, tmp_path)
    state["samples"] = [[1 * GB, 100.0]]
    state["cubes"]["Small"].update(status="done", duration_s=100.0)
    server.orders["Small"] = list(plan["cubes"][0]["target_order"])

    assert odb.prepare_resume(server.connect(), plan, state) == 0
    assert state["samples"] == [[1 * GB, 100.0]]

    path = tmp_path / "run.json"
    result = odb.execute_plan(server.connect, plan, state,
                              lambda: odb.write_json(path, state))
    assert server.reorders == []
    assert result["status"] == "stopped_time_limit"
    assert result["cubes"]["Medium"]["status"] == "pending"


def test_list_runs_warns_about_a_run_file_it_cannot_read(tmp_path, caplog):
    folder = tmp_path / "srv"
    folder.mkdir()
    (folder / f"{odb.RUN_PREFIX}broken.json").write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert odb.list_runs(tmp_path) == []
    assert f"{odb.RUN_PREFIX}broken.json" in caplog.text


# --- the report ------------------------------------------------------------

def _report_rows(path):
    """The per-cube rows the report's table is rendered from."""
    text = path.read_text(encoding="utf-8")
    start = text.index("const rows = ") + len("const rows = ")
    return {r["cube"]: r["statusLabel"] for r in json.loads(text[start:text.index(";\n", start)])}


def mixed_outcome_server():
    """Four cubes that end reordered, reverted, failed and not started."""
    return FakeServer(
        orders={name: ["A", "B", "C"] for name in ("Kept", "Worse", "Locked", "Huge")},
        ram={"Kept": 10 * GB, "Worse": 11 * GB, "Locked": 12 * GB, "Huge": 1000 * GB},
        behaviour={"Kept": {"duration": 100.0}, "Worse": {"duration": 100.0, "pct": 4.2},
                   "Locked": {"duration": 100.0, "fail": True}},
    )


def test_a_finished_run_leaves_a_report_naming_each_cube_with_its_status(tmp_path, frozen_clock):
    server = mixed_outcome_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    # Enough for the three small cubes; the large one is priced far past the limit.
    plan["options"]["time_limit_hours"] = 1000 / 3600

    result = odb.optimize_db(server.connect, plan=plan, result_path=tmp_path)
    assert result["status"] == "stopped_time_limit"

    report = odb.report_path(plan["plan_id"], "srv", tmp_path)
    assert report.parent == odb.run_path(plan["plan_id"], "srv", tmp_path).parent
    assert _report_rows(report) == {"Kept": "Reordered", "Worse": "Reverted",
                                    "Locked": "Failed", "Huge": "Not started"}
    assert "Stopped — time limit" in report.read_text(encoding="utf-8")


def test_the_reported_saving_and_share_are_the_run_totals(tmp_path, frozen_clock):
    server = mixed_outcome_server()
    frozen_clock["server"] = server
    plan = make_plan(server)
    plan["options"]["time_limit_hours"] = 1000 / 3600

    result = odb.optimize_db(server.connect, plan=plan, result_path=tmp_path)
    saved = result["totals"]["bytes_saved"]
    assert saved == pytest.approx(1 * GB)  # only Kept counts: 10 GB at -10%
    text = odb.report_path(plan["plan_id"], "srv", tmp_path).read_text(encoding="utf-8")
    assert f"{saved / GB:.2f} GB" in text
    assert f"{saved / plan['total_model_ram_bytes']:.1%} of the model's" in text


def test_a_report_that_cannot_be_written_leaves_the_outcome_alone(tmp_path, frozen_clock, monkeypatch, caplog):
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)

    def refuse(*args):
        raise OSError("disk full")

    monkeypatch.setattr(odb, "write_report", refuse)
    with caplog.at_level(logging.WARNING):
        result = odb.optimize_db(server.connect, plan=plan, result_path=tmp_path)
    assert result["status"] == "completed"
    assert json.loads(odb.run_path("p1", "srv", tmp_path).read_text())["status"] == "completed"
    assert not odb.report_path("p1", "srv", tmp_path).exists()
    assert "disk full" in caplog.text


def test_a_dry_run_writes_no_report(tmp_path, frozen_clock):
    server = three_cube_server()
    frozen_clock["server"] = server
    plan = make_plan(server)

    odb.optimize_db(server.connect, plan=plan, dry_run=True, result_path=tmp_path)
    assert server.reorders == []
    assert list(tmp_path.rglob("*")) == []


def test_a_resumed_run_rewrites_its_report_when_it_finishes(tmp_path, frozen_clock):
    server = three_cube_server(Medium={"probe_raises_once": True})
    frozen_clock["server"] = server
    plan = make_plan(server)
    odb.write_json(odb.plan_path(plan["plan_id"], "srv", tmp_path), plan)
    report = odb.report_path(plan["plan_id"], "srv", tmp_path)

    with pytest.raises(KeyError):
        odb.optimize_db(server.connect, plan=plan, result_path=tmp_path)
    assert _report_rows(report) == {"Small": "Reordered", "Medium": "Not started", "Big": "Not started"}

    odb.optimize_db(server.connect, resume_plan_id=plan["plan_id"], result_path=tmp_path)
    assert _report_rows(report) == {"Small": "Reordered", "Medium": "Reordered", "Big": "Reordered"}
    assert "Completed" in report.read_text(encoding="utf-8")


def test_the_report_words_a_run_status_as_the_optimize_db_page_does():
    app_js = (Path(odb.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const OPTDB_RUN_STATUS = \{(.*?)\};", app_js, re.S).group(1)
    page = dict(re.findall(r'(\w+): "([^"]+)"', block))
    assert page == odb.RUN_STATUS_LABELS
