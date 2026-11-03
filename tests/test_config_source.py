"""Settings chooses the config.ini by link or by copy, and never edits one.

The UI runs inside tmp_path (the `ui_server` fixture), so OptimusPy's own copy is
tmp_path/config/config.ini and the settings file is tmp_path/config/settings.ini.
"""
import json
import logging
import types
import urllib.error
import urllib.request

import pytest

from optimuspy import ui
from optimuspy.core import DEFAULT_PORT, load_settings, save_setting

INI = (
    "[tm1srv01]\n"
    "address=localhost\n"
    "port=8001\n"
    "user=admin\n"
    "password=secret\n"
    "ssl=True\n"
)
# What RushTI's config.ini might hold: comments and an order worth keeping.
SHARED_INI = (
    "; shared with RushTI\n"
    "[tm1srv02]\n"
    "address = localhost\n"
    "port = 8002\n"
    "# user is the service account\n"
    "user = admin\n"
)


def _request(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        with e:
            return e.code, json.loads(e.read().decode())


def _shared(tmp_path, name="rushti/config.ini"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SHARED_INI, encoding="utf-8")
    return path


def _own(tmp_path):
    return tmp_path / "config" / "config.ini"


# --- what Settings shows --------------------------------------------------------

def test_the_instances_come_with_the_file_in_use(ui_server, tmp_path):
    base, ini = ui_server(INI)
    status, payload = _request("GET", f"{base}/api/instances")
    assert status == 200
    assert payload == {"instances": ["tm1srv01"], "config_path": str(ini), "source": "default",
                       "own_copy_exists": False, "error": None}


def test_a_linked_file_that_is_gone_is_reported(ui_server, tmp_path):
    base, ini = ui_server(INI, source="linked")
    ini.unlink()
    status, payload = _request("GET", f"{base}/api/instances")
    assert status == 200
    assert payload["instances"] == []
    assert str(ini) in payload["error"]


def test_a_file_that_does_not_parse_is_reported(ui_server):
    base, _ = ui_server("address=localhost\n")
    _, payload = _request("GET", f"{base}/api/instances")
    assert payload["instances"] == []
    assert "section" in payload["error"].lower()


def test_a_default_file_that_does_not_exist_yet_is_the_empty_state(ui_server):
    base, ini = ui_server(INI)
    ini.unlink()
    _, payload = _request("GET", f"{base}/api/instances")
    assert payload["instances"] == [] and payload["error"] is None


def test_an_instance_is_shown_without_its_secrets(ui_server):
    base, _ = ui_server(INI)
    status, payload = _request("GET", f"{base}/api/instance/tm1srv01")
    assert status == 200
    assert payload["params"]["user"] == "admin"
    assert "password" not in payload["params"]


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/instances", {"name": "new", "params": {}}),
    ("POST", "/api/instance/tm1srv01", {"params": {"port": "9999"}}),
    ("DELETE", "/api/instance/tm1srv01", None),
    ("DELETE", "/api/instance/tm1srv01/field/port", None),
])
def test_nothing_edits_config_ini(ui_server, method, path, body):
    base, ini = ui_server(INI)
    status, _ = _request(method, f"{base}{path}", body)
    assert status == 404
    assert ini.read_text(encoding="utf-8") == INI


# --- link ---------------------------------------------------------------------

def test_a_link_is_remembered_for_the_cli_and_used_at_once(ui_server, tmp_path):
    base, _ = ui_server(INI)
    shared = _shared(tmp_path)
    status, payload = _request("POST", f"{base}/api/config-source", {"mode": "link", "path": str(shared)})
    assert status == 200, payload
    assert payload["instances"] == ["tm1srv02"]
    assert payload["source"] == "linked"
    assert load_settings()["config_ini"] == str(shared)
    assert ui._config_ini_path == str(shared)


def test_a_folder_means_the_config_ini_inside_it(ui_server, tmp_path):
    base, _ = ui_server(INI)
    shared = _shared(tmp_path)
    status, _ = _request("POST", f"{base}/api/config-source", {"mode": "link", "path": str(shared.parent)})
    assert status == 200
    assert load_settings()["config_ini"] == str(shared)


