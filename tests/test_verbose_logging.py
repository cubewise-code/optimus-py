"""`-v` is the only thing that makes a skipped order's reason readable.

Every refusal the order frame issues — the locked slot, an ignored order, a
position rule — is reported at DEBUG. Before `-v` existed, `configure_logging`
hardcoded INFO and no CLI argument touched the level, so those lines were not
suppressed-by-default but unreachable at every flag. These tests pin the channel
open.

Offline, no fake: the measure_orders evaluator stands in for the server.
"""
import logging

import pytest

from optimuspy.core import configure_logging
from tests.conftest import install_offline_measurements
from tests.test_fold_a import make_main_executor

DIMS = ["D0", "D1", "D2", "M"]
CARD = {"D0": 100, "D1": 900, "D2": 8000, "M": 3}


class _Capture(logging.Handler):
    """Records whatever the root logger's level lets through, and nothing else.

    Deliberately not `caplog`: that fixture forces the root level to capture, so
    a test written around it would pass whether or not `-v` worked — which is
    the exact class of non-existent mitigation this task exists to remove.
    """

    def __init__(self):
        super().__init__(level=logging.NOTSET)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def captured(logging_sandbox):
    handler = _Capture()
    logging_sandbox.addHandler(handler)
    try:
        yield handler.records
    finally:
        logging_sandbox.removeHandler(handler)


@pytest.fixture
def logging_sandbox(monkeypatch, tmp_path):
    """Let a test configure the root logger without leaking the change."""
    # configure_logging writes to logs/ under the install dir; keep it out of the repo.
    monkeypatch.setattr("optimuspy.core.get_app_base_dir", lambda: tmp_path)
    root = logging.getLogger()
    before = root.level
    yield root
    root.setLevel(before)


def test_verbose_off_leaves_debug_unreachable(logging_sandbox):
    configure_logging(verbose=False)
    assert logging_sandbox.level == logging.INFO
    assert not logging_sandbox.isEnabledFor(logging.DEBUG)
    assert logging_sandbox.isEnabledFor(logging.INFO)


def test_verbose_on_opens_the_debug_channel(logging_sandbox):
    configure_logging(verbose=True)
    assert logging_sandbox.level == logging.DEBUG
    assert logging_sandbox.isEnabledFor(logging.DEBUG)


def test_configure_logging_does_not_stack_stdout_handlers(logging_sandbox):
    # It is called once per process today, but a second call must not double
    # every line on stdout.
    configure_logging()
    count = len(logging_sandbox.handlers)
    configure_logging(verbose=True)
    assert len(logging_sandbox.handlers) == count


@pytest.fixture
def bare_root_logger():
    """The root logger, with its handlers and level restored afterwards.

    The test itself empties the handlers: pytest adds its capture handler after
    fixtures run, and basicConfig does nothing while any handler is attached.
    """
    root = logging.getLogger()
    before_handlers, before_level = root.handlers[:], root.level
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers = before_handlers
    root.setLevel(before_level)


def test_the_log_is_written_under_the_install_dir(bare_root_logger, monkeypatch, tmp_path):
    # Not in the folder the command runs from: the log is always in one place.
    install_dir = tmp_path / "install"
    run_dir = tmp_path / "run"
    install_dir.mkdir()
    run_dir.mkdir()
    monkeypatch.setattr("optimuspy.core.get_app_base_dir", lambda: install_dir)
    monkeypatch.chdir(run_dir)

    bare_root_logger.handlers = []
    configure_logging()
    logging.info("a line for the logfile")
    for handler in bare_root_logger.handlers:
        handler.flush()

    log = install_dir / "logs" / "optimuspy.log"
    assert log.exists()
    assert "a line for the logfile" in log.read_text(encoding="utf-8")
    assert list(run_dir.iterdir()) == []


