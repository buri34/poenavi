from unittest.mock import Mock, patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from src.poetore.poe2.desecration_ocr import ChoiceBand
from src.poetore.poe2.desecration_overlay import (
    STATUS_LABELS,
    CategoryChoiceOverlay,
    DesecrationTierController,
    DesecrationTierOverlay,
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


def test_unresolved_statuses_have_distinct_user_facing_labels():
    assert STATUS_LABELS == {
        "read_failed": "読取失敗",
        "unsupported": "未対応",
        "tierless": "Tierなし",
        "category_unselected": "部位未選択",
    }


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


def test_controller_retries_closed_region_when_open_panel_ocr_cannot_resolve():
    """A structurally plausible open crop must not suppress the closed fallback."""
    QApplication.instance() or QApplication([])
    open_image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    closed_image = QImage("tests/fixtures/poetore/poe2/desecration/spear-reveal.png")
    regions = {
        "inventory_open_region": {"left": 0, "top": 0, "right": .5, "bottom": .5},
        "inventory_closed_region": {"left": .5, "top": .5, "right": 1, "bottom": 1},
    }
    unresolved = ["読取不能"] * 9
    resolved = [
        "この武器によるアタックは20%の火耐性を貫通する",
        "この武器によるアタックは20%の火耐性を貫通する",
        "この武器によるアタックは20%の火耐性を貫通する",
        "26から43の冷気ダメージを追加する",
        "26から43の冷気ダメージを追加する",
        "26から43の冷気ダメージを追加する",
        "物理ダメージが28%増加する\n命中力 +57",
        "物理ダメージが28%増加する\n命中力 +57",
        "物理ダメージが28%増加する\n命中力 +57",
    ]
    ocr = Mock()
    ocr.recognize.side_effect = [unresolved, resolved]
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: regions, ocr_server=ocr, scan_coordinator=gate,
    )
    controller._grab = Mock(side_effect=[open_image, closed_image])

    class ImmediateThread:
        def __init__(self, *, target, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    assert controller._grab.call_count == 2
    assert ocr.recognize.call_count == 2
    assert controller._capture_rect == QRect(960, 540, 960, 540)
    controller.close()


def test_controller_reports_all_unreadable_without_showing_badges():
    QApplication.instance() or QApplication([])
    image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    ocr = Mock()
    ocr.recognize.return_value = ["", "読取不能", "別の誤読"] * 3
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=ocr,
        scan_coordinator=gate,
    )
    controller._grab = Mock(return_value=image)
    failures = []
    controller.failed.connect(failures.append)

    class ImmediateThread:
        def __init__(self, *, target, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    assert failures == ["3つのModを読み取れませんでした。読取範囲を確認してください。"]
    assert not controller._overlay.isVisible()
    gate.finish.assert_called_once_with("desecration")
    controller.close()


def test_controller_rejects_repeated_scan_while_current_scan_is_running():
    QApplication.instance() or QApplication([])
    image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=Mock(), scan_coordinator=gate,
    )
    controller._grab = Mock(return_value=image)
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch("src.poetore.poe2.desecration_overlay.threading.Thread"):
        assert controller.request_scan()
        assert not controller.request_scan()

    gate.try_begin.assert_called_once_with("desecration")
    controller.close()


def test_stale_async_result_cannot_replace_a_newer_scan_or_release_its_gate():
    QApplication.instance() or QApplication([])
    gate = Mock()
    controller = DesecrationTierController(ocr_server=Mock(), scan_coordinator=gate)
    controller._scan_generation = 2
    controller._running = True
    controller._display = Mock()

    controller._show_result(
        Mock(), QRect(0, 0, 1920, 1080), QRect(100, 100, 600, 300),
        (ChoiceBand(0, 100), ChoiceBand(100, 200), ChoiceBand(200, 300)), 1,
    )

    controller._display.assert_not_called()
    gate.finish.assert_not_called()
    assert controller.running
    controller.close()


def test_tier_ranges_render_outside_the_registered_panel():
    QApplication.instance() or QApplication([])
    overlay = DesecrationTierOverlay()
    client = QRect(0, 0, 800, 360)
    capture = QRect(60, 30, 600, 300)
    overlay.show_tiers(
        client, capture, (600, 300),
        (ChoiceBand(0, 100), ChoiceBand(100, 200), ChoiceBand(200, 300)),
        (1, 5, 6),
        statuses=("matched", "matched", "matched"),
        range_labels=(("15–25%",), ("22–29", "34–44"), ("25–34%", "47–72")),
        show_ranges=True,
    )
    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    overlay.render(image)
    outside_left = capture.right() + 1
    assert any(
        image.pixelColor(x, y).alpha() > 0
        for y in range(image.height())
        for x in range(outside_left, image.width())
    )
    overlay.close()


def test_category_cancel_displays_explicit_unselected_state():
    QApplication.instance() or QApplication([])
    controller = DesecrationTierController(ocr_server=Mock())
    controller._display = Mock()
    bands = (ChoiceBand(0, 10), ChoiceBand(10, 20), ChoiceBand(20, 30))
    controller._pending = (Mock(), QRect(0, 0, 800, 600), QRect(100, 100, 500, 300), bands)
    controller._category_cancelled()
    assert controller._pending is None
    assert controller._display.call_args.kwargs["statuses"] == (
        "category_unselected", "category_unselected", "category_unselected",
    )
    controller.close()
