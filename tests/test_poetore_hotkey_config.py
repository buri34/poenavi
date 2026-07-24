import json
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow, _hotkey_key_name
from src.ui.settings_dialog import SettingsDialog


def test_alt_d_is_default_poetore_capture_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["poetore_capture"] == "alt+d"


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


def test_f4_key_repeat_opens_the_vendor_search_menu_once(monkeypatch):
    callbacks = {}

    class FakeListener:
        def __init__(self, on_press, on_release):
            callbacks["on_press"] = on_press
            callbacks["on_release"] = on_release

        def start(self):
            pass

        def stop(self):
            pass

    emitted = []
    window = SimpleNamespace(
        config={"hotkeys": {"search_string_test": "F4"}},
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)

    MainWindow.register_hotkeys(window)
    f4 = SimpleNamespace(name="f4")
    callbacks["on_press"](f4)
    callbacks["on_press"](f4)

    assert emitted == ["search_string_test"]


def test_settings_dialog_can_change_poetore_capture_hotkey(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "src.ui.settings_dialog.load_guide_data",
        lambda _version: {},
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
        dialog.poetore_capture_btn.key_text = "Alt+Q"
        assert dialog.get_settings()["hotkeys"]["poetore_capture"] == "Alt+Q"
    finally:
        dialog.close()
        app.processEvents()
