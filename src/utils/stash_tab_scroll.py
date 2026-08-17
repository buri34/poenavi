"""Awakened PoE Trade互換のCtrl+ホイールによるスタッシュタブ切替。"""

import sys
from collections.abc import Callable

from src.utils.window_focus import (
    get_foreground_window,
    get_window_rect,
    is_path_of_exile_window,
)


def is_stash_area(x: int, y: int, rect: tuple[int, int, int, int] | None) -> bool:
    """Awakenedと同じ比率で、PoE左側のスタッシュ領域か判定する。"""
    if rect is None:
        return False
    left, top, _width, height = rect
    sidebar_width = round(height * 370 / 600)
    if x > left + sidebar_width:
        return False
    return top + height * 154 / 1600 < y < top + height * 1192 / 1600


class StashTabScrollController:
    """スタッシュ領域外のCtrl+ホイールを左右キーへ変換する。"""

    def __init__(
        self,
        enabled: bool = True,
        *,
        foreground_window: Callable = get_foreground_window,
        is_poe_window: Callable = is_path_of_exile_window,
        window_rect: Callable = get_window_rect,
        ctrl_pressed: Callable[[], bool] | None = None,
        tap_key: Callable[[str], None] | None = None,
    ):
        self.enabled = bool(enabled)
        self._foreground_window = foreground_window
        self._is_poe_window = is_poe_window
        self._window_rect = window_rect
        self._ctrl_pressed = ctrl_pressed or self._default_ctrl_pressed
        self._tap_key = tap_key or self._default_tap_key
        self._mouse_listener = None

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)

    def start(self):
        if sys.platform != "win32" or self._mouse_listener is not None:
            return
        try:
            from pynput import mouse

            self._mouse_listener = mouse.Listener(on_scroll=self.handle_scroll)
            self._mouse_listener.start()
        except Exception as exc:
            self._mouse_listener = None
            print(f"[STASH SCROLL] Failed to start mouse listener: {exc}")

    def stop(self):
        listener = self._mouse_listener
        self._mouse_listener = None
        if listener is not None:
            listener.stop()

    def handle_scroll(self, x: int, y: int, _dx: int, dy: int):
        if not self.enabled or not self._ctrl_pressed() or not dy:
            return
        hwnd = self._foreground_window()
        if not hwnd or not self._is_poe_window(hwnd):
            return
        if is_stash_area(x, y, self._window_rect(hwnd)):
            # スタッシュ内はPoE本体のCtrl+ホイール処理に任せ、二重入力を防ぐ。
            return
        self._tap_key("left" if dy > 0 else "right")

    @staticmethod
    def _default_ctrl_pressed() -> bool:
        if sys.platform != "win32":
            return False
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)

    @staticmethod
    def _default_tap_key(key_name: str):
        from pynput.keyboard import Controller, Key

        controller = Controller()
        key = Key.left if key_name == "left" else Key.right
        controller.press(key)
        controller.release(key)
