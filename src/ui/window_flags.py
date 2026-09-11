import sys

from PySide6.QtCore import Qt

from src.utils.config_manager import ConfigManager


MINI_TOPMOST_POE_ONLY = "poe_only"
MINI_TOPMOST_ALWAYS = "always"
MINI_TOPMOST_NEVER = "never"
MINI_TOPMOST_MODES = frozenset({
    MINI_TOPMOST_POE_ONLY,
    MINI_TOPMOST_ALWAYS,
    MINI_TOPMOST_NEVER,
})


def _is_always_on_top_enabled(parent=None):
    """設定に応じて最前面表示を有効にするか返す。"""
    if parent is not None and hasattr(parent, "config"):
        return parent.config.get("always_on_top", True)
    return ConfigManager.load_config().get("always_on_top", True)


def _with_optional_always_on_top(flags, parent=None):
    if _is_always_on_top_enabled(parent):
        return flags | Qt.WindowStaysOnTopHint
    return flags & ~Qt.WindowStaysOnTopHint


def mini_topmost_mode_from_config(config) -> str:
    """設定dictから、互換性を保ってみになびの前面表示モードを返す。"""
    mini_config = config.get("mini_guide_overlay", {}) if isinstance(config, dict) else {}
    if isinstance(mini_config, dict):
        mode = mini_config.get("topmost_mode")
        if mode in MINI_TOPMOST_MODES:
            return mode
        if mini_config.get("always_on_top") is False:
            return MINI_TOPMOST_NEVER
    return MINI_TOPMOST_POE_ONLY


def _mini_topmost_mode(parent=None):
    """みになびの前面表示モード。旧設定は新しい標準仕様へ読み替える。"""
    if parent is not None and hasattr(parent, "config"):
        config = parent.config
    else:
        config = ConfigManager.load_config()
    return mini_topmost_mode_from_config(config)


def _is_mini_always_on_top_enabled(parent=None):
    """互換用。常時最前面モードの場合だけTrueを返す。"""
    return _mini_topmost_mode(parent) == MINI_TOPMOST_ALWAYS


def _with_optional_mini_always_on_top(flags, parent=None):
    if _is_mini_always_on_top_enabled(parent):
        return flags | Qt.WindowStaysOnTopHint
    return flags & ~Qt.WindowStaysOnTopHint


def set_native_window_topmost(widget, enabled: bool) -> bool:
    """Windowsでフォーカスを奪わず、既存ウィンドウの前面属性だけを切り替える。"""
    if sys.platform != "win32" or widget is None:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        insert_after = wintypes.HWND(-1 if enabled else -2)  # HWND_TOPMOST / HWND_NOTOPMOST
        flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
        return bool(
            user32.SetWindowPos(
                wintypes.HWND(int(widget.winId())),
                insert_after,
                0,
                0,
                0,
                0,
                flags,
            )
        )
    except Exception as exc:
        print(f"[MINI NAVI] topmost update failed: {exc}")
        return False


def native_window_z_order_state(widget, foreground_hwnd=None) -> dict:
    """Return privacy-safe topmost and relative Z-order state for diagnostics."""
    unknown = {"topmost": None, "foreground_above": None}
    if sys.platform != "win32" or widget is None:
        return unknown
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        if not hwnd:
            return unknown

        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        GW_HWNDNEXT = 2
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetTopWindow.argtypes = [wintypes.HWND]
        user32.GetTopWindow.restype = wintypes.HWND
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND

        ex_style = int(user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE))
        foreground_above = None
        foreground = int(foreground_hwnd or 0)
        if foreground:
            widget_index = None
            foreground_index = None
            current = user32.GetTopWindow(None)
            for index in range(4096):
                current_value = int(current or 0)
                if not current_value:
                    break
                if current_value == hwnd:
                    widget_index = index
                if current_value == foreground:
                    foreground_index = index
                if widget_index is not None and foreground_index is not None:
                    break
                current = user32.GetWindow(current, GW_HWNDNEXT)
            if widget_index is not None and foreground_index is not None:
                foreground_above = foreground_index < widget_index

        return {
            "topmost": bool(ex_style & WS_EX_TOPMOST),
            "foreground_above": foreground_above,
        }
    except Exception as exc:
        print(f"[MINI NAVI] Z-order diagnostic failed: {exc}")
        return unknown
