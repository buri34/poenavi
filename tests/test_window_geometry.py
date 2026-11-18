from PySide6.QtCore import QRect

from src.ui.window_geometry import fit_saved_window_geometry


def test_geometry_in_monitor_layout_gap_uses_caller_fallback():
    screens = [QRect(0, 0, 1920, 1080), QRect(1920, 1080, 1920, 1080)]

    restored = fit_saved_window_geometry(
        {"x": 2200, "y": 500, "width": 600, "height": 400}, screens
    )

    assert restored is None


def test_removed_monitor_geometry_uses_caller_fallback():
    restored = fit_saved_window_geometry(
        {"x": 3840, "y": 100, "width": 700, "height": 900},
        [QRect(0, 0, 1920, 1080)],
    )

    assert restored is None


def test_oversized_geometry_is_clamped_to_one_monitor():
    restored = fit_saved_window_geometry(
        {"x": -500, "y": -400, "width": 5000, "height": 3000},
        [QRect(0, 0, 2560, 1440), QRect(2560, 0, 1920, 1080)],
    )

    assert restored == QRect(0, 0, 2560, 1440)


def test_malformed_geometry_uses_caller_fallback():
    assert fit_saved_window_geometry(
        {"x": 10, "y": 20, "width": -1, "height": 500},
        [QRect(0, 0, 1920, 1080)],
    ) is None
