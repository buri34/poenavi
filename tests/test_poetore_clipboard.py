from unittest.mock import Mock, patch

from src.poetore.clipboard import clipboard_change_token, read_item_clipboard


def test_uses_qt_clipboard_outside_windows():
    clipboard = Mock()
    clipboard.text.return_value = "日本語の本文"

    with patch("src.poetore.clipboard.sys.platform", "darwin"):
        assert read_item_clipboard(clipboard) == "日本語の本文"


def test_prefers_windows_unicode_clipboard_text():
    clipboard = Mock()
    clipboard.text.return_value = "Pandemonium Bane"

    with (
        patch("src.poetore.clipboard.sys.platform", "win32"),
        patch(
            "src.poetore.clipboard._read_windows_unicode_text",
            return_value="地獄の破滅",
        ),
    ):
        assert read_item_clipboard(clipboard) == "地獄の破滅"


def test_falls_back_to_qt_when_windows_unicode_text_is_unavailable():
    clipboard = Mock()
    clipboard.text.return_value = "fallback"

    with (
        patch("src.poetore.clipboard.sys.platform", "win32"),
        patch("src.poetore.clipboard._read_windows_unicode_text", return_value=""),
    ):
        assert read_item_clipboard(clipboard) == "fallback"


def test_windows_clipboard_uses_pointer_sized_handle_types():
    """64bit WindowsのHGLOBALを32bit intへ切り詰めない。"""
    import ctypes
    from ctypes import wintypes

    assert ctypes.sizeof(wintypes.HGLOBAL) == ctypes.sizeof(ctypes.c_void_p)


def test_windows_change_token_uses_sequence_number_even_for_identical_text():
    clipboard = Mock()
    with patch("src.poetore.clipboard.sys.platform", "win32"), patch(
        "src.poetore.clipboard._windows_clipboard_sequence_number", return_value=42,
    ):
        assert clipboard_change_token(clipboard) == ("windows", 42)
    clipboard.text.assert_not_called()


def test_change_token_falls_back_to_qt_text():
    clipboard = Mock()
    clipboard.text.return_value = "現在の本文"
    with patch("src.poetore.clipboard.sys.platform", "darwin"):
        assert clipboard_change_token(clipboard) == ("qt", "現在の本文")
