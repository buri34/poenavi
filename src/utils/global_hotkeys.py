"""モード間で共有するグローバルホットキー監視。"""

import sys
from PySide6.QtCore import QObject, QTimer, Signal

from src.utils.internal_key_input import is_internal_key_input
from src.utils.window_focus import focus_window, get_foreground_window, is_path_of_exile_window
from src.poetore.performance import record_hotkey_event


HOTKEY_ACTIONS_ALLOWED_OUTSIDE_POE = frozenset({
    "start_stop",
    "lap",
    "click_through",
    "cheat_sheets_toggle",
    "cheat_sheets_escape",
})


def suppressed_hotkeys_supported(platform=None) -> bool:
    """Return whether the native key-suppression backend is available."""
    return (sys.platform if platform is None else platform) == "win32"


def is_hotkey_action_allowed(action: str, foreground_window=None) -> bool:
    """Return whether a hotkey action may run for the current foreground window."""
    if action in HOTKEY_ACTIONS_ALLOWED_OUTSIDE_POE:
        return True
    foreground = get_foreground_window() if foreground_window is None else foreground_window
    return bool(foreground and is_path_of_exile_window(foreground))


def find_duplicate_hotkeys(hotkeys: dict[str, str]) -> dict[str, list[str]]:
    """未割り当てを除き、同じキーへ割り当てられた操作を返す。"""
    by_key: dict[str, list[str]] = {}
    for action, key in hotkeys.items():
        normalized = str(key or "").strip().casefold()
        if not normalized or normalized == "none":
            continue
        by_key.setdefault(normalized, []).append(action)
    return {key: actions for key, actions in by_key.items() if len(actions) > 1}


def listener_hotkey_name(key_text: str) -> str:
    normalized = str(key_text).lower().replace(" ", "_").replace("capslock", "caps_lock")
    return {
        "left_alt": "alt_l",
        "right_alt": "alt_r",
    }.get(normalized, normalized)


def hotkey_key_name(key) -> str | None:
    if hasattr(key, "name") and key.name:
        return key.name.lower()

    char = getattr(key, "char", None)
    if char and char.isprintable():
        return char.lower()

    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        if ord("A") <= vk <= ord("Z"):
            return chr(vk).lower()
        if ord("0") <= vk <= ord("9"):
            return chr(vk)

    if char and len(char) == 1 and 1 <= ord(char) <= 26:
        return chr(ord("a") + ord(char) - 1)
    return None


