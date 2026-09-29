"""The UI's HTTP layer, exercised through a real server on a free port.

Nothing here reaches TM1: the tests use endpoints that only touch config.ini and
the results folder, or jobs whose work is a stand-in function.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest
from TM1py.Exceptions import TM1pyRestException

from optimuspy import optimize_db as odb
from optimuspy import ui
from optimuspy.core import load_settings
from optimuspy.executors import OptimizationCancelled

INI = (
    "[prod]\n"
    "address=10.0.0.1\n"
    "port=12354\n"
    "user=admin\n"
    "password=s3cret\n"
    "api_key=k3y\n"
    "ssl=True\n"
)


def request(method, url, body=None, headers=None):
    """Send one request; returns (status, headers, body text) for any status."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, dict(e.headers), e.read().decode()


def _port(base):
    return base.rsplit(":", 1)[1]


def test_a_request_from_another_origin_is_refused(ui_server):
    base, _ = ui_server(INI)
    status, headers, _ = request("GET", f"{base}/api/instance/prod",
                                 headers={"Origin": "https://evil.example"})
    assert status == 403
    assert "Access-Control-Allow-Origin" not in headers


def test_a_request_for_another_host_is_refused(ui_server):
    # A DNS-rebinding page reaches 127.0.0.1 under its own host name.
    base, _ = ui_server(INI)
    status, _, _ = request("GET", f"{base}/api/instances",
                           headers={"Host": f"attacker.example:{_port(base)}"})
    assert status == 403


@pytest.mark.parametrize("name", ["127.0.0.1", "localhost"])
def test_the_page_itself_is_answered_under_either_loopback_name(ui_server, name):
    base, _ = ui_server(INI)
    own = f"{name}:{_port(base)}"
    # DELETE of a config that does not exist: reaching the handler means a 404.
    status, headers, _ = request("DELETE", f"{base}/api/config/none.json",
                                 headers={"Host": own, "Origin": f"http://{own}"})
    assert status == 404
    assert "Access-Control-Allow-Origin" not in headers