@pytest.mark.parametrize("typed", ['"{}"', "'{}'", "  {}  ", ' "{}" '])
def test_a_pasted_path_loses_its_quotes_and_spaces(ui_server, tmp_path, typed):
    base, _ = ui_server(INI)
    shared = _shared(tmp_path)
    status, _ = _request("POST", f"{base}/api/config-source",
                         {"mode": "link", "path": typed.format(shared)})
    assert status == 200
    assert load_settings()["config_ini"] == str(shared)


@pytest.mark.parametrize("mode", ["link", "copy"])
@pytest.mark.parametrize("content,reason", [
    (None, "no such file"),
    ("", "no instance sections"),
    ("address=localhost\n", "can't be read"),
])
def test_a_path_that_is_not_a_config_ini_is_refused_by_name(ui_server, tmp_path, mode, content, reason):
    base, _ = ui_server(INI)
    target = tmp_path / "elsewhere" / "config.ini"
    if content is not None:
        target.parent.mkdir()
        target.write_text(content, encoding="utf-8")
    status, payload = _request("POST", f"{base}/api/config-source", {"mode": mode, "path": str(target)})
    assert status == 400
    assert str(target) in payload["error"] and reason in payload["error"]
    assert load_settings() == {}
    assert not _own(tmp_path).exists()


def test_an_empty_path_is_refused(ui_server):
    base, _ = ui_server(INI)
    status, _ = _request("POST", f"{base}/api/config-source", {"mode": "link", "path": "  "})
    assert status == 400


def test_an_unknown_mode_is_refused(ui_server):
    base, _ = ui_server(INI)
    status, _ = _request("POST", f"{base}/api/config-source", {"mode": "edit"})
    assert status == 400


# --- copy and own ---------------------------------------------------------------

def test_a_copy_is_the_file_byte_for_byte(ui_server, tmp_path):
    base, _ = ui_server(INI)
    shared = _shared(tmp_path)
    save_setting("config_ini", str(shared))
    status, payload = _request("POST", f"{base}/api/config-source", {"mode": "copy", "path": str(shared)})
    assert status == 200, payload
    assert _own(tmp_path).read_bytes() == shared.read_bytes()
    assert payload["source"] == "default" and payload["instances"] == ["tm1srv02"]
    assert "config_ini" not in load_settings()


def test_a_copy_asks_before_it_replaces_the_own_copy(ui_server, tmp_path):
    base, _ = ui_server(INI)
    _own(tmp_path).parent.mkdir()
    _own(tmp_path).write_text(INI, encoding="utf-8")
    shared = _shared(tmp_path)

    status, payload = _request("POST", f"{base}/api/config-source", {"mode": "copy", "path": str(shared)})
    assert status == 409 and payload["exists"] is True
    assert _own(tmp_path).read_text(encoding="utf-8") == INI

    status, _ = _request("POST", f"{base}/api/config-source",
                         {"mode": "copy", "path": str(shared), "overwrite": True})
    assert status == 200
    assert _own(tmp_path).read_bytes() == shared.read_bytes()


@pytest.mark.parametrize("typed", ["config/config.ini", "config"])
def test_the_own_copy_is_never_copied_onto_itself(ui_server, tmp_path, typed):
    base, _ = ui_server(INI)
    _own(tmp_path).parent.mkdir()
    _own(tmp_path).write_text(INI, encoding="utf-8")
    status, _ = _request("POST", f"{base}/api/config-source",
                         {"mode": "copy", "path": str(tmp_path / typed), "overwrite": True})
    assert status == 400
    assert _own(tmp_path).read_text(encoding="utf-8") == INI


def test_going_back_to_the_own_copy_drops_the_link(ui_server, tmp_path):
    base, _ = ui_server(INI, source="linked")
    _own(tmp_path).parent.mkdir()
    _own(tmp_path).write_text(INI, encoding="utf-8")
    save_setting("config_ini", str(_shared(tmp_path)))
    status, payload = _request("POST", f"{base}/api/config-source", {"mode": "own"})
    assert status == 200
    assert payload["source"] == "default" and payload["own_copy_exists"] is True
    assert load_settings() == {}