class GlobalHotkeyService(QObject):
    """指定された操作だけを登録する、モード非依存のキーボード監視。"""

    command = Signal(str)

    def __init__(
        self, hotkeys=None, *, listener_factory=None, action_filter=None, parent=None,
    ):
        super().__init__(parent)
        self._listener_factory = listener_factory
        self._action_filter = action_filter
        self._listener = None
        self._hotkey_map = {}
        self.configure(hotkeys or {})

    @property
    def registered_actions(self):
        return frozenset(self._hotkey_map.values())

    @property
    def is_running(self):
        return self._listener is not None

    def configure(self, hotkeys):
        self._hotkey_map = {
            listener_hotkey_name(key): action
            for action, key in (hotkeys or {}).items()
            if key and str(key).lower() != "none"
        }
        if self.is_running:
            self.start()

    def start(self):
        self.stop()
        try:
            listener_factory = self._listener_factory
            if listener_factory is None:
                from pynput import keyboard

                listener_factory = keyboard.Listener

            pressed_modifiers = set()
            pressed_keys = set()
            triggered_combos = set()
            pending_releases = {}

            def on_press(key):
                if is_internal_key_input():
                    return
                key_name = hotkey_key_name(key)
                if key_name is None:
                    return
                modifier = self._modifier_name(key_name)
                if modifier:
                    pressed_modifiers.add(modifier)
                pressed_keys.add(modifier or key_name)

                if key_name in {"esc", "escape"}:
                    if self._action_is_allowed("cheat_sheets_escape"):
                        self.command.emit("cheat_sheets_escape")

                combo = "+".join(
                    [
                        modifier_name
                        for modifier_name in ("ctrl", "alt", "shift")
                        if modifier_name in pressed_modifiers
                    ]
                    + [key_name]
                )
                configured = self._hotkey_map.get(combo) or self._hotkey_map.get(key_name)
                if (configured and combo not in triggered_combos
                        and self._action_is_allowed(configured)):
                    triggered_combos.add(combo)
                    if configured in {
                        "poetore_capture", "poetore_auto_hide", "map_check",
                    }:
                        pending_releases[combo] = frozenset(combo.split("+"))
                    self.command.emit(configured)

            def on_release(key):
                key_name = hotkey_key_name(key)
                if key_name is None:
                    return
                if is_internal_key_input():
                    triggered_combos.clear()
                    return
                modifier = self._modifier_name(key_name)
                if modifier:
                    pressed_modifiers.discard(modifier)
                pressed_keys.discard(modifier or key_name)
                for combo, required_keys in tuple(pending_releases.items()):
                    action = self._hotkey_map.get(combo) or "poetore_capture"
                    hold_key_released = (
                        action == "poetore_auto_hide"
                        and modifier in {"ctrl", "alt"}
                        and modifier in required_keys
                    )
                    if hold_key_released or (
                        action != "poetore_auto_hide"
                        and not required_keys.intersection(pressed_keys)
                    ):
                        pending_releases.pop(combo, None)
                        self.command.emit(f"{action}_released")
                triggered_combos.clear()

            self._listener = listener_factory(on_press=on_press, on_release=on_release)
            self._listener.start()
        except Exception as exc:
            self._listener = None
            print(f"Failed to register mode hotkeys: {exc}")

    def stop(self):
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def _action_is_allowed(self, action):
        return self._action_filter is None or bool(self._action_filter(action))

    @staticmethod
    def _modifier_name(key_name):
        if key_name in {"alt", "alt_l", "alt_r", "alt_gr"}:
            return "alt"
        if key_name in {"ctrl", "ctrl_l", "ctrl_r"}:
            return "ctrl"
        if key_name in {"shift", "shift_l", "shift_r"}:
            return "shift"
        return None


