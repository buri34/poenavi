from types import SimpleNamespace

from src.utils.global_hotkeys import (
    HOTKEY_ACTIONS_ALLOWED_OUTSIDE_POE,
    GlobalHotkeyService,
    find_duplicate_hotkeys,
    hotkey_key_name,
    is_hotkey_action_allowed,
)
from src.utils.internal_key_input import internal_key_input


class FakeListener:
    def __init__(self, on_press, on_release):
        self.on_press = on_press
        self.on_release = on_release
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_ctrl_control_character_is_normalized_to_letter():
    key = SimpleNamespace(char="\x04", vk=ord("D"))
    assert hotkey_key_name(key) == "d"


def test_duplicate_hotkeys_are_normalized_and_disabled_values_are_ignored():
    assert find_duplicate_hotkeys(
        {
            "exit": "F5",
            "capture": " f5 ",
            "disabled": "none",
            "empty": "",
        }
    ) == {"f5": ["exit", "capture"]}


def test_only_requested_passive_actions_are_allowed_outside_poe(monkeypatch):
    monkeypatch.setattr(
        "src.utils.global_hotkeys.is_path_of_exile_window", lambda _hwnd: False,
    )
    assert HOTKEY_ACTIONS_ALLOWED_OUTSIDE_POE == {
        "start_stop", "lap", "click_through",
        "cheat_sheets_toggle", "cheat_sheets_escape",
    }
    for action in HOTKEY_ACTIONS_ALLOWED_OUTSIDE_POE:
        assert is_hotkey_action_allowed(action, foreground_window=123)
    assert not is_hotkey_action_allowed("poetore_capture", foreground_window=123)
    assert not is_hotkey_action_allowed("custom_command:0", foreground_window=123)


def test_restricted_hotkeys_are_allowed_when_poe_is_foreground(monkeypatch):
    monkeypatch.setattr(
        "src.utils.global_hotkeys.is_path_of_exile_window", lambda hwnd: hwnd == 123,
    )
    assert is_hotkey_action_allowed("poetore_capture", foreground_window=123)
    assert not is_hotkey_action_allowed("poetore_capture", foreground_window=456)


def test_service_filters_disallowed_press_and_its_release():
    listeners = []
    service = GlobalHotkeyService(
        {"poetore_capture": "alt+d", "cheat_sheets_toggle": "shift+space"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
        action_filter=lambda action: action in HOTKEY_ACTIONS_ALLOWED_OUTSIDE_POE,
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    listeners[0].on_press(SimpleNamespace(name="alt"))
    listeners[0].on_press(SimpleNamespace(char="d", vk=ord("D")))
    listeners[0].on_release(SimpleNamespace(char="d", vk=ord("D")))
    listeners[0].on_release(SimpleNamespace(name="alt"))
    assert emitted == []

    listeners[0].on_press(SimpleNamespace(name="shift"))
    listeners[0].on_press(SimpleNamespace(name="space"))
    assert emitted == ["cheat_sheets_toggle"]


def test_service_registers_only_supplied_mode_actions():
    listeners = []

    def factory(**kwargs):
        listener = FakeListener(**kwargs)
        listeners.append(listener)
        return listener

    service = GlobalHotkeyService(
        {
            "poetore_capture": "alt+d",
            "cheat_sheets_toggle": "shift+space",
            "disabled": "none",
        },
        listener_factory=factory,
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    listeners[0].on_press(SimpleNamespace(name="alt"))
    listeners[0].on_press(SimpleNamespace(char="d", vk=ord("D")))
    listeners[0].on_press(SimpleNamespace(char="d", vk=ord("D")))

    assert service.registered_actions == {
        "poetore_capture",
        "cheat_sheets_toggle",
    }
    assert emitted == ["poetore_capture"]

    listeners[0].on_release(SimpleNamespace(char="d", vk=ord("D")))
    assert emitted == ["poetore_capture"]
    listeners[0].on_release(SimpleNamespace(name="alt"))
    assert emitted == ["poetore_capture", "poetore_capture_released"]


def test_capture_release_waits_for_every_key_regardless_of_release_order():
    listeners = []
    service = GlobalHotkeyService(
        {"poetore_capture": "ctrl+shift+p"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    listeners[0].on_press(SimpleNamespace(name="ctrl"))
    listeners[0].on_press(SimpleNamespace(name="shift"))
    listeners[0].on_press(SimpleNamespace(char="p", vk=ord("P")))
    listeners[0].on_release(SimpleNamespace(name="ctrl"))
    listeners[0].on_release(SimpleNamespace(name="shift"))
    assert emitted == ["poetore_capture"]
    listeners[0].on_release(SimpleNamespace(char="p", vk=ord("P")))
    assert emitted == ["poetore_capture", "poetore_capture_released"]


def test_auto_hide_capture_emits_its_own_release_notification():
    listeners = []
    service = GlobalHotkeyService(
        {"poetore_auto_hide": "ctrl+d"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    listeners[0].on_press(SimpleNamespace(name="ctrl"))
    listeners[0].on_press(SimpleNamespace(char="d", vk=ord("D")))
    listeners[0].on_release(SimpleNamespace(char="d", vk=ord("D")))
    listeners[0].on_release(SimpleNamespace(name="ctrl"))

    assert emitted == ["poetore_auto_hide", "poetore_auto_hide_released"]


def test_map_check_uses_its_own_release_notification():
    listeners = []
    service = GlobalHotkeyService(
        {"map_check": "alt+f"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    listeners[0].on_press(SimpleNamespace(name="alt"))
    listeners[0].on_press(SimpleNamespace(char="f", vk=ord("F")))
    listeners[0].on_release(SimpleNamespace(char="f", vk=ord("F")))
    listeners[0].on_release(SimpleNamespace(name="alt"))
    assert emitted == ["map_check", "map_check_released"]


def test_escape_is_available_for_common_cheat_sheet_overlay():
    listener_box = []

    def factory(**kwargs):
        listener = FakeListener(**kwargs)
        listener_box.append(listener)
        return listener

    service = GlobalHotkeyService({}, listener_factory=factory)
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    listener_box[0].on_press(SimpleNamespace(name="esc"))

    assert emitted == ["cheat_sheets_escape"]


def test_service_ignores_keys_sent_by_the_application():
    listeners = []
    service = GlobalHotkeyService(
        {"custom_command:0": "ctrl+c"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    with internal_key_input(cooldown_seconds=0):
        listeners[0].on_press(SimpleNamespace(name="ctrl"))
        listeners[0].on_press(SimpleNamespace(char="c", vk=ord("C")))
        listeners[0].on_release(SimpleNamespace(char="c", vk=ord("C")))
        listeners[0].on_release(SimpleNamespace(name="ctrl"))

    assert emitted == []

    listeners[0].on_press(SimpleNamespace(name="ctrl"))
    listeners[0].on_press(SimpleNamespace(char="c", vk=ord("C")))
    assert emitted == ["custom_command:0"]
