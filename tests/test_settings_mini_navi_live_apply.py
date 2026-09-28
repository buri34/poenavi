from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.act4_checklist import Act4ChecklistWindow
from src.ui.main_window import MainWindow
from src.ui.mini_navi import MiniNaviOverlay
from src.ui.window_flags import MINI_TOPMOST_ALWAYS, MINI_TOPMOST_POE_ONLY


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def _window_with_overlays(topmost_mode: str):
    window = Mock()
    window.config = {
        "mini_guide_overlay": {
            "font_size": 18,
            "topmost_mode": topmost_mode,
        }
    }
    window.mini_navi_overlay = Mock()
    window.act4_checklist_window = Mock()
    return window


def test_font_change_does_not_recreate_mini_navi_native_windows():
    window = _window_with_overlays(MINI_TOPMOST_POE_ONLY)
    window.config["mini_guide_overlay"]["font_size"] = 22

    MainWindow._apply_mini_navi_related_settings(window, MINI_TOPMOST_POE_ONLY)

    window.mini_navi_overlay.apply_settings.assert_called_once_with(
        refresh_window_flags=False
    )
    window.act4_checklist_window.apply_settings.assert_called_once_with(
        refresh_window_flags=False
    )


def test_topmost_change_recreates_mini_navi_native_windows():
    window = _window_with_overlays(MINI_TOPMOST_ALWAYS)

    MainWindow._apply_mini_navi_related_settings(window, MINI_TOPMOST_POE_ONLY)

    window.mini_navi_overlay.apply_settings.assert_called_once_with(
        refresh_window_flags=True
    )
    window.act4_checklist_window.apply_settings.assert_called_once_with(
        refresh_window_flags=True
    )


def test_medium_large_small_sequence_updates_both_windows_immediately():
    window = Mock()
    window.config = {
        "mini_guide_overlay": {
            "font_size": 18,
            "topmost_mode": MINI_TOPMOST_POE_ONLY,
        }
    }
    window.mini_navi_overlay = MiniNaviOverlay(window)
    window.act4_checklist_window = Act4ChecklistWindow(window)

    expected_profiles = ((18, "medium", 15), (22, "large", 18), (15, "small", 12))
    for font_size, profile_name, checklist_body_size in expected_profiles:
        window.config["mini_guide_overlay"]["font_size"] = font_size
        MainWindow._apply_mini_navi_related_settings(
            window, MINI_TOPMOST_POE_ONLY
        )

        assert f"font-size: {font_size}px" in window.mini_navi_overlay.text_label.styleSheet()
        assert window.act4_checklist_window.font_profile_name == profile_name
        assert window.act4_checklist_window.body_font_size == checklist_body_size

    window.mini_navi_overlay.close()
    window.act4_checklist_window.close()
