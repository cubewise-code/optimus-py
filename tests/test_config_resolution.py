"""Which config.ini is read, and the settings file that remembers the choice.

Every test here reads and writes the settings file under tmp_path (the
`settings_path` fixture in conftest).
"""
import configparser
import logging
import re
from pathlib import Path

import pytest

from optimuspy import core, ui
from optimuspy.core import (
    ConfigLocation, DEFAULT_CONFIG_INI, DEFAULT_PORT, load_settings, resolve_config_path,
    save_setting, setting_open_browser, setting_ui_port,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "settings.ini.example"


def _ini(tmp_path, name="shared.ini"):
    path = tmp_path / name
    path.write_text("[tm1srv01]\naddress=localhost\n", encoding="utf-8")
    return path


# --- which config.ini ---------------------------------------------------------

def test_with_nothing_chosen_it_is_the_default():
    assert resolve_config_path(None) == ConfigLocation(DEFAULT_CONFIG_INI, "default")


def test_a_linked_file_wins_over_the_default(tmp_path):
    linked = _ini(tmp_path)
    save_setting("config_ini", str(linked))
    assert resolve_config_path(None) == ConfigLocation(str(linked), "linked")


def test_the_flag_wins_over_a_linked_file(tmp_path):
    save_setting("config_ini", str(_ini(tmp_path, "linked.ini")))
    flag = _ini(tmp_path, "flag.ini")
    assert resolve_config_path(str(flag)) == ConfigLocation(str(flag), "flag")


def test_a_flag_that_names_no_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_config_path(str(tmp_path / "nope.ini"))


def test_a_linked_file_that_is_gone_is_still_returned(tmp_path):
    # The CLI reports it and the UI starts; neither is resolve's decision.
    gone = tmp_path / "gone.ini"
    save_setting("config_ini", str(gone))
    assert resolve_config_path(None) == ConfigLocation(str(gone), "linked")


# --- the settings file --------------------------------------------------------

def test_no_settings_file_is_no_settings(settings_path):
    assert not settings_path.exists()
    assert load_settings() == {}


def test_a_corrupt_settings_file_is_ignored_with_a_warning(settings_path, caplog):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("ui_port = 9000\n[optimuspy\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load_settings() == {}
        assert resolve_config_path(None).source == "default"
    assert str(settings_path) in caplog.text


def test_saving_a_setting_keeps_the_others(settings_path):
    save_setting("ui_port", "9000")
    save_setting("open_browser", "false")
    assert load_settings() == {"ui_port": "9000", "open_browser": "false"}


def test_saving_none_removes_the_key(settings_path):
    save_setting("ui_port", "9000")
    save_setting("open_browser", "false")
    save_setting("ui_port", None)
    assert load_settings() == {"open_browser": "false"}


def test_a_save_that_fails_midway_leaves_the_file_as_it_was(settings_path, monkeypatch):
    save_setting("ui_port", "9000")
    before = settings_path.read_bytes()

    def crash(self, f, *args, **kwargs):
        f.write("[optimuspy]\nui_po")
        raise OSError("disk full")

    monkeypatch.setattr(configparser.ConfigParser, "write", crash)
    with pytest.raises(OSError):
        save_setting("open_browser", "false")
    assert settings_path.read_bytes() == before
    assert [p.name for p in settings_path.parent.iterdir()] == ["settings.ini"]


def test_a_save_never_overwrites_a_file_it_cannot_parse(settings_path):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("hand edited, no section\n", encoding="utf-8")
    with pytest.raises(configparser.Error):
        save_setting("ui_port", "9000")
    assert settings_path.read_text(encoding="utf-8") == "hand edited, no section\n"


@pytest.mark.parametrize("value", ["9000", " 9000 "])
def test_ui_port_comes_from_the_file(value):
    save_setting("ui_port", value)
    assert setting_ui_port() == 9000


def test_ui_port_defaults():
    assert setting_ui_port() == DEFAULT_PORT


@pytest.mark.parametrize("value", ["0", "65536", "http", "80.5"])
def test_an_invalid_ui_port_falls_back_to_the_default(value, caplog):
    save_setting("ui_port", value)
    with caplog.at_level(logging.WARNING):
        assert setting_ui_port() == DEFAULT_PORT
    assert "ui_port" in caplog.text and value in caplog.text


@pytest.mark.parametrize("value,expected", [("false", False), ("no", False), ("0", False),
                                            ("true", True), ("yes", True)])
def test_open_browser_reads_as_a_boolean(value, expected):
    save_setting("open_browser", value)
    assert setting_open_browser() is expected


def test_an_invalid_open_browser_falls_back_to_true(caplog):
    save_setting("open_browser", "sometimes")
    with caplog.at_level(logging.WARNING):
        assert setting_open_browser() is True
    assert "open_browser" in caplog.text and "sometimes" in caplog.text


# --- config/settings.ini.example ----------------------------------------------

def _example_uncommented() -> str:
    """The example with every `# key = value` line made live."""
    return re.sub(r"^# (\w+ =.*)$", r"\1", EXAMPLE.read_text(encoding="utf-8"), flags=re.M)


def test_the_example_parses_and_sets_nothing():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(EXAMPLE.read_text(encoding="utf-8"))
    assert parser.sections() == ["optimuspy"]
    assert dict(parser["optimuspy"]) == {}


def test_every_key_in_the_example_is_commented_at_its_default(settings_path):
    live = configparser.ConfigParser(interpolation=None)
    live.read_string(_example_uncommented())
    assert set(live["optimuspy"]) == {
        "config_ini", "cube_configs_dir", "exports_dir", "ui_port", "open_browser"}

    # The same answers with no file and with the uncommented example.
    def answers():
        return (resolve_config_path(None), setting_ui_port(), setting_open_browser(),
                ui.cube_configs_dir(), ui.exports_dir())

    with_no_file = answers()
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(_example_uncommented(), encoding="utf-8")
    assert core.load_settings()["ui_port"] == "8765"
    assert answers() == with_no_file
