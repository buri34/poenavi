from types import SimpleNamespace

from src.utils.global_hotkeys import (
    ForegroundSuppressedHotkeyService,
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


def test_alt_auto_hide_waits_for_selected_hold_key_release():
    listeners = []
    service = GlobalHotkeyService(
        {"poetore_auto_hide": "alt+q"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    listeners[0].on_press(SimpleNamespace(name="alt"))
    listeners[0].on_press(SimpleNamespace(char="q", vk=ord("Q")))
    listeners[0].on_release(SimpleNamespace(char="q", vk=ord("Q")))
    assert emitted == ["poetore_auto_hide"]

    listeners[0].on_release(SimpleNamespace(name="alt"))
    assert emitted == ["poetore_auto_hide", "poetore_auto_hide_released"]


def test_auto_hide_ignores_internal_copy_releases_then_detects_physical_hold_release(
    monkeypatch,
):
    listeners = []
    internal = {"active": False}
    monkeypatch.setattr(
        "src.utils.global_hotkeys.is_internal_key_input",
        lambda: internal["active"],
    )
    service = GlobalHotkeyService(
        {"poetore_auto_hide": "ctrl+d"},
        listener_factory=lambda **kwargs: listeners.append(FakeListener(**kwargs)) or listeners[-1],
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()

    listeners[0].on_press(SimpleNamespace(name="ctrl"))
    listeners[0].on_press(SimpleNamespace(char="d", vk=ord("D")))
    internal["active"] = True
    listeners[0].on_release(SimpleNamespace(char="d", vk=ord("D")))
    listeners[0].on_press(SimpleNamespace(name="ctrl"))
    listeners[0].on_press(SimpleNamespace(char="c", vk=ord("C")))
    listeners[0].on_release(SimpleNamespace(char="c", vk=ord("C")))
    listeners[0].on_release(SimpleNamespace(name="ctrl"))
    internal["active"] = False
    assert emitted == ["poetore_auto_hide"]

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



class FakeNativeHook:
    def __init__(self, hotkey, *, should_suppress, on_event):
        self.hotkey = hotkey
        self.should_suppress = should_suppress
        self.on_event = on_event
        self.is_running = False

    def start(self): self.is_running = True
    def stop(self): self.is_running = False
    def press(self):
        if not self.should_suppress(): return False
        self.on_event("pressed")
        return True
    def release(self): self.on_event("released")


class FakeNativeHookFactory:
    def __init__(self): self.hooks = []
    def __call__(self, *args, **kwargs):
        hook = FakeNativeHook(*args, **kwargs)
        self.hooks.append(hook)
        return hook


def make_suppressed(factory, foreground, **kwargs):
    return ForegroundSuppressedHotkeyService(
        "poetore_capture", "alt+d", native_hook_factory=factory,
        foreground_getter=lambda: foreground["hwnd"], platform="win32", **kwargs,
    )


def test_suppressed_hotkey_passes_outside_and_dispatches_in_poe():
    factory, foreground = FakeNativeHookFactory(), {"hwnd": 20}
    service = make_suppressed(factory, foreground, poe_window_checker=lambda h: h == 10)
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    hook = factory.hooks[-1]
    assert hook.press() is False
    foreground["hwnd"] = 10
    service._refresh_foreground_context()
    assert hook.press() is True
    hook.release()
    assert emitted == ["poetore_capture", "poetore_capture_released"]
    service.stop()
    assert not hook.is_running


def test_suppressed_hotkey_remains_usable_for_repeated_searches():
    factory, foreground = FakeNativeHookFactory(), {"hwnd": 10}
    service = make_suppressed(factory, foreground, poe_window_checker=lambda h: h == 10)
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    hook = factory.hooks[-1]
    for _ in range(3):
        assert hook.press() is True
        hook.release()
    assert emitted == ["poetore_capture", "poetore_capture_released"] * 3
    assert len(factory.hooks) == 1
    service.stop()


def test_suppressed_hotkey_focuses_poe_from_result_before_dispatch():
    factory, foreground, focused = FakeNativeHookFactory(), {"hwnd": 20}, []
    service = make_suppressed(
        factory, foreground, poe_window_checker=lambda h: h == 10,
        result_window_checker=lambda h: h == 20, poe_target_getter=lambda: 10,
        focus_target=lambda h: focused.append(h) or True,
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    hook = factory.hooks[-1]
    assert hook.press() is True
    hook.release()
    assert focused == [10]
    assert emitted == ["poetore_capture", "poetore_capture_released"]
    service.stop()


def test_suppressed_hotkey_does_not_dispatch_when_focus_fails():
    factory, foreground = FakeNativeHookFactory(), {"hwnd": 20}
    service = make_suppressed(
        factory, foreground, poe_window_checker=lambda h: h == 10,
        result_window_checker=lambda h: h == 20, poe_target_getter=lambda: 10,
        focus_target=lambda _h: False,
    )
    emitted = []
    service.command.connect(emitted.append)
    service.start()
    hook = factory.hooks[-1]
    assert hook.press() is True
    hook.release()
    assert emitted == []
    service.stop()


def test_suppressed_hotkey_callback_uses_cached_context_only():
    factory, foreground, calls = FakeNativeHookFactory(), {"hwnd": 20}, []
    service = make_suppressed(
        factory, foreground,
        poe_window_checker=lambda h: h == 10,
    )
    original_getter = service._foreground_getter
    service._foreground_getter = lambda: calls.append(True) or original_getter()
    service.start()
    initial_calls = len(calls)
    assert factory.hooks[-1].press() is False
    assert len(calls) == initial_calls
    foreground["hwnd"] = 10
    service._refresh_foreground_context()
    refreshed_calls = len(calls)
    assert factory.hooks[-1].press() is True
    assert len(calls) == refreshed_calls
    service.stop()


def test_suppressed_hotkey_is_disabled_on_non_windows():
    factory = FakeNativeHookFactory()
    service = ForegroundSuppressedHotkeyService(
        "poetore_capture", "alt+d", native_hook_factory=factory, platform="darwin",
    )
    service.start()
    assert service.is_running and not service.is_registered
    assert factory.hooks == []
    service.stop()
