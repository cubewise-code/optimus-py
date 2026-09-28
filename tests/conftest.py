"""Shared test plumbing.

The suite is split in two. **Offline** tests — the default run — make no
connection and use no fake TM1: they exercise the frame, the sweep arithmetic
and the result chain directly. **Live** tests carry `@pytest.mark.live` and are
deselected unless asked for:

    pytest -m live --instance tm1srv01     # v11
    pytest -m live --instance tm1srv02     # v12

They connect with a real `TM1Service`; there is deliberately no fake to fall
back on, so a live test that cannot reach its server skips rather than passing
against a simulation.
"""
import importlib
import sys
import threading
import types
from pathlib import Path

import pytest

from optimuspy.executors import Measurement
from optimuspy.order_frame import OrderFrame
from optimuspy.results import ExecutionContext


# --- live suite plumbing ---------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--instance", action="store", default=None,
        help="config.ini section a live test connects to, e.g. tm1srv01 (v11) or tm1srv02 (v12)")
    parser.addoption(
        "--tm1-config", action="store", default="config/config.ini",
        help="path to the config.ini holding the --instance section")
    parser.addoption(
        "--v11", action="store", default=None,
        help="config.ini section for the v11 instance (the cross-version parity gate)")
    parser.addoption(
        "--v12", action="store", default=None,
        help="config.ini section for the v12 instance (the cross-version parity gate)")


@pytest.fixture(scope="session")
def live_instance(request):
    """The instance name a live test connects to, or a skip when none was named."""
    instance = request.config.getoption("--instance")
    if not instance:
        pytest.skip("live test needs --instance (e.g. --instance tm1srv01)")
    return instance


@pytest.fixture(scope="session")
def tm1_config_path(request):
    return request.config.getoption("--tm1-config")


@pytest.fixture(scope="session")
def tm1_connection_args(live_instance, tm1_config_path):
    """Connection kwargs for `live_instance`, straight out of the real config.ini."""
    from optimuspy.core import get_tm1_config

    config = get_tm1_config(tm1_config_path)
    if not config.has_section(live_instance):
        pytest.skip(f"no [{live_instance}] section in {tm1_config_path}")
    args = dict(config[live_instance])
    args["session_context"] = "optimuspy-tests"
    return args


@pytest.fixture(scope="session")
def tm1(live_instance, tm1_connection_args):
    """A real TM1Service. No fake ever stands in for this.

    A server that cannot be reached SKIPS: the machine simply has no route to it,
    which is not a claim about the code. A server that answers and REFUSES us
    FAILS: an expired credential is a configuration error someone has to fix, and
    skipping it makes a run that tested nothing look exactly like a run on a
    laptop with no TM1 access. That difference matters here more than usual —
    these tests are the justification for coverage that left CI, so "10 skipped"
    must never be the way a stale password reports itself.
    """
    from TM1py import TM1Service

    try:
        service = TM1Service(**tm1_connection_args)
    except Exception as e:
        status = getattr(e, "status_code", None)
        if status in (401, 403):
            pytest.fail(
                f"TM1 refused the credentials for [{live_instance}] (HTTP {status}). "
                f"The server answered, so this is a config.ini problem, not an "
                f"unreachable host — refresh the credentials and re-run. {e}",
                pytrace=False)
        pytest.skip(f"cannot reach TM1: {e}")
    with service:
        yield service


def sample_module(name):
    """Import one of the samples/ scripts as a module.

    The live smoke and parity runs were written there first, as argparse CLIs
    that pytest never collected. Promoting them into the suite means calling
    into them, not copying them — there is one fixture-cube builder and one
    crash-and-resume scenario, and it stays in samples/ where it can also be run
    by hand against an instance that is misbehaving.
    """
    samples = Path(__file__).resolve().parent.parent / "samples"
    if str(samples) not in sys.path:
        sys.path.insert(0, str(samples))
    return importlib.import_module(name)


@pytest.fixture(scope="session")
def is_v12(tm1):
    from optimuspy.metrics import detect_is_v12

    return detect_is_v12(tm1)


# --- offline plumbing ------------------------------------------------------