def test_there_is_no_going_back_without_an_own_copy(ui_server, tmp_path):
    base, _ = ui_server(INI, source="linked")
    save_setting("config_ini", str(_shared(tmp_path)))
    status, _ = _request("POST", f"{base}/api/config-source", {"mode": "own"})
    assert status == 400
    assert "config_ini" in load_settings()


@pytest.mark.parametrize("body", [
    {"mode": "link", "path": "rushti/config.ini"},
    {"mode": "copy", "path": "rushti/config.ini", "overwrite": True},
    {"mode": "own"},
])
def test_a_file_set_by_the_flag_cannot_be_changed_here(ui_server, tmp_path, body):
    base, ini = ui_server(INI, source="flag")
    _shared(tmp_path)
    _own(tmp_path).parent.mkdir()
    _own(tmp_path).write_text(INI, encoding="utf-8")
    status, payload = _request("POST", f"{base}/api/config-source", body)
    assert status == 409
    assert "--config" in payload["error"]
    assert ui._config_ini_path == str(ini)
    assert load_settings() == {}


# --- starting the UI --------------------------------------------------------------

@pytest.fixture
def run_ui(monkeypatch, tmp_path):
    """ui.main with no server loop, no browser tab and no logfile.

    Returns `run(*argv) -> seen`, where `seen["port"]` is the port the server was
    given and `seen["opened"]` the URLs a browser was opened on.
    """
    seen = {"opened": []}

    class Server:
        def __init__(self, address, handler):
            seen["port"] = address[1]

        def serve_forever(self):
            raise KeyboardInterrupt

        def shutdown(self):
            pass

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ui, "ThreadingHTTPServer", Server)
    monkeypatch.setattr(ui, "configure_logging", lambda: None)
    monkeypatch.setattr(ui, "get_logfile_path", lambda: tmp_path / "optimuspy.log")
    monkeypatch.setattr(ui.webbrowser, "open", seen["opened"].append)
    monkeypatch.setattr(ui.threading, "Timer", lambda delay, fn: types.SimpleNamespace(start=fn))
    # main() sets these; put them back afterwards.
    monkeypatch.setattr(ui, "_config_ini_path", ui._config_ini_path)
    monkeypatch.setattr(ui, "_config_source", ui._config_source)

    def run(*argv):
        ui.main(list(argv))
        return seen
    return run


def test_the_port_is_the_flag_then_the_setting_then_the_default(run_ui):
    assert run_ui()["port"] == DEFAULT_PORT
    save_setting("ui_port", "9123")
    assert run_ui()["port"] == 9123
    assert run_ui("--port", "9200")["port"] == 9200


def test_an_invalid_port_setting_starts_on_the_default(run_ui, caplog):
    save_setting("ui_port", "99999")
    with caplog.at_level(logging.WARNING):
        assert run_ui()["port"] == DEFAULT_PORT
    assert "ui_port" in caplog.text


def test_the_browser_opens_unless_the_setting_says_not_to(run_ui):
    assert run_ui()["opened"] == [f"http://127.0.0.1:{DEFAULT_PORT}"]
    save_setting("open_browser", "false")
    assert run_ui()["opened"] == [f"http://127.0.0.1:{DEFAULT_PORT}"]  # no second tab


def test_the_ui_starts_on_a_linked_file_that_is_gone(run_ui, tmp_path, capsys):
    gone = tmp_path / "gone.ini"
    save_setting("config_ini", str(gone))
    run_ui()
    assert (ui._config_ini_path, ui._config_source) == (str(gone), "linked")
    assert str(gone) in capsys.readouterr().out


def test_the_ui_starts_on_the_linked_file(run_ui, tmp_path):
    shared = _shared(tmp_path)
    save_setting("config_ini", str(shared))
    run_ui()
    assert (ui._config_ini_path, ui._config_source) == (str(shared), "linked")
