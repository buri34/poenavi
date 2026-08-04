import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication

from src.ui.map_viewer import MapImageDialog, geometry_inside_available_screens


def test_map_image_dialog_does_not_quit_the_application_when_closed():
    QApplication.instance() or QApplication([])
    with patch("src.utils.config_manager.ConfigManager.load_config", return_value={}):
        dialog = MapImageDialog("missing-map.png")

    assert not dialog.testAttribute(Qt.WA_QuitOnClose)
    dialog.close()


def test_map_image_geometry_is_clamped_inside_monitor_work_area():
    corrected = geometry_inside_available_screens(
        QRect(1700, -80, 500, 600), [QRect(0, 0, 1920, 1040)],
    )

    assert corrected == QRect(1420, 0, 500, 600)


def test_map_image_geometry_supports_negative_monitor_coordinates():
    corrected = geometry_inside_available_screens(
        QRect(-2200, -120, 640, 700),
        [QRect(-1920, 0, 1920, 1040), QRect(0, 0, 2560, 1400)],
    )

    assert corrected == QRect(-1920, 0, 640, 700)


def test_oversized_map_image_is_reduced_to_available_work_area():
    corrected = geometry_inside_available_screens(
        QRect(5000, 400, 3000, 1800),
        [QRect(-1920, 0, 1920, 1040), QRect(0, 0, 2560, 1400)],
    )

    assert corrected == QRect(0, 0, 2560, 1400)
