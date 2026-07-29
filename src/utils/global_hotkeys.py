"""モード間で共有するグローバルホットキー監視。"""

from PySide6.QtCore import QObject, Signal


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

    def __init__(self, hotkeys=None, *, listener_factory=None, parent=None):
        super().__init__(parent)
        self._listener_factory = listener_factory
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
            triggered_combos = set()

            def on_press(key):
                key_name = hotkey_key_name(key)
                if key_name is None:
                    return
                modifier = self._modifier_name(key_name)
                if modifier:
                    pressed_modifiers.add(modifier)

                if key_name in {"esc", "escape"}:
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
                if configured and combo not in triggered_combos:
                    triggered_combos.add(combo)
                    self.command.emit(configured)

            def on_release(key):
                key_name = hotkey_key_name(key)
                if key_name is None:
                    return
                modifier = self._modifier_name(key_name)
                if modifier:
                    pressed_modifiers.discard(modifier)
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

    @staticmethod
    def _modifier_name(key_name):
        if key_name in {"alt", "alt_l", "alt_r", "alt_gr"}:
            return "alt"
        if key_name in {"ctrl", "ctrl_l", "ctrl_r"}:
            return "ctrl"
        if key_name in {"shift", "shift_l", "shift_r"}:
            return "shift"
        return None
