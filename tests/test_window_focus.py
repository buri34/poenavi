from unittest.mock import Mock

from src.utils.window_focus import SW_RESTORE, _restore_window_if_minimized


def test_minimized_window_is_restored_before_focusing():
    user32 = Mock()
    user32.IsIconic.return_value = True
    hwnd = 123

    restored = _restore_window_if_minimized(user32, hwnd)

    assert restored is True
    user32.ShowWindow.assert_called_once_with(hwnd, SW_RESTORE)


def test_maximized_window_is_not_restored():
    user32 = Mock()
    user32.IsIconic.return_value = False
    hwnd = 123

    restored = _restore_window_if_minimized(user32, hwnd)

    assert restored is False
    user32.ShowWindow.assert_not_called()


def test_normal_window_is_not_restored():
    user32 = Mock()
    user32.IsIconic.return_value = False
    hwnd = 123

    restored = _restore_window_if_minimized(user32, hwnd)

    assert restored is False
    user32.ShowWindow.assert_not_called()
