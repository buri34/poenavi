import json
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow, _hotkey_key_name
from src.ui.settings_dialog import AutoHideHotkeyWidget, SettingsDialog
from src.utils.poe_version_data import POE2


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


def test_stash_tab_scroll_is_enabled_by_default():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["stash_tab_scroll_enabled"] is True


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


def test_main_mode_uses_suppressed_service_for_capture_hotkey(monkeypatch):
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
    suppressed_instances = []

    class FakeSignal:
        def __init__(self):
            self.connected = None

        def connect(self, callback):
            self.connected = callback

    class FakeSuppressedService:
        def __init__(self, action, hotkey, parent=None, **kwargs):
            self.action = action
            self.hotkey = hotkey
            self.parent = parent
            self.options = kwargs
            self.command = FakeSignal()
            self.started = False
            suppressed_instances.append(self)

        def start(self):
            self.started = True

        def stop(self):
            pass
    window = SimpleNamespace(
        config={"hotkeys": {"poetore_capture": "alt+d"}},
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=emitted.append),
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)
    monkeypatch.setattr(
        "src.ui.main_window.ForegroundSuppressedHotkeyService",
        FakeSuppressedService,
    )
    monkeypatch.setattr(
        "src.ui.main_window.suppressed_hotkeys_supported", lambda: True,
    )

    MainWindow.register_hotkeys(window)
    assert "poetore_capture" not in window.hotkey_map.values()
    assert len(suppressed_instances) == 1
    service = suppressed_instances[0]
    assert (service.action, service.hotkey, service.parent) == (
        "poetore_capture", "alt+d", None,
    )
    assert callable(service.options["result_window_checker"])
    assert callable(service.options["poe_target_getter"])
    assert service.command.connected is window.hotkey_signal.emit
    assert service.started


def test_main_mode_does_not_register_poetore_hotkeys_in_poe2(monkeypatch):
    class FakeListener:
        def __init__(self, on_press, on_release):
            self.on_press = on_press
            self.on_release = on_release

        def start(self):
            pass

        def stop(self):
            pass

    window = SimpleNamespace(
        config={
            "poe_version": POE2,
            "hotkeys": {
                "poetore_capture": "alt+d",
                "poetore_auto_hide": "ctrl+d",
                "map_check": "alt+f",
            },
        },
        keyboard_listener=None,
        hotkey_signal=SimpleNamespace(emit=lambda _action: None),
        _hotkey_action_allowed=lambda _action: True,
    )
    monkeypatch.setattr("src.ui.main_window.pynput_keyboard.Listener", FakeListener)

    MainWindow.register_hotkeys(window)

    assert "poetore_capture" not in window.hotkey_map.values()
    assert "poetore_auto_hide" not in window.hotkey_map.values()
    assert "map_check" in window.hotkey_map.values()


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
        assert dialog.poetore_capture_btn.key_text == "ctrl+P"
        assert dialog.poetore_capture_btn.ctrl_button.isChecked()
        assert dialog.poetore_capture_btn.key_button.key_text == "P"
        assert dialog.poetore_auto_hide_btn.key_text == "ctrl+d"
        assert dialog.poetore_auto_hide_btn.ctrl_button.isChecked()
        assert dialog.poetore_auto_hide_btn.key_button.key_text == "d"
        assert dialog.poetore_auto_hide_btn.ctrl_button.width() == 48
        assert dialog.poetore_auto_hide_btn.alt_button.width() == 48
        assert dialog.poetore_capture_btn.width() == AutoHideHotkeyWidget.INPUT_WIDTH
        assert dialog.poetore_auto_hide_btn.width() == AutoHideHotkeyWidget.INPUT_WIDTH
        assert "#B0FF7B" in dialog.poetore_auto_hide_btn.ctrl_button.styleSheet()
        assert "#49D6B0" not in dialog.poetore_auto_hide_btn.ctrl_button.styleSheet()
        assert (
            dialog.poetore_auto_hide_btn.key_button.width()
            > dialog.poetore_auto_hide_btn.ctrl_button.width()
        )
        assert dialog.map_check_btn.key_text == "alt+f"
        assert dialog.cheat_sheets_toggle_btn.key_text == "shift+space"
        assert dialog.exit_btn.key_text == "F5"
        assert dialog.undo_lap_btn.key_text == "none"
        assert dialog.stash_tab_scroll_enabled_cb.isChecked()
        assert "スタッシュ外" in dialog.stash_tab_scroll_enabled_cb.text()
        dialog.poetore_capture_btn.set_modifier("alt")
        dialog.poetore_capture_btn.set_key("Q")
        dialog.poetore_auto_hide_btn.set_modifier("alt")
        dialog.poetore_auto_hide_btn.set_key("Q")
        dialog.cheat_sheets_toggle_btn.key_text = "Ctrl+Space"
        dialog.exit_btn.key_text = "Ctrl+F5"
        dialog.stash_tab_scroll_enabled_cb.setChecked(False)
        assert dialog.get_settings()["hotkeys"]["poetore_capture"] == "alt+Q"
        assert dialog.get_settings()["hotkeys"]["poetore_auto_hide"] == "alt+Q"
        assert dialog.get_settings()["hotkeys"]["cheat_sheets_toggle"] == "Ctrl+Space"
        assert dialog.get_settings()["hotkeys"]["exit"] == "Ctrl+F5"
        assert dialog.get_settings()["stash_tab_scroll_enabled"] is False
    finally:
        dialog.close()
        app.processEvents()
