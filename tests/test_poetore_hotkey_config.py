import json
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow, _hotkey_key_name
from src.ui.settings_dialog import SettingsDialog


def test_alt_d_is_default_poetore_capture_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["poetore_capture"] == "alt+d"


def test_ctrl_d_is_default_poetore_auto_hide_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["poetore_auto_hide"] == "ctrl+d"


def test_alt_f_is_default_map_check_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["map_check"] == "alt+f"


def test_shift_space_is_default_cheat_sheets_toggle_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["cheat_sheets_toggle"] == "shift+space"


def test_default_hotkeys_prioritize_vendor_search_and_chat_exit():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)

    assert config["hotkeys"]["lap"] == "none"
    assert config["hotkeys"]["logout"] == "none"
    assert config["hotkeys"]["exit"] == "F5"
    assert config["hotkeys"]["undo_lap"] == "none"
    assert config["hotkeys"]["search_string_test"] == "F4"


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
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)

    MainWindow.register_hotkeys(window)
    f4 = SimpleNamespace(name="f4")
    callbacks["on_press"](f4)
    callbacks["on_press"](f4)

    assert emitted == ["search_string_test"]


def test_main_mode_blocks_restricted_actions_but_keeps_passive_actions_outside_poe(
    monkeypatch,
):
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
    allowed_outside_poe = {"start_stop", "lap", "click_through", "cheat_sheets_toggle"}
    window = SimpleNamespace(
        config={"hotkeys": {
            "search_string_test": "F4",
            "start_stop": "F7",
            "lap": "F9",
            "click_through": "F6",
            "cheat_sheets_toggle": "shift+space",
        }},
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
        _hotkey_action_allowed=lambda action: action in allowed_outside_poe,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)

    MainWindow.register_hotkeys(window)
    callbacks["on_press"](SimpleNamespace(name="f4"))
    callbacks["on_press"](SimpleNamespace(name="f7"))
    callbacks["on_press"](SimpleNamespace(name="f9"))
    callbacks["on_press"](SimpleNamespace(name="f6"))
    callbacks["on_press"](SimpleNamespace(name="shift"))
    callbacks["on_press"](SimpleNamespace(name="space"))

    assert emitted == [
        "start_stop", "lap", "click_through", "cheat_sheets_toggle",
    ]


def test_f2_starts_and_releases_gem_shop_hold(monkeypatch):
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
        config={"hotkeys": {"gem_shop_search": "F2"}},
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)

    MainWindow.register_hotkeys(window)
    f2 = SimpleNamespace(name="f2")
    callbacks["on_press"](f2)
    callbacks["on_release"](f2)

    assert emitted == ["gem_shop_search_pressed", "gem_shop_search_released"]


def test_main_mode_waits_for_all_poetore_hotkey_keys_to_be_released(monkeypatch):
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
        config={"hotkeys": {"poetore_capture": "alt+d"}},
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)

    MainWindow.register_hotkeys(window)
    alt = SimpleNamespace(name="alt")
    d_key = SimpleNamespace(char="d", vk=ord("D"))
    callbacks["on_press"](alt)
    callbacks["on_press"](d_key)
    callbacks["on_release"](alt)
    assert emitted == ["poetore_capture"]
    callbacks["on_release"](d_key)
    assert emitted == ["poetore_capture", "poetore_capture_released"]


def test_main_mode_emits_auto_hide_release_separately(monkeypatch):
    callbacks = {}

    class FakeListener:
        def __init__(self, on_press, on_release):
            callbacks["on_press"] = on_press
            callbacks["on_release"] = on_release
        def start(self): pass
        def stop(self): pass

    emitted = []
    window = SimpleNamespace(
        config={"hotkeys": {"poetore_auto_hide": "ctrl+d"}},
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)
    MainWindow.register_hotkeys(window)
    callbacks["on_press"](SimpleNamespace(name="ctrl"))
    callbacks["on_press"](SimpleNamespace(char="d", vk=ord("D")))
    callbacks["on_release"](SimpleNamespace(char="d", vk=ord("D")))
    callbacks["on_release"](SimpleNamespace(name="ctrl"))
    assert emitted == ["poetore_auto_hide", "poetore_auto_hide_released"]


def test_main_mode_emits_map_check_release_separately(monkeypatch):
    callbacks = {}

    class FakeListener:
        def __init__(self, on_press, on_release):
            callbacks["on_press"] = on_press
            callbacks["on_release"] = on_release
        def start(self): pass
        def stop(self): pass

    emitted = []
    window = SimpleNamespace(
        config={"hotkeys": {"map_check": "alt+f"}}, keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)
    MainWindow.register_hotkeys(window)
    callbacks["on_press"](SimpleNamespace(name="alt"))
    callbacks["on_press"](SimpleNamespace(char="f", vk=ord("F")))
    callbacks["on_release"](SimpleNamespace(char="f", vk=ord("F")))
    callbacks["on_release"](SimpleNamespace(name="alt"))
    assert emitted == ["map_check", "map_check_released"]


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
        assert dialog.poetore_auto_hide_btn.key_text == "ctrl+d"
        assert dialog.map_check_btn.key_text == "alt+f"
        assert dialog.cheat_sheets_toggle_btn.key_text == "shift+space"
        assert dialog.exit_btn.key_text == "F5"
        assert dialog.undo_lap_btn.key_text == "none"
        dialog.poetore_capture_btn.key_text = "Alt+Q"
        dialog.poetore_auto_hide_btn.key_text = "Ctrl+Q"
        dialog.cheat_sheets_toggle_btn.key_text = "Ctrl+Space"
        dialog.exit_btn.key_text = "Ctrl+F5"
        assert dialog.get_settings()["hotkeys"]["poetore_capture"] == "Alt+Q"
        assert dialog.get_settings()["hotkeys"]["poetore_auto_hide"] == "Ctrl+Q"
        assert dialog.get_settings()["hotkeys"]["cheat_sheets_toggle"] == "Ctrl+Space"
        assert dialog.get_settings()["hotkeys"]["exit"] == "Ctrl+F5"
    finally:
        dialog.close()
        app.processEvents()