def _greedy_run(orders_to_ignore=None):
    """Run Fold A and return the orders it evaluated."""
    ex = make_main_executor(DIMS, CARD, orders_to_ignore=orders_to_ignore)
    log = []
    install_offline_measurements(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_a()
    return ex, log


def _skip_lines(records):
    return [r.getMessage() for r in records
            if r.levelno == logging.DEBUG and r.getMessage().startswith("Skipping order")]


def test_a_skipped_order_names_its_reason_at_verbose(captured):
    # Pick an order the sweep genuinely produces, so the skip is real rather
    # than arranged.
    _, evaluated = _greedy_run()
    doomed = evaluated[0]

    configure_logging(verbose=True)
    del captured[:]
    ex, log = _greedy_run(orders_to_ignore=[doomed])

    assert doomed not in log, "the order under test was evaluated, not skipped"
    assert ex.skipped_orders, "nothing was skipped — the test would prove nothing"

    skips = _skip_lines(captured)
    assert skips, "no skip line reached DEBUG"
    # The line has to carry the reason, not just the fact: it is the only record
    # of why an order the user expected to see tested is missing from the report.
    assert any("orders_to_ignore" in m for m in skips)
    assert any(str(doomed) in m for m in skips)


def test_the_same_run_says_nothing_at_the_default_level(captured):
    _, evaluated = _greedy_run()
    doomed = evaluated[0]

    configure_logging(verbose=False)
    del captured[:]
    ex, _ = _greedy_run(orders_to_ignore=[doomed])

    assert ex.skipped_orders, "nothing was skipped — the test would prove nothing"
    assert not _skip_lines(captured)


# --- the flag actually reaches configure_logging ---------------------------

def _run_cli(monkeypatch, tmp_path, extra_args):
    import json
    import sys

    from optimuspy.cli import main

    ini = tmp_path / "config.ini"
    ini.write_text("[tm1srv01]\naddress=localhost\nport=8001\nuser=admin\npassword=apple\n")
    cube_json = tmp_path / "cube.json"
    # A tier-1 config error, so the run returns before any TM1 connection.
    cube_json.write_text(json.dumps({
        "instance": "tm1srv01", "cube": "Sales", "executions": 1, "output": "csv",
        "predefined_orders": [["Time", "Time"]]}))
    monkeypatch.setattr(
        sys, "argv",
        ["optimuspy", "optimize", str(cube_json), "--config", str(ini)] + extra_args)
    return main()


@pytest.mark.parametrize("flag", ["-v", "--verbose"])
def test_the_cli_flag_opens_the_channel(logging_sandbox, monkeypatch, tmp_path, capsys, flag):
    assert _run_cli(monkeypatch, tmp_path, [flag]) == 1
    capsys.readouterr()
    assert logging_sandbox.level == logging.DEBUG


def test_the_cli_defaults_to_info(logging_sandbox, monkeypatch, tmp_path, capsys):
    assert _run_cli(monkeypatch, tmp_path, []) == 1
    capsys.readouterr()
    assert logging_sandbox.level == logging.INFO


def test_verbose_recovers_the_traceback_the_wide_catch_swallows(
        captured, monkeypatch, tmp_path, capsys):
    # cli.py catches (ValueError, FileNotFoundError) around the whole run, as
    # optimize-db does, so a ValueError raised deep inside a run prints one line
    # instead of a stack. That is only defensible if the stack is recoverable:
    # this is the test that keeps the mitigation honest.
    def _boom(**kwargs):
        raise ValueError("something deep went wrong")

    monkeypatch.setattr("optimuspy.cli.run_optimize", _boom)
    import json
    import sys

    from optimuspy.cli import main

    ini = tmp_path / "config.ini"
    ini.write_text("[tm1srv01]\naddress=localhost\n")
    cube_json = tmp_path / "cube.json"
    cube_json.write_text(json.dumps({
        "instance": "tm1srv01", "cube": "Sales", "executions": 1, "output": "csv"}))
    monkeypatch.setattr(
        sys, "argv",
        ["optimuspy", "optimize", str(cube_json), "--config", str(ini), "-v"])

    assert main() == 1
    capsys.readouterr()

    with_stack = [r for r in captured if r.levelno == logging.DEBUG and r.exc_info]
    assert with_stack, "the swallowed traceback was not recoverable at -v"
    assert "something deep went wrong" in str(with_stack[0].exc_info[1])
