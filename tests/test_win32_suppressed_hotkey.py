import sys

import pytest

from src.utils.win32_suppressed_hotkey import (
    HotkeyEventProcessor,
    VK_CONTROL,
    VK_LMENU,
    VK_MENU,
    _parse_hotkey,
    Win32SuppressedHotkeyHook,
)


def test_parse_hotkey_accepts_required_modifier_and_regular_key():
    assert _parse_hotkey("Alt+D") == (VK_MENU, ord("D"))
    assert _parse_hotkey("ctrl+1") == (VK_CONTROL, ord("1"))
    assert _parse_hotkey("ctrl+F5") == (VK_CONTROL, 0x74)
    assert _parse_hotkey("alt+Space") == (VK_MENU, 0x20)


@pytest.mark.parametrize("hotkey", ["d", "shift+d", "alt+escape", "ctrl+"])
def test_parse_hotkey_rejects_unsupported_bindings(hotkey):
    with pytest.raises(ValueError):
        _parse_hotkey(hotkey)


def test_processor_suppresses_target_only_in_allowed_context():
    allowed = {"value": False}
    events = []
    processor = HotkeyEventProcessor(
        VK_MENU, ord("D"), lambda: allowed["value"], events.append,
    )

    assert processor.process(VK_LMENU, True) is False
    assert processor.process(ord("D"), True) is False
    assert processor.process(ord("D"), False) is False

    allowed["value"] = True
    assert processor.process(ord("D"), True) is True
    assert processor.process(ord("D"), True) is True  # auto-repeat
    assert processor.process(ord("D"), False) is True
    assert processor.process(VK_LMENU, False) is False
    assert events == ["pressed", "released"]


def test_processor_ignores_injected_copy_input():
    events = []
    processor = HotkeyEventProcessor(
        VK_CONTROL, ord("C"), lambda: True, events.append,
    )
    processor.process(VK_CONTROL, True, injected=True)
    assert processor.process(ord("C"), True, injected=True) is False
    assert events == []


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 hook smoke test")
def test_native_hook_can_start_and_stop_on_windows():
    hook = Win32SuppressedHotkeyHook(
        "alt+f24", should_suppress=lambda: False, on_event=lambda _event: None,
    )
    hook.start()
    assert hook.is_running
    hook.stop()
    assert not hook.is_running
