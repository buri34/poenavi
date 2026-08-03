from __future__ import annotations

import sys


def clipboard_change_token(qt_clipboard):
    """Return a value that changes whenever the OS clipboard is rewritten."""
    if sys.platform == "win32":
        sequence = _windows_clipboard_sequence_number()
        if sequence is not None:
            return ("windows", sequence)
    return ("qt", qt_clipboard.text())


def read_item_clipboard(qt_clipboard) -> str:
    """WindowsではUnicode本文を直接読み、取得できなければQtへフォールバックする。"""
    if sys.platform == "win32":
        native_text = _read_windows_unicode_text()
        if native_text:
            return native_text
    return qt_clipboard.text()


def _read_windows_unicode_text() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _windows_clipboard_sequence_number() -> int | None:
    """Read the Windows clipboard generation without opening the clipboard."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.GetClipboardSequenceNumber.argtypes = []
        user32.GetClipboardSequenceNumber.restype = ctypes.c_uint
        return int(user32.GetClipboardSequenceNumber())
    except (AttributeError, OSError):
        return None
