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


def test_parse_hotkey_accepts_single_key_only_when_explicitly_enabled():
    assert _parse_hotkey("D", allow_unmodified=True) == (None, ord("D"))
    assert _parse_hotkey("F5", allow_unmodified=True) == (None, 0x74)
    with pytest.raises(ValueError):
        _parse_hotkey("D")


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


def test_processor_suppresses_unmodified_target_without_modifier():
    events = []
    processor = HotkeyEventProcessor(
        None, ord("D"), lambda: True, events.append,
    )
    assert processor.process(ord("D"), True) is True
    assert processor.process(ord("D"), True) is True
    assert processor.process(ord("D"), False) is True
    assert events == ["pressed", "released"]


def test_processor_does_not_treat_modified_key_as_unmodified_hotkey():
    events = []
    processor = HotkeyEventProcessor(
        None, ord("D"), lambda: True, events.append,
    )
    assert processor.process(VK_CONTROL, True) is False
    assert processor.process(ord("D"), True) is False
    assert processor.process(ord("D"), False) is False
    assert processor.process(VK_CONTROL, False) is False
    assert events == []


def test_processor_recognizes_injected_modifier_from_external_software():
    events = []
    processor = HotkeyEventProcessor(
        VK_MENU, ord("D"), lambda: True, events.append,
    )
    assert processor.process(VK_MENU, True, injected=True) is False
    assert processor.process(ord("D"), True) is True
    assert processor.process(ord("D"), False) is True
    assert processor.process(VK_MENU, False, injected=True) is False
    assert events == ["pressed", "released"]


def test_processor_recognizes_fully_injected_hotkey_from_external_software():
    events = []
    processor = HotkeyEventProcessor(
        VK_MENU, ord("D"), lambda: True, events.append,
    )
    assert processor.process(VK_MENU, True, injected=True) is False
    assert processor.process(ord("D"), True, injected=True) is True
    assert processor.process(ord("D"), False, injected=True) is True
    assert processor.process(VK_MENU, False, injected=True) is False
    assert events == ["pressed", "released"]


def test_processor_leaves_internal_input_unsuppressed_when_callback_rejects_it():
    events = []
    processor = HotkeyEventProcessor(
        VK_CONTROL, ord("C"), lambda: False, events.append,
    )
    assert processor.process(VK_CONTROL, True, injected=True) is False
    assert processor.process(ord("C"), True, injected=True) is False
    assert processor.process(ord("C"), False, injected=True) is False
    assert processor.process(VK_CONTROL, False, injected=True) is False
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
