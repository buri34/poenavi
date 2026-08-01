from types import SimpleNamespace

from src.utils.global_hotkeys import (
    GlobalHotkeyService,
    find_duplicate_hotkeys,
    hotkey_key_name,
)


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


def test_alt_w_is_available_to_close_passive_poetore_window():
    listener_box = []

    def factory(**kwargs):
        listener = FakeListener(**kwargs)
        listener_box.append(listener)
        return listener

    service = GlobalHotkeyService({}, listener_factory=factory)
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    listener_box[0].on_press(SimpleNamespace(name="alt"))
    listener_box[0].on_press(SimpleNamespace(char="w", vk=ord("W")))

    assert emitted == ["poetore_close"]
