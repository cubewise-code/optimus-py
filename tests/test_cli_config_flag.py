import os
import subprocess
import sys
from pathlib import Path

import pytest

from optimuspy.cli import main


def test_cli_missing_config_exits_1(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "nope.ini"
    monkeypatch.setattr(
        sys, "argv",
        ["optimuspy", "scan", "--instance", "tm1srv01", "--config", str(missing)],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "not found" in capsys.readouterr().out.lower()


def test_cli_with_a_linked_file_that_is_gone_exits_1(monkeypatch, tmp_path, capsys):
    from optimuspy.core import save_setting

    gone = tmp_path / "gone.ini"
    save_setting("config_ini", str(gone))
    monkeypatch.setattr(sys, "argv", ["optimuspy", "scan", "--instance", "tm1srv01"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert (f"ERROR: config.ini not found: {gone} (linked from the UI's Settings page)"
            in capsys.readouterr().out)


def test_cli_reads_the_linked_file_without_a_flag(monkeypatch, tmp_path, capsys):
    from optimuspy.core import save_setting

    save_setting("config_ini", str(_write_config_ini(tmp_path)))
    monkeypatch.setattr(sys, "argv", ["optimuspy", "scan", "--instance", "nosuch"])
    code = main()
    out = capsys.readouterr().out
    assert code == 1
    assert f"ERROR: Instance 'nosuch' not found in {tmp_path / 'config.ini'}" in out


def _write_config_ini(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("[tm1srv01]\naddress=localhost\nport=8001\nuser=admin\npassword=apple\nssl=True\n")
    return ini


def _run_cli(monkeypatch, tmp_path, cube_config):
    import json

    cube_json = tmp_path / "cube.json"
    cube_json.write_text(json.dumps(cube_config))
    monkeypatch.setattr(
        sys, "argv",
        ["optimuspy", "optimize", str(cube_json),
         "--config", str(_write_config_ini(tmp_path))],
    )
    return main()


def test_tier1_config_error_prints_the_message_without_a_traceback(
        monkeypatch, tmp_path, capsys):
    # A malformed predefined order is a config error. The operator — often a TI
    # process reading only stdout — gets the message and exit 1, not a stack
    # trace. Offline: validate_cube_config runs before any TM1 connection.
    code = _run_cli(monkeypatch, tmp_path, {
        "instance": "tm1srv01", "cube": "Sales", "executions": 1, "output": "csv",
        "predefined_orders": [["Time", "Time", "Region"]],
    })

    out = capsys.readouterr().out
    assert code == 1
    # One line, the whole report: the banner precedes it, nothing follows it.
    assert out.rstrip().splitlines()[-1].startswith("ERROR: ")
    assert "repeats" in out
    assert "Traceback" not in out


def test_a_tier1_failure_raised_inside_the_run_is_caught_too(
        monkeypatch, tmp_path, capsys):
    # _validate_predefined_orders needs the cube's real dimension list, so it
    # raises from inside run_optimize rather than from validate_cube_config.
    # Both must reach the operator the same way.
    def _raises(**kwargs):
        raise ValueError("'predefined_orders[0]' names 'Prodcut', which is not a "
                         "dimension of cube 'Sales'")

    monkeypatch.setattr("optimuspy.cli.run_optimize", _raises)
    code = _run_cli(monkeypatch, tmp_path, {
        "instance": "tm1srv01", "cube": "Sales", "executions": 1, "output": "csv",
        "predefined_orders": [["Prodcut"]],
    })

    out = capsys.readouterr().out
    assert code == 1
    assert "Prodcut" in out
    assert "Traceback" not in out


def _capture_ui(monkeypatch):
    import optimuspy.ui
    seen = []
    monkeypatch.setattr(optimuspy.ui, "main", lambda argv=None: seen.append(argv))
    return seen


def test_ui_opens_the_web_ui_with_its_own_options(monkeypatch):
    seen = _capture_ui(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["optimuspy", "ui", "--port", "9123"])
    main()
    assert seen == [["--port", "9123"]]


def test_a_double_clicked_executable_opens_the_web_ui(monkeypatch):
    # A double-click starts the executable with no arguments.
    seen = _capture_ui(monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("optimuspy.cli.set_current_directory", lambda: None)
    monkeypatch.setattr(sys, "argv", ["optimuspy.exe"])
    main()
    assert seen == [[]]


def test_no_arguments_outside_the_executable_still_asks_for_a_mode(monkeypatch):
    seen = _capture_ui(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["optimuspy"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert seen == []


def test_the_ui_reads_the_options_it_is_given(monkeypatch, tmp_path, capsys):
    from optimuspy import ui
    monkeypatch.setattr(ui, "configure_logging", lambda: None)
    monkeypatch.setattr(ui, "get_logfile_path", lambda: tmp_path / "optimuspy.log")
    with pytest.raises(SystemExit) as exc:
        ui.main(["--config", str(tmp_path / "nope.ini")])
    assert exc.value.code == 1
    assert "not found" in capsys.readouterr().out.lower()


def test_the_banner_survives_a_console_that_cannot_encode_it(tmp_path):
    # On Windows a redirected stdout is cp1252, which has no box-drawing
    # characters. A TI process capturing the output must not kill the run.
    src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ, PYTHONPATH=str(src), PYTHONIOENCODING="cp1252")
    done = subprocess.run([sys.executable, "-m", "optimuspy.cli", "--help"],
                          cwd=tmp_path, env=env, capture_output=True)
    assert done.returncode == 0, done.stderr.decode("cp1252", "replace")
    assert b"optimize-db" in done.stdout


# --- an instance that is not in config.ini --------------------------------

def test_set_with_an_unknown_instance_is_a_one_line_error(monkeypatch, tmp_path, capsys):
    # set and optimize share core.main, so one of them covers both.
    import json

    cube_json = tmp_path / "cube.json"
    cube_json.write_text(json.dumps({
        "instance": "nosuch", "cube": "Sales", "executions": 1, "output": "csv",
        "predefined_orders": [["Time", "Region"]]}))
    monkeypatch.setattr(
        sys, "argv",
        ["optimuspy", "set", str(cube_json), "--config", str(_write_config_ini(tmp_path))])

    code = main()

    out = capsys.readouterr().out
    assert code == 1
    assert "ERROR: Instance 'nosuch' not found in" in out
    assert "Traceback" not in out


def test_scan_with_an_unknown_instance_is_a_one_line_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        sys, "argv",
        ["optimuspy", "scan", "--instance", "nosuch",
         "--config", str(_write_config_ini(tmp_path))])

    code = main()

    out = capsys.readouterr().out
    assert code == 1
    assert "ERROR: Instance 'nosuch' not found in" in out
    assert "Traceback" not in out


def test_tm1_params_applies_a_password_given_on_the_command_line(tmp_path):
    from optimuspy.core import APP_NAME, tm1_params

    params = tm1_params(str(_write_config_ini(tmp_path)), "tm1srv01", "plain-secret")

    assert params["address"] == "localhost"
    assert params["password"] == "plain-secret"
    assert params["decode_b64"] is False
    assert params["session_context"] == APP_NAME
