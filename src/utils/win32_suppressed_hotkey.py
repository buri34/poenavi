"""Win32 low-level keyboard hook for one conditionally suppressed hotkey."""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes


WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
WH_KEYBOARD_LL = 13
LLKHF_INJECTED = 0x00000010
HC_ACTION = 0

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LWIN = 0x5B
VK_RWIN = 0x5C

MODIFIER_GROUPS = {
    "ctrl": {VK_CONTROL, VK_LCONTROL, VK_RCONTROL},
    "alt": {VK_MENU, VK_LMENU, VK_RMENU},
    "shift": {VK_SHIFT, VK_LSHIFT, VK_RSHIFT},
    "win": {VK_LWIN, VK_RWIN},
}

NAMED_VIRTUAL_KEYS = {
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "insert": 0x2D,
}


def _parse_hotkey(
    hotkey: str, *, allow_unmodified: bool = False,
) -> tuple[frozenset[str], int]:
    parts = [
        part.strip().casefold()
        for part in str(hotkey or "").split("+")
        if part.strip()
    ]
    aliases = {"control": "ctrl"}
    parts = [aliases.get(part, part) for part in parts]
    modifiers = parts[:-1]
    key = parts[-1] if parts else ""
    if not modifiers and not allow_unmodified:
        raise ValueError("suppressed hotkey requires Ctrl, Alt, or Shift")
    if (
        any(part not in {"ctrl", "alt", "shift"} for part in modifiers)
        or len(set(modifiers)) != len(modifiers)
        or key in {"ctrl", "alt", "shift", "win", "meta"}
    ):
        raise ValueError(
            "suppressed hotkey must use Ctrl/Alt/Shift and one regular key"
        )
    if len(key) == 1 and key.isascii() and key.isalnum():
        target_vk = ord(key.upper())
    elif key in NAMED_VIRTUAL_KEYS:
        target_vk = NAMED_VIRTUAL_KEYS[key]
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        target_vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"unsupported suppressed hotkey key: {key}")
    return frozenset(modifiers), target_vk


class HotkeyEventProcessor:
    """Pure state machine used by the native hook and unit tests."""

    def __init__(
        self, required_modifier_groups, target_vk: int, should_suppress, on_event,
    ):
        if required_modifier_groups is None:
            required_modifier_groups = frozenset()
        elif isinstance(required_modifier_groups, int):
            required_modifier_groups = {
                VK_CONTROL: frozenset({"ctrl"}),
                VK_MENU: frozenset({"alt"}),
                VK_SHIFT: frozenset({"shift"}),
            }.get(required_modifier_groups, frozenset())
        self.required_modifier_groups = frozenset(required_modifier_groups)
        self.target_vk = target_vk
        self.should_suppress = should_suppress
        self.on_event = on_event
        self.pressed_modifier_groups = set()
        self.suppressing_target = False

    def process(self, vk_code: int, is_down: bool, *, injected: bool = False) -> bool:
        modifier_group = next(
            (name for name, virtual_keys in MODIFIER_GROUPS.items()
             if vk_code in virtual_keys),
            None,
        )
        if modifier_group is not None:
            if is_down:
                self.pressed_modifier_groups.add(modifier_group)
            else:
                self.pressed_modifier_groups.discard(modifier_group)
            return False
        if vk_code != self.target_vk:
            return False
        if is_down:
            if self.suppressing_target:
                return True
            modifier_matches = (
                self.pressed_modifier_groups == self.required_modifier_groups
            )
            if modifier_matches and self.should_suppress():
                self.suppressing_target = True
                self.on_event("pressed")
                return True
            return False
        if self.suppressing_target:
            self.suppressing_target = False
            self.on_event("released")
            return True
        return False


class Win32SuppressedHotkeyHook:
    """Own and run a WH_KEYBOARD_LL hook on a dedicated message-loop thread."""

    def __init__(
        self, hotkey: str, *, should_suppress, on_event,
        allow_unmodified: bool = False,
    ):
        modifier_groups, target_vk = _parse_hotkey(
            hotkey, allow_unmodified=allow_unmodified,
        )
        self._processor = HotkeyEventProcessor(
            modifier_groups, target_vk, should_suppress, on_event,
        )
        self._thread = None
        self._thread_id = 0
        self._hook = None
        self._callback = None
        self._startup = queue.Queue(maxsize=1)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._hook)

    def start(self, timeout: float = 3.0) -> None:
        if self.is_running:
            return
        self._startup = queue.Queue(maxsize=1)
        self._thread = threading.Thread(
            target=self._run, name="PoENaviWin32Hotkey", daemon=True,
        )
        self._thread.start()
        result = self._startup.get(timeout=timeout)
        if isinstance(result, BaseException):
            self._thread = None
            raise result

    def stop(self, timeout: float = 3.0) -> None:
        thread = self._thread
        if not thread:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread.join(timeout)
        self._thread = None
        self._thread_id = 0
        self._hook = None
        self._callback = None

    def _run(self) -> None:
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.CallNextHookEx.argtypes = [
                ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
            ]
            user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            callback_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
            )

            def hook_proc(code, message, data_ptr):
                if code == HC_ACTION:
                    data = ctypes.cast(
                        data_ptr, ctypes.POINTER(KBDLLHOOKSTRUCT),
                    ).contents
                    is_down = message in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    is_up = message in (WM_KEYUP, WM_SYSKEYUP)
                    if (is_down or is_up) and self._processor.process(
                        int(data.vkCode), is_down,
                        injected=bool(data.flags & LLKHF_INJECTED),
                    ):
                        return 1
                return user32.CallNextHookEx(self._hook, code, message, data_ptr)

            self._callback = callback_type(hook_proc)
            self._thread_id = int(kernel32.GetCurrentThreadId())
            self._hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._callback, kernel32.GetModuleHandleW(None), 0,
            )
            if not self._hook:
                raise ctypes.WinError()
            self._startup.put(True)
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as exc:
            if self._startup.empty():
                self._startup.put(exc)
        finally:
            if self._hook:
                ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