def test_a_cross_origin_preflight_is_refused(ui_server):
    base, _ = ui_server(INI)
    status, headers, _ = request("OPTIONS", f"{base}/api/instance/prod", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert status == 403
    assert "Access-Control-Allow-Methods" not in headers


def test_stored_secrets_are_never_sent_to_the_page(ui_server):
    base, _ = ui_server(INI)
    status, _, text = request("GET", f"{base}/api/instance/prod")
    params = json.loads(text)["params"]
    assert status == 200
    assert params["address"] == "10.0.0.1"
    assert "password" not in params
    assert "api_key" not in params


# --- jobs --------------------------------------------------------------------

def wait_done(job, timeout=5):
    deadline = time.time() + timeout
    while job.status == "running":
        assert time.time() < deadline, "job did not finish"
        time.sleep(0.01)


def _kinds(job):
    events, _ = job.events_after(0, timeout=0)
    return [e["event"] for e in events if e["event"] != "log"]


def test_a_job_ends_with_one_final_event_carrying_its_status():
    jobs = ui.JobManager()

    def work(job):
        job.emit("progress", {"step": 1})
        return "completed", {"success": True}

    job = jobs.get(jobs.start("optimize", "Sales", "prod", work))
    wait_done(job)
    events, done = job.events_after(0, timeout=0)
    assert done
    assert _kinds(job) == ["progress", "complete"]
    assert events[-1]["data"] == {"success": True, "status": "completed"}


def test_reading_the_log_does_not_consume_it():
    jobs = ui.JobManager()
    job = jobs.get(jobs.start("optimize", "Sales", "prod", lambda job: ("completed", {})))
    wait_done(job)
    first, _ = job.events_after(0, timeout=0)
    second, _ = job.events_after(0, timeout=0)
    tail, done = job.events_after(len(first) - 1, timeout=0)
    assert first == second
    assert done and tail == first[-1:]


def test_a_raised_cancel_ends_the_job_as_cancelled():
    jobs = ui.JobManager()

    def work(job):
        raise OptimizationCancelled()

    job = jobs.get(jobs.start("optimize", "Sales", "prod", work))
    wait_done(job)
    assert job.status == "cancelled"
    assert _kinds(job)[-1] == "cancelled"


def test_an_error_ends_the_job_as_failed_with_its_message():
    jobs = ui.JobManager()

    def work(job):
        raise RuntimeError("boom")

    job = jobs.get(jobs.start("optimize", "Sales", "prod", work))
    wait_done(job)
    events, _ = job.events_after(0, timeout=0)
    assert job.status == "failed" and job.error == "boom"
    assert events[-1] == {"event": "error_event", "data": {"error": "boom", "status": "failed"}}


def test_only_one_job_runs_at_a_time():
    jobs = ui.JobManager()
    gate = threading.Event()

    def slow(job):
        gate.wait(5)
        return "completed", {}

    first = jobs.get(jobs.start("optimize", "A", "prod", slow))
    with pytest.raises(RuntimeError):
        jobs.start("optimize", "B", "prod", lambda job: ("completed", {}))
    gate.set()
    wait_done(first)
    jobs.start("optimize", "B", "prod", lambda job: ("completed", {}))  # free again


class _Monitoring:
    def __init__(self):
        self.cancelled = []

    def get_active_session_threads(self):
        return [{"ID": 7}]

    def cancel_thread(self, thread_id):
        self.cancelled.append(thread_id)


class _Service:
    def __init__(self):
        self.monitoring = _Monitoring()


def test_stop_aborts_server_threads_only_for_work_that_published_its_service():
    jobs = ui.JobManager()
    published, unpublished = _Service(), _Service()

    def benchmark(job):  # single-cube Optimize: a query in flight is safe to abort
        job.tm1_holder["tm1"] = published
        job.cancel_event.wait(5)
        return "cancelled", {}

    job = jobs.get(jobs.start("optimize", "Sales", "prod", benchmark))
    while "tm1" not in job.tm1_holder:
        time.sleep(0.01)
    assert jobs.cancel(job.job_id)
    wait_done(job)
    assert published.monitoring.cancelled == [7]

    def rebuild(job):  # a storage reorder in flight must be left to finish
        job.cancel_event.wait(5)
        return "cancelled", {}

    job = jobs.get(jobs.start("optimize-db", "plan", "prod", rebuild))
    assert jobs.cancel(job.job_id)
    wait_done(job)
    assert unpublished.monitoring.cancelled == []
    assert job.status == "cancelled"


def read_stream(url, headers=None):
    """A finished job's stream, as (id, event, data) triples, heartbeats dropped."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode()
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in fields:
            events.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return events


def test_a_stream_replays_the_log_and_resumes_after_the_last_event_seen(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)

    def work(job):
        for i in range(3):
            job.emit("progress", {"i": i})
        return "completed", {}

    job = jobs.get(jobs.start("transfer", "3 cubes", "prod", work))
    wait_done(job)
    url = f"{base}/api/job/{job.job_id}/stream"
    full = read_stream(url)
    assert [e[1] for e in full if e[1] != "log"] == ["progress", "progress", "progress", "complete"]
    assert [e[0] for e in full] == list(range(1, len(full) + 1))
    assert read_stream(url, headers={"Last-Event-ID": "2"})[0][0] == 3
    assert read_stream(url + "?after=2")[0][0] == 3


# --- concurrency ---------------------------------------------------------------

def _hold_until_cancelled(job):
    job.cancel_event.wait(10)
    return "cancelled", {}


def test_stop_reaches_a_job_while_its_stream_is_open(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    job_id = jobs.start("optimize-db", "plan", "prod", _hold_until_cancelled)
    stream = urllib.request.urlopen(f"{base}/api/job/{job_id}/stream", timeout=10)
    try:
        started = time.time()
        status, _, _ = request("POST", f"{base}/api/job/{job_id}/cancel")
        assert status == 200
        assert time.time() - started < 2
        assert "event: complete" in stream.read().decode()
    finally:
        stream.close()


def test_two_open_streams_each_receive_the_whole_log(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    gate = threading.Event()

    def work(job):
        gate.wait(10)
        job.emit("progress", {"cube": "Sales"})
        return "completed", {}

    job_id = jobs.start("transfer", "1 cubes", "prod", work)
    url = f"{base}/api/job/{job_id}/stream"
    first = urllib.request.urlopen(url, timeout=10)
    second = urllib.request.urlopen(url, timeout=10)
    gate.set()
    for stream in (first, second):
        with stream:
            text = stream.read().decode()
        assert "event: progress" in text
        assert "event: complete" in text


def test_a_request_that_logs_during_a_job_stays_out_of_the_job_log(ui_server, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    base, _ = ui_server(INI)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    gate = threading.Event()

    def work(job):
        logging.info("from the job")
        gate.wait(10)
        return "completed", {}

    def noisy_validate(config, mode):
        logging.info("from a request")
        raise ValueError("not valid")

    monkeypatch.setattr(ui, "validate_cube_config", noisy_validate)
    job = jobs.get(jobs.start("optimize", "Sales", "prod", work))
    request("POST", f"{base}/api/validate", body={"config": {"cube": "Sales"}})
    gate.set()
    wait_done(job)
    events, _ = job.events_after(0, timeout=0)
    messages = [e["data"]["message"] for e in events if e["event"] == "log"]
    assert "from the job" in messages
    assert "from a request" not in messages


def test_an_optimization_that_reports_failure_finishes_failed(ui_server, monkeypatch):
    # core.main reports a fatal error by returning False, not by raising, so the
    # job still ends with "complete". The status in that event is the only thing
    # that tells the page the run failed.
    base, _ = ui_server(INI)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    monkeypatch.setattr(ui, "run_optimuspy", lambda **kwargs: False)
    status, _, text = request("POST", f"{base}/api/job/start", body={
        "mode": "optimize", "cube_config": {"instance": "prod", "cube": "Sales"}})
    assert status == 200
    job = jobs.get(json.loads(text)["job_id"])
    wait_done(job)
    events, _ = job.events_after(0, timeout=0)
    assert job.status == "failed"
    assert events[-1]["event"] == "complete"
    assert events[-1]["data"]["status"] == "failed"
    assert events[-1]["data"]["success"] is False


# --- sync order ----------------------------------------------------------------

class _Cubes:
    """Storage orders by cube name. A cube in `broken` fails to read. With a
    `gate`, reading cube 'A' signals `entered` and then waits for the gate."""

    def __init__(self, orders, broken=(), gate=None):
        self.orders = {name: list(order) for name, order in orders.items()}
        self.broken = set(broken)
        self.gate = gate
        self.entered = threading.Event()
        self.applied = []

    def get_storage_dimension_order(self, cube_name):
        if self.gate is not None and cube_name == "A":
            self.entered.set()
            self.gate.wait(5)
        if cube_name in self.broken:
            raise RuntimeError(f"cube '{cube_name}' is locked")
        return list(self.orders[cube_name])

    def update_storage_dimension_order(self, cube_name, order):
        self.applied.append(cube_name)
        self.orders[cube_name] = list(order)
        return 0.0


class _SyncTarget:
    def __init__(self, cubes):
        self.cubes = cubes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sync(base, monkeypatch, cubes, orders):
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    monkeypatch.setattr(ui, "_create_tm1_connection", lambda instance, password=None: _SyncTarget(cubes))
    status, _, text = request("POST", f"{base}/api/transfer/apply", body={"instance": "prod", "orders": orders})
    assert status == 200
    return jobs, jobs.get(json.loads(text)["job_id"])


def test_sync_reports_each_cube_and_fails_when_any_cube_failed(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    cubes = _Cubes({"Same": ["a", "b"], "Change": ["a", "b"], "Locked": ["a", "b"]}, broken={"Locked"})
    _, job = _sync(base, monkeypatch, cubes,
                   {"Same": ["a", "b"], "Change": ["b", "a"], "Locked": ["b", "a"]})
    wait_done(job)
    events, _ = job.events_after(0, timeout=0)
    progress = [e["data"] for e in events if e["event"] == "progress"]
    assert [(p["cube"], p["status"]) for p in progress] == [
        ("Same", "skipped"), ("Change", "applied"), ("Locked", "failed")]
    assert [(p["index"], p["total"]) for p in progress] == [(1, 3), (2, 3), (3, 3)]
    assert "locked" in progress[2]["error"]
    assert cubes.applied == ["Change"]            # the unchanged cube is not rebuilt
    assert job.status == "failed"
    assert events[-1]["data"]["success"] is False


def test_sync_with_nothing_failed_completes(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    cubes = _Cubes({"Change": ["a", "b"]})
    _, job = _sync(base, monkeypatch, cubes, {"Change": ["b", "a"]})
    wait_done(job)
    assert job.status == "completed"


def test_stop_ends_a_sync_between_cubes(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    gate = threading.Event()
    cubes = _Cubes({"A": ["a", "b"], "B": ["a", "b"]}, gate=gate)
    jobs, job = _sync(base, monkeypatch, cubes, {"A": ["b", "a"], "B": ["b", "a"]})
    assert cubes.entered.wait(5)      # the job is inside cube A
    assert jobs.cancel(job.job_id)
    gate.set()
    wait_done(job)
    assert cubes.applied == ["A"]     # the cube in hand finishes; B is never started
    assert job.status == "cancelled"


# --- optimize db ---------------------------------------------------------------

PLAN_INI = (
    "[Planning Prod]\naddress=10.0.0.1\nport=1\nuser=admin\n"
    "[dev]\naddress=10.0.0.2\nport=1\nuser=admin\n"
)
PLAN_ID = "Planning Prod_2026-09-23_22-00-00"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _plan_file(tmp_path, plan_id=PLAN_ID, instance="Planning Prod"):
    return tmp_path / "results" / instance / f"optdb_plan_{plan_id}.json"


def _run_file(tmp_path, plan_id=PLAN_ID, instance="Planning Prod"):
    return tmp_path / "results" / instance / f"optdb_run_{plan_id}.json"


def _run_plan(base, monkeypatch, body):
    """POST /api/optimize-db/run with optimize_db stubbed; returns (status, payload, job, kwargs)."""
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    seen = {}

    def fake_optimize_db(connect, **kwargs):
        seen.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(ui, "optimize_db", fake_optimize_db)
    status, _, text = request("POST", f"{base}/api/optimize-db/run", body=body)
    payload = json.loads(text)
    job = jobs.get(payload["job_id"]) if status == 200 else None
    if job is not None:
        wait_done(job)
    return status, payload, job, seen


def test_running_a_plan_executes_the_plan_that_was_reviewed(ui_server, monkeypatch, tmp_path):
    base, _ = ui_server(PLAN_INI)
    plan = {"plan_id": PLAN_ID, "instance": "Planning Prod", "cubes": [{"cube": "Sales"}]}
    _write_json(_plan_file(tmp_path), plan)
    status, _, job, seen = _run_plan(base, monkeypatch, {"instance": "Planning Prod", "plan_id": PLAN_ID})
    assert status == 200
    assert seen["plan"] == plan
    # No instructions to re-plan from, and no TM1 service handed to Stop.
    assert sorted(seen) == ["cancel_event", "plan"]
    assert job.label == PLAN_ID


def test_running_a_plan_that_already_started_continues_its_run(ui_server, monkeypatch, tmp_path):
    # A run left "running" is what a killed or restarted UI leaves behind.
    base, _ = ui_server(PLAN_INI)
    _write_json(_plan_file(tmp_path), {"plan_id": PLAN_ID, "instance": "Planning Prod", "cubes": []})
    _write_json(_run_file(tmp_path), {"plan_id": PLAN_ID, "instance": "Planning Prod", "status": "running"})
    status, _, _, seen = _run_plan(base, monkeypatch, {"instance": "Planning Prod", "plan_id": PLAN_ID})
    assert status == 200
    assert sorted(seen) == ["cancel_event", "resume_plan_id"]
    assert seen["resume_plan_id"] == PLAN_ID


def test_a_run_is_only_continued_on_its_own_instance(ui_server, monkeypatch, tmp_path):
    base, _ = ui_server(PLAN_INI)
    _write_json(_run_file(tmp_path), {"plan_id": PLAN_ID, "instance": "Planning Prod", "status": "cancelled"})
    status, _, _, seen = _run_plan(base, monkeypatch, {"instance": "dev", "plan_id": PLAN_ID})
    assert status == 400
    assert seen == {}


def test_an_unknown_plan_is_not_found(ui_server, monkeypatch):
    base, _ = ui_server(PLAN_INI)
    status, _, _, seen = _run_plan(base, monkeypatch, {"instance": "Planning Prod", "plan_id": PLAN_ID})
    assert status == 404
    assert seen == {}


@pytest.mark.parametrize("body,expected", [
    ({"instance": "Planning Prod"}, 400),                                  # instructions, no plan id
    ({"instance": "nowhere", "plan_id": PLAN_ID}, 400),                    # not in config.ini
    ({"instance": "Planning Prod", "plan_id": "../../etc/x"}, 400),        # a path, not an id
    ({"instance": "Planning Prod", "plan_id": "*"}, 404),                  # a pattern matches nothing
])
def test_a_plan_id_names_exactly_one_plan(ui_server, monkeypatch, tmp_path, body, expected):
    base, _ = ui_server(PLAN_INI)
    _write_json(_run_file(tmp_path), {"plan_id": PLAN_ID, "instance": "Planning Prod", "status": "cancelled"})
    status, _, _, seen = _run_plan(base, monkeypatch, body)
    assert status == expected
    assert seen == {}


# --- hygiene -------------------------------------------------------------------

def test_an_unknown_instance_is_named_in_the_error(ui_server):
    base, _ = ui_server(INI)
    status, _, text = request("POST", f"{base}/api/connect", body={"instance": "prod2"})
    assert status == 502
    assert "Instance 'prod2' not found" in json.loads(text)["error"]


def test_a_saved_config_is_read_as_utf8(ui_server, tmp_path):
    # Pins Windows behaviour: on a UTF-8 host this passes with or without the
    # explicit encoding, so it guards against the encoding being dropped again.
    base, _ = ui_server(INI)
    (tmp_path / "cube-configs").mkdir()
    (tmp_path / "cube-configs" / "ventas.json").write_bytes(
        json.dumps({"cube": "Ventas €", "instance": "prod"}, ensure_ascii=False).encode("utf-8"))
    status, _, text = request("GET", f"{base}/api/saved-cubes")
    assert status == 200
    assert [c["cube"] for c in json.loads(text)["saved_cubes"]] == ["Ventas €"]


def test_a_response_never_carries_nan(ui_server, tmp_path):
    base, _ = ui_server(INI)
    (tmp_path / "cube-configs").mkdir()
    (tmp_path / "cube-configs" / "odd.json").write_text(
        '{"cube": "Sales", "instance": "prod", "executions": NaN}', encoding="utf-8")
    _, _, text = request("GET", f"{base}/api/saved-cubes")
    assert "NaN" not in text
    assert json.loads(text)["saved_cubes"][0]["executions"] is None


def test_a_stream_event_never_carries_nan(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    job = jobs.get(jobs.start("optimize-db", "plan", "prod",
                              lambda job: ("completed", {"run": {"pct_change": float("nan")}})))
    wait_done(job)
    final = read_stream(f"{base}/api/job/{job.job_id}/stream")[-1]
    assert final[1] == "complete"
    assert final[2]["run"]["pct_change"] is None


def test_the_run_state_is_read_back_in_plan_order(ui_server, tmp_path):
    base, _ = ui_server(PLAN_INI)
    cubes = {"Small": {"status": "done", "pct_change": -12.5},
             "Middle": {"status": "in_flight", "pct_change": None},
             "Large": {"status": "pending", "pct_change": None}}
    _write_json(_run_file(tmp_path), {"plan_id": PLAN_ID, "instance": "Planning Prod",
                                      "status": "running", "cubes": cubes})
    status, _, text = request("GET", f"{base}/api/optimize-db/run/{urllib.parse.quote(PLAN_ID)}")
    run = json.loads(text)["run"]
    assert status == 200
    assert list(run["cubes"]) == ["Small", "Middle", "Large"]
    assert run["cubes"]["Small"]["pct_change"] == -12.5


@pytest.mark.parametrize("plan_id,expected", [(urllib.parse.quote(PLAN_ID), 404), ("..%2F..%2Fsecret", 400)])
def test_the_run_state_of_an_unknown_or_malformed_id(ui_server, plan_id, expected):
    base, _ = ui_server(PLAN_INI)
    status, _, _ = request("GET", f"{base}/api/optimize-db/run/{plan_id}")
    assert status == expected


REFUSED = TM1pyRestException("", 401, "Unauthorized", {
    "Set-Cookie": "TM1SessionId=s3ss10n; Path=/api/; HttpOnly", "WWW-Authenticate": 'Basic realm="TM1"'})


def _tm1_raises(monkeypatch, error):
    def connect(instance, password=None):
        raise error
    monkeypatch.setattr(ui, "_create_tm1_connection", connect)


def test_a_refused_login_shows_the_status_not_the_headers(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    _tm1_raises(monkeypatch, REFUSED)
    status, _, text = request("POST", f"{base}/api/connect", body={"instance": "prod"})
    assert status == 502
    assert json.loads(text)["error"] == "Connection failed: TM1 returned 401 Unauthorized"
    assert "TM1SessionId" not in text


def test_tm1s_own_message_is_what_the_page_shows(ui_server, monkeypatch):
    base, _ = ui_server(INI)
    _tm1_raises(monkeypatch, TM1pyRestException(
        '{"error": {"code": "278", "message": "Cube \'Nope\' not found"}}', 404, "Not Found",
        {"Set-Cookie": "TM1SessionId=s3ss10n"}))
    status, _, text = request("POST", f"{base}/api/views", body={"instance": "prod", "cube": "Nope"})
    assert status == 500
    assert json.loads(text)["error"] == "TM1 returned 404 Not Found: Cube 'Nope' not found"


def test_a_job_that_hits_a_tm1_error_reports_it_without_the_headers():
    jobs = ui.JobManager()

    def work(job):
        raise TM1pyRestException("boom", 500, "Internal Server Error", {"Set-Cookie": "TM1SessionId=s3ss10n"})

    job = jobs.get(jobs.start("optimize", "Sales", "prod", work))
    wait_done(job)
    events, _ = job.events_after(0, timeout=0)
    assert events[-1]["event"] == "error_event"
    assert events[-1]["data"]["error"] == "TM1 returned 500 Internal Server Error: boom"
    assert "TM1SessionId" not in json.dumps(events)


# --- folders -------------------------------------------------------------------

CUBE_CONFIG = {"instance": "prod", "cube": "Sales", "executions": 1, "output": "csv"}


def _set_folder(base, body):
    status, _, text = request("POST", f"{base}/api/folders", body=body)
    return status, json.loads(text)


def test_saved_cube_configs_go_to_cube_configs_by_default(ui_server, tmp_path):
    base, _ = ui_server(INI)
    status, _, text = request("POST", f"{base}/api/config", body={"config": CUBE_CONFIG, "filename": "sales"})
    assert status == 200
    saved = tmp_path / "cube-configs" / "sales.json"
    assert json.loads(text)["path"] == str(saved)
    assert json.loads(saved.read_text(encoding="utf-8")) == CUBE_CONFIG


def test_a_chosen_folder_is_used_to_save_list_and_delete(ui_server, tmp_path):
    base, _ = ui_server(INI)
    folder = tmp_path / "shared" / "cubes"
    status, folders = _set_folder(base, {"kind": "cube_configs", "path": f' "{folder}" '})
    assert status == 200
    assert folders["cube_configs"] == {"path": str(folder), "is_default": False}

    status, _, text = request("POST", f"{base}/api/config", body={"config": CUBE_CONFIG, "filename": "sales"})
    assert status == 200 and json.loads(text)["path"] == str(folder / "sales.json")
    _, _, text = request("GET", f"{base}/api/saved-cubes")
    assert [c["filename"] for c in json.loads(text)["saved_cubes"]] == ["sales.json"]
    status, _, _ = request("DELETE", f"{base}/api/config/sales.json")
    assert status == 200
    assert not (folder / "sales.json").exists()
    assert not (tmp_path / "cube-configs").exists()


def test_a_chosen_exports_folder_is_used_by_export_to_folder(ui_server, tmp_path):
    base, _ = ui_server(INI)
    folder = tmp_path / "orders"
    _set_folder(base, {"kind": "exports", "path": str(folder)})
    status, _, text = request("POST", f"{base}/api/transfer/export",
                              body={"instance": "prod", "orders": {"Sales": ["Time", "Region"]}})
    payload = json.loads(text)
    assert status == 200
    assert payload == {"files": [str(folder / "Sales.json")], "folder": str(folder)}
    assert json.loads((folder / "Sales.json").read_text())["predefined_orders"] == [["Time", "Region"]]
    assert not (tmp_path / "exports").exists()


def test_exports_go_to_exports_by_default(ui_server, tmp_path):
    base, _ = ui_server(INI)
    _, _, text = request("POST", f"{base}/api/transfer/export",
                         body={"instance": "prod", "orders": {"Sales": ["Time"]}})
    assert json.loads(text)["folder"] == str(tmp_path / "exports")


def test_the_folders_start_at_their_defaults(ui_server, tmp_path):
    base, _ = ui_server(INI)
    status, _, text = request("GET", f"{base}/api/folders")
    assert status == 200
    assert json.loads(text) == {
        "cube_configs": {"path": str(tmp_path / "cube-configs"), "is_default": True},
        "exports": {"path": str(tmp_path / "exports"), "is_default": True},
    }


@pytest.mark.parametrize("body", [{"kind": "results", "path": "x"}, {"path": "x"}, {"kind": "exports"}])
def test_an_unknown_kind_or_no_path_is_refused(ui_server, body):
    base, _ = ui_server(INI)
    status, _ = _set_folder(base, body)
    assert status == 400
    assert load_settings() == {}


def test_reset_goes_back_to_the_default(ui_server, tmp_path):
    base, _ = ui_server(INI)
    _set_folder(base, {"kind": "cube_configs", "path": str(tmp_path / "elsewhere")})
    status, folders = _set_folder(base, {"kind": "cube_configs", "reset": True})
    assert status == 200
    assert folders["cube_configs"] == {"path": str(tmp_path / "cube-configs"), "is_default": True}
    assert load_settings() == {}


def test_choosing_the_default_folder_stores_nothing(ui_server, tmp_path):
    base, _ = ui_server(INI)
    status, folders = _set_folder(base, {"kind": "exports", "path": "exports"})
    assert status == 200 and folders["exports"]["is_default"] is True
    assert load_settings() == {}


def test_a_path_that_is_a_file_is_refused(ui_server, tmp_path):
    base, _ = ui_server(INI)
    (tmp_path / "notes.txt").write_text("x")
    status, payload = _set_folder(base, {"kind": "exports", "path": str(tmp_path / "notes.txt")})
    assert status == 400
    assert "notes.txt" in payload["error"]
    assert load_settings() == {}


def test_a_chosen_folder_is_created_at_once(ui_server, tmp_path):
    base, _ = ui_server(INI)
    folder = tmp_path / "a" / "b"
    _set_folder(base, {"kind": "exports", "path": str(folder)})
    assert folder.is_dir()


def test_a_chosen_folder_survives_a_restart(ui_server, tmp_path):
    folder = tmp_path / "shared"
    base, _ = ui_server(INI)
    _set_folder(base, {"kind": "cube_configs", "path": str(folder)})
    (folder / "sales.json").write_text(json.dumps(CUBE_CONFIG), encoding="utf-8")

    restarted, _ = ui_server(INI)  # a new server reading the same settings.ini
    _, _, text = request("GET", f"{restarted}/api/saved-cubes")
    assert [c["filename"] for c in json.loads(text)["saved_cubes"]] == ["sales.json"]
    assert ui.cube_configs_dir() == folder


# --- reports -----------------------------------------------------------------

def _touch(tmp_path, relative, text="x"):
    path = tmp_path / "results" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _names(files):
    return [f["filename"] for f in files]


def _reports(base):
    status, _, text = request("GET", f"{base}/api/reports")
    assert status == 200
    return {i["name"]: i for i in json.loads(text)["instances"]}


def _plan_and_run(plan_id=PLAN_ID):
    """A one-cube plan and the finished run of it, as Optimize DB writes them."""
    options = odb.resolve_options({"instance": "Planning Prod"})
    records = [{"cube": "Sales", "ram_bytes": 2 * 1024 ** 3, "storage_order": ["A", "B", "C"],
                "dimensions": {d: {"name": d, "leaf_elements": n, "has_strings": False}
                               for d, n in (("A", 3), ("B", 2), ("C", 1))}}]
    plan = odb.build_plan("Planning Prod", plan_id, options, records, 4 * 1024 ** 3, [])
    run = odb.new_run(plan)
    run["cubes"]["Sales"].update(status="done", pct_change=-25.0, duration_s=3.0)
    run.update(status="completed", finished_at=run["started_at"] + 10)
    return plan, run


def test_reports_are_grouped_by_instance_cube_and_run(ui_server, tmp_path):
    base, _ = ui_server(PLAN_INI)
    inst = "Planning Prod"
    for stamp in ("2026-09-01_10-00-00", "2026-09-02_10-00-00"):
        _touch(tmp_path, f"{inst}/{inst}_Sales_{stamp}.html")
        _touch(tmp_path, f"{inst}/{inst}_Sales_{stamp}.csv")
    _touch(tmp_path, f"{inst}/{inst}_Ventas_por mes_2026-09-03_10-00-00.html")
    _touch(tmp_path, f"{inst}/{inst}_Ventas_por mes_2026-09-03_10-00-00.xlsx")
    with_report, without_report, plan_only = (f"{inst}_2026-09-0{d}_10-00-00" for d in (4, 5, 6))
    for plan_id in (with_report, without_report):
        _write_json(_plan_file(tmp_path, plan_id), {"plan_id": plan_id})
        _write_json(_run_file(tmp_path, plan_id), {"plan_id": plan_id, "status": "completed",
                                                   "started_at": 0})
    _touch(tmp_path, f"{inst}/optdb_report_{with_report}.html")
    _write_json(_plan_file(tmp_path, plan_only), {"plan_id": plan_only})
    _touch(tmp_path, "checkpoint_Sales.json")
    _touch(tmp_path, f"{inst}/notes.txt")
    _touch(tmp_path, f"{inst}/optdb_run_{with_report}.tmp")
    _touch(tmp_path, "Sales_2025-01-01_10-00-00.csv")

    tree = _reports(base)
    assert list(tree) == [inst, ""]
    prod = tree[inst]

    assert [c["cube"] for c in prod["cubes"]] == ["Sales", "Ventas_por mes"]
    sales = prod["cubes"][0]["runs"]
    assert [r["id"] for r in sales] == ["2026-09-02_10-00-00", "2026-09-01_10-00-00"]
    assert sales[0]["kind"] == "cube"
    assert sales[0]["report"]["filename"] == f"{inst}/{inst}_Sales_2026-09-02_10-00-00.html"
    assert _names(sales[0]["data"]) == [f"{inst}/{inst}_Sales_2026-09-02_10-00-00.csv"]
    ventas = prod["cubes"][1]["runs"][0]
    assert ventas["report"]["type"] == "html" and [d["type"] for d in ventas["data"]] == ["xlsx"]

    db = {r["id"]: r for r in prod["optimize_db"]}
    assert db[with_report]["kind"] == "optimize_db" and db[with_report]["status"] == "completed"
    assert db[with_report]["report"]["filename"] == f"{inst}/optdb_report_{with_report}.html"
    assert _names(db[with_report]["data"]) == [f"{inst}/optdb_plan_{with_report}.json",
                                               f"{inst}/optdb_run_{with_report}.json"]
    assert db[without_report]["kind"] == "optimize_db" and db[without_report]["report"] is None
    assert db[plan_only]["kind"] == "plan_only" and db[plan_only]["report"] is None
    assert _names(db[plan_only]["data"]) == [f"{inst}/optdb_plan_{plan_only}.json"]
    assert "status" not in db[plan_only]

    assert _names(prod["other"]) == [f"{inst}/notes.txt"]
    legacy = tree[""]
    assert [c["cube"] for c in legacy["cubes"]] == ["Sales"]
    assert _names(legacy["cubes"][0]["runs"][0]["data"]) == ["Sales_2025-01-01_10-00-00.csv"]
    assert "checkpoint" not in json.dumps(tree)
    assert ".tmp" not in json.dumps(tree)


def test_a_run_file_that_does_not_parse_still_lists_without_a_status(ui_server, tmp_path):
    base, _ = ui_server(PLAN_INI)
    _write_json(_plan_file(tmp_path), {"plan_id": PLAN_ID})
    _touch(tmp_path, f"Planning Prod/optdb_run_{PLAN_ID}.json", "{not json")

    run = _reports(base)["Planning Prod"]["optimize_db"][0]
    assert run["kind"] == "optimize_db" and run["id"] == PLAN_ID
    assert "status" not in run
    assert run["started"] is not None  # from the plan id


def test_no_results_folder_is_no_reports(ui_server):
    base, _ = ui_server(PLAN_INI)
    assert _reports(base) == {}


def test_runs_are_listed_only_by_the_reports_endpoint(ui_server):
    base, _ = ui_server(PLAN_INI)
    status, _, _ = request("GET", f"{base}/api/results")
    assert status == 404


def test_build_report_writes_the_missing_report_and_names_it(ui_server, tmp_path):
    base, _ = ui_server(PLAN_INI)
    plan, run = _plan_and_run()
    _write_json(_plan_file(tmp_path), plan)
    _write_json(_run_file(tmp_path), run)

    status, _, text = request("POST", f"{base}/api/optimize-db/report", body={"plan_id": PLAN_ID})
    assert status == 200
    filename = json.loads(text)["filename"]
    assert filename == f"Planning Prod/optdb_report_{PLAN_ID}.html"
    report = (tmp_path / "results" / filename).read_text(encoding="utf-8")
    assert "Planning Prod / Optimize DB" in report and "Sales" in report and "Completed" in report
    assert _reports(base)["Planning Prod"]["optimize_db"][0]["report"]["filename"] == filename


def test_build_report_with_no_run_is_not_found(ui_server, tmp_path):
    base, _ = ui_server(PLAN_INI)
    _write_json(_plan_file(tmp_path), _plan_and_run()[0])
    status, _, _ = request("POST", f"{base}/api/optimize-db/report", body={"plan_id": PLAN_ID})
    assert status == 404
    assert not (tmp_path / "results" / "Planning Prod" / f"optdb_report_{PLAN_ID}.html").exists()


def test_build_report_waits_for_a_run_in_progress(ui_server, tmp_path, monkeypatch):
    base, _ = ui_server(PLAN_INI)
    plan, run = _plan_and_run()
    run["status"] = "running"
    _write_json(_plan_file(tmp_path), plan)
    _write_json(_run_file(tmp_path), run)
    jobs = ui.JobManager()
    monkeypatch.setattr(ui, "job_manager", jobs)
    job = jobs.get(jobs.start("optimize-db", PLAN_ID, "Planning Prod", _hold_until_cancelled))
    try:
        status, _, _ = request("POST", f"{base}/api/optimize-db/report", body={"plan_id": PLAN_ID})
        assert status == 409
        assert not (tmp_path / "results" / "Planning Prod" / f"optdb_report_{PLAN_ID}.html").exists()
    finally:
        jobs.cancel(job.job_id)
        wait_done(job)


@pytest.mark.parametrize("body", [{}, {"plan_id": "../../secret"}, {"plan_id": 7}])
def test_build_report_refuses_a_malformed_plan_id(ui_server, body):
    base, _ = ui_server(PLAN_INI)
    status, _, _ = request("POST", f"{base}/api/optimize-db/report", body=body)
    assert status == 400


def test_a_data_file_is_served_as_json(ui_server, tmp_path):
    base, _ = ui_server(PLAN_INI)
    _write_json(_run_file(tmp_path), {"plan_id": PLAN_ID, "instance": "Ventas €"})
    filename = urllib.parse.quote(f"Planning Prod/optdb_run_{PLAN_ID}.json", safe="")
    status, headers, text = request("GET", f"{base}/api/result/{filename}")
    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(text)["instance"] == "Ventas €"