def offline_executor(cls, dimensions, *, view_names=None, process_names=None,
                     last_slot_locked=False, order_frame=None, cube_name="C",
                     executions=1, context=None, **kwargs):
    """A real executor with no TM1 handle at all.

    Built through the production constructor, so a test never keeps its own list
    of attributes in step with `__init__`. Four hand-rolled factories used to do
    that and all four silently lacked `_reanchor_needed` — invisible for as long
    as the tests also replaced the method that reads it.

    `tm1=None` is deliberate: a sweep that reached for the server fails here
    rather than passing quietly against something that answers.
    """
    return cls(
        None, cube_name, list(view_names or []), list(process_names or []),
        list(dimensions), executions, last_slot_locked,
        context=context if context is not None else ExecutionContext(),
        order_frame=order_frame or OrderFrame(dimensions, last_slot_locked),
        **kwargs)


def install_offline_measurements(executor, ram_of, evaluated_log, query_of=None):
    """Stand in for the server's measurements only — not for anything built on them.

    `_measure_permutation` is the single TM1 call in a sweep (executors.py). It
    applies an order and reports what the server reports: a percentage change, an
    optional absolute RAM reading, query times. Replacing it lets an offline test
    drive a real fold and get real `PermutationResult`s back, because everything
    downstream — the %-chain, the reanchor, the pending write, the run artifact —
    stays production code and is exercised, not simulated.

    This replaced an earlier helper that stubbed `_evaluate_permutation` whole and
    therefore built `PermutationResult`s itself, re-deriving the percentage from
    `context.current_ram`. That was a second copy of the chain the code under test
    owns; it grew its own regression test, which is the point at which a test
    helper has become a fake.

    ram_of:    Callable[[tuple[str, ...]], float] -> the cube's RAM in that order.
    query_of:  optional Callable[[tuple[str, ...]], float] -> composite query time.
    evaluated_log: list; each order actually applied is appended.
    """
    view = executor.view_names[0] if executor.view_names else "__offline__"
    # What the cube measured before the first reorder — the anchor the server's
    # first percentage would be relative to.
    state = {"previous": executor.context.current_ram}

    def _measured(self, permutation, retrieve_ram):
        order = list(permutation)
        evaluated_log.append(order)
        ram = float(ram_of(tuple(order)))
        previous, state["previous"] = state["previous"], ram
        return Measurement(
            # The server reports the change this reorder caused, i.e. against the
            # order the cube was in a moment ago — not against a running baseline.
            ram_percentage_change=0.0 if not previous else (ram / previous - 1.0) * 100.0,
            reorder_duration=0.0,
            query_times_by_view={view: [query_of(tuple(order))]} if query_of else {},
            # Parity with the server stand-in this replaced: process timings are
            # supplied per-test where a test needs them.
            process_times_by_process=None,
            # With no anchor there is nothing for a percentage to be relative to,
            # so the first reading is always absolute — as it is in production,
            # where the original order is measured with retrieve_ram=True.
            ram_usage=ram if (retrieve_ram or not previous) else None,
        )

    executor._measure_permutation = types.MethodType(_measured, executor)


@pytest.fixture
def measure_orders():
    return install_offline_measurements


# --- settings and UI server plumbing ----------------------------------------

@pytest.fixture(autouse=True)
def settings_path(tmp_path, monkeypatch):
    """The settings file every test reads and writes: tmp_path/config/settings.ini,
    never the repo's config/settings.ini."""
    path = tmp_path / "config" / "settings.ini"
    monkeypatch.setattr("optimuspy.core.SETTINGS_PATH", path)
    monkeypatch.setattr("optimuspy.ui.SETTINGS_PATH", path)
    return path


@pytest.fixture
def ui_server(tmp_path, monkeypatch):
    """Start the UI's request handler on a free port, against a throwaway config.ini.

    Returns `start(ini_text, source="default") -> (base_url, ini_path)`, where
    `source` is where the config.ini in use came from. The test runs inside
    `tmp_path`, so the `results/`, `configs/` and `config/` folders the UI reads
    and writes are the test's own. Every server started is shut down afterwards.
    """
    from http.server import ThreadingHTTPServer
    from optimuspy import ui

    monkeypatch.chdir(tmp_path)
    servers = []

    def start(ini_text, source="default"):
        ini = tmp_path / "config.ini"
        ini.write_text(ini_text, encoding="utf-8")
        monkeypatch.setattr(ui, "_config_ini_path", str(ini))
        monkeypatch.setattr(ui, "_config_source", source)
        server = ThreadingHTTPServer(("127.0.0.1", 0), ui.OptimusPyHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}", ini

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()
