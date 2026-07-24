import json

from PySide6.QtWidgets import QApplication

from src.ui.main_window import _hotkey_key_name
from src.ui.settings_dialog import SettingsDialog


def test_alt_d_is_default_poetore_capture_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["poetore_capture"] == "alt+d"


def test_shift_space_is_default_cheat_sheets_toggle_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["cheat_sheets_toggle"] == "shift+space"


def test_f4_is_default_exit_hotkey_and_undo_lap_is_unassigned():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)

    assert config["hotkeys"]["exit"] == "F4"
    assert config["hotkeys"]["undo_lap"] == "none"
    assert config["hotkeys"]["search_string_test"] == "none"


def test_ctrl_letter_control_character_is_normalized_to_letter():
    class CtrlDKey:
        char = "\x04"
        vk = ord("D")

    assert _hotkey_key_name(CtrlDKey()) == "d"


def test_regular_and_function_hotkey_names_are_preserved():
    class AltEKey:
        char = "e"
        vk = ord("E")

    class F3Key:
        name = "f3"

    assert _hotkey_key_name(AltEKey()) == "e"
    assert _hotkey_key_name(F3Key()) == "f3"


def test_settings_dialog_can_change_poetore_capture_hotkey(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "src.ui.settings_dialog.load_guide_data",
        lambda _version, **_kwargs: {},
    )
    monkeypatch.setattr(
        "src.ui.settings_dialog.load_zone_master_data",
        lambda: {
            "zone_data_by_version": {"poe1": {}, "poe2": {}},
            "town_zones_by_version": {"poe1": [], "poe2": []},
        },
    )
    monkeypatch.setattr(
        SettingsDialog,
        "_rebuild_zone_tab",
        lambda self: None,
    )
    monkeypatch.setattr(
        "src.ui.settings_dialog.save_zone_master_data",
        lambda *_args, **_kwargs: None,
    )

    dialog = SettingsDialog(
        current_config={
            "hotkeys": {"poetore_capture": "Ctrl+Shift+P"},
            "poe_version": "poe1",
            "poe_version_mode": "ask",
        }
    )
    try:
        assert dialog.poetore_capture_btn.key_text == "Ctrl+Shift+P"
        assert dialog.cheat_sheets_toggle_btn.key_text == "shift+space"
        assert dialog.exit_btn.key_text == "F4"
        assert dialog.undo_lap_btn.key_text == "none"
        dialog.poetore_capture_btn.key_text = "Alt+Q"
        dialog.cheat_sheets_toggle_btn.key_text = "Ctrl+Space"
        dialog.exit_btn.key_text = "Ctrl+F4"
        assert dialog.get_settings()["hotkeys"]["poetore_capture"] == "Alt+Q"
        assert dialog.get_settings()["hotkeys"]["cheat_sheets_toggle"] == "Ctrl+Space"
        assert dialog.get_settings()["hotkeys"]["exit"] == "Ctrl+F4"
    finally:
        dialog.close()
        app.processEvents()
