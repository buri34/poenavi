from unittest.mock import Mock, patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from src.poetore.poe2.desecration_overlay import (
    CategoryChoiceOverlay,
    DesecrationTierController,
    normalized_capture_rect,
)


def test_normalized_capture_rect_is_client_relative():
    rect = normalized_capture_rect(QRect(100, 50, 1000, 500), {
        "left": .2, "top": .1, "right": .8, "bottom": .7,
    })
    assert rect == QRect(300, 100, 600, 300)


def test_normalized_capture_rect_rejects_invalid_values():
    assert normalized_capture_rect(QRect(0, 0, 100, 100), None) is None
    assert normalized_capture_rect(QRect(0, 0, 100, 100), {
        "left": .8, "top": 0, "right": .2, "bottom": 1,
    }) is None


def test_category_selector_is_non_modal_and_does_not_accept_focus():
    QApplication.instance() or QApplication([])
    overlay = CategoryChoiceOverlay()
    assert overlay.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert overlay.testAttribute(Qt.WA_ShowWithoutActivating)
    assert not overlay.isModal()
    overlay.close()


def test_controller_tries_open_region_before_optional_closed_region():
    QApplication.instance() or QApplication([])
    valid = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    regions = {
        "inventory_open_region": {"left": 0, "top": 0, "right": .5, "bottom": .5},
        "inventory_closed_region": {"left": .5, "top": .5, "right": 1, "bottom": 1},
    }
    ocr = Mock()
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: regions, ocr_server=ocr, scan_coordinator=gate,
    )
    controller._grab = Mock(side_effect=[QImage(), valid])
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch("src.poetore.poe2.desecration_overlay.threading.Thread"):
        assert controller.request_scan()
    assert controller._grab.call_count == 2
    controller.close()
    ocr.close.assert_not_called()


def test_controller_does_not_try_closed_region_when_open_panel_is_detected():
    QApplication.instance() or QApplication([])
    valid = QImage("tests/fixtures/poetore/poe2/desecration/spear-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    controller = DesecrationTierController(
        regions_getter=lambda: {
            "inventory_open_region": region,
            "inventory_closed_region": region,
        },
        ocr_server=Mock(), scan_coordinator=Mock(try_begin=Mock(return_value=True)),
    )
    controller._grab = Mock(return_value=valid)
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch("src.poetore.poe2.desecration_overlay.threading.Thread"):
        assert controller.request_scan()
    controller._grab.assert_called_once()
    controller.close()