class ForegroundSuppressedHotkeyService(QObject):
    """PoEが前面の間だけ、Windowsで元キーを通さずホットキーを発火する。"""

    command = Signal(str)
    _native_pressed = Signal()
    _native_released = Signal()

    def __init__(
        self,
        action: str,
        hotkey: str,
        *,
        native_hook_factory=None,
        foreground_getter=None,
        poe_window_checker=None,
        result_window_checker=None,
        poe_target_getter=None,
        focus_target=None,
        platform=None,
        poll_interval_ms=100,
        parent=None,
    ):
        super().__init__(parent)
        self._action = action
        self._hotkey = str(hotkey or "").strip()
        self._native_hook_factory = native_hook_factory
        self._foreground_getter = foreground_getter or get_foreground_window
        self._poe_window_checker = poe_window_checker or is_path_of_exile_window
        self._result_window_checker = result_window_checker
        self._poe_target_getter = poe_target_getter
        self._focus_target = focus_target or focus_window
        self._platform = sys.platform if platform is None else platform
        self._poll_interval_ms = poll_interval_ms
        self._native_hook = None
        self._running = False
        self._foreground_timer = QTimer(self)
        self._foreground_timer.setInterval(self._poll_interval_ms)
        self._foreground_timer.timeout.connect(self._refresh_foreground_context)
        self._waiting_for_release = False
        self._pending_focus_target = None
        self._foreground_context = "outside"
        self._cached_focus_target = None
        self._native_pressed.connect(self._on_native_pressed)
        self._native_released.connect(self._on_native_released)

    @property
    def is_running(self):
        return self._running

    @property
    def is_registered(self):
        return bool(self._native_hook and self._native_hook.is_running)

    @property
    def is_supported(self):
        return (
            suppressed_hotkeys_supported(self._platform)
            and bool(self._hotkey)
            and self._hotkey.casefold() != "none"
        )

    def start(self):
        self.stop()
        self._running = True
        if not self.is_supported:
            return
        self._refresh_foreground_context()
        self._foreground_timer.start()
        self._register()

    def stop(self):
        self._running = False
        self._foreground_timer.stop()
        self._waiting_for_release = False
        self._pending_focus_target = None
        self._unregister()

    def refresh(self):
        """Restart only when the native hook thread has actually stopped."""
        if not self._running or not self.is_supported:
            return
        if not self.is_registered:
            self._register()

    def _register(self):
        try:
            factory = self._native_hook_factory
            if factory is None:
                from src.utils.win32_suppressed_hotkey import Win32SuppressedHotkeyHook
                factory = Win32SuppressedHotkeyHook
            hook = factory(
                self._hotkey,
                should_suppress=self._should_suppress_native_event,
                on_event=self._receive_native_event,
            )
            hook.start()
            self._native_hook = hook
            record_hotkey_event("registered", hotkey=self._hotkey)
        except Exception as exc:
            self._native_hook = None
            record_hotkey_event("registration_failed", hotkey=self._hotkey, error=str(exc))
            print(f"Failed to register suppressed hotkey {self._hotkey}: {exc}")

    def _unregister(self):
        hook = self._native_hook
        self._native_hook = None
        if hook is None:
            return
        try:
            hook.stop()
        except Exception as exc:
            print(f"Failed to unregister suppressed hotkey {self._hotkey}: {exc}")

    def _should_suppress_native_event(self):
        """Called in the hook thread; only read precomputed state."""
        if not self._running:
            return False
        context = self._foreground_context
        if context not in {"poe", "result"}:
            return False
        if context == "result" and not self._cached_focus_target:
            return False
        if is_internal_key_input():
            return False
        return True

    def _receive_native_event(self, event):
        if event == "pressed":
            self._native_pressed.emit()
        elif event == "released":
            self._native_released.emit()

    def _on_native_pressed(self):
        if not self._running or self._waiting_for_release:
            return
        context = self._foreground_context
        record_hotkey_event("pressed", hotkey=self._hotkey, context=context)
        self._waiting_for_release = True
        self._pending_focus_target = (
            self._cached_focus_target if context == "result" else None
        )

    def _on_native_released(self):
        if not self._waiting_for_release:
            return
        self._waiting_for_release = False
        focus_target = self._pending_focus_target
        self._pending_focus_target = None
        if not self._running:
            return
        if focus_target is not None and not self._focus_target(focus_target):
            record_hotkey_event("focus_failed", hotkey=self._hotkey)
            return
        record_hotkey_event("dispatched", hotkey=self._hotkey)
        self.command.emit(self._action)
        self.command.emit(f"{self._action}_released")

    def _refresh_foreground_context(self):
        """Resolve the active app outside the low-level keyboard-hook callback."""
        context = "outside"
        focus_target = None
        try:
            foreground = self._foreground_getter()
            if foreground and self._poe_window_checker(foreground):
                context = "poe"
            elif (
                foreground
                and self._result_window_checker is not None
                and self._result_window_checker(foreground)
                and self._poe_target_getter is not None
            ):
                candidate = self._poe_target_getter()
                if candidate and self._poe_window_checker(candidate):
                    context = "result"
                    focus_target = candidate
        except Exception as exc:
            record_hotkey_event("context_check_failed", error=str(exc))
        changed = (
            context != self._foreground_context
            or focus_target != self._cached_focus_target
        )
        self._foreground_context = context
        self._cached_focus_target = focus_target
        if changed:
            record_hotkey_event(
                "context_changed", context=context,
                has_focus_target=bool(focus_target),
            )
