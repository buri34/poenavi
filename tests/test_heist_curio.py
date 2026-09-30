from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QDialog

from src.poetore.heist_curio import (
    CurioHeaderBand,
    CurioRegionSelector,
    HeistCurioController,
    curio_item_text,
    detect_header_bands,
    image_point_for_capture,
    load_curio_items,
    load_curio_unique_mod_templates,
    rank_curio_matches,
    select_header_band,
    trusted_curio_match,
)
from src.poetore.parser import parse_item_text
from src.poetore.ui import PoetoreWindow
from src.poetore.window_position import PlacementContext


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_bundled_dictionary_has_the_verified_259_unique_items():
    items = load_curio_items()

    assert len(items) == 259
    assert len({item.stable_id for item in items}) == 259
    assert {
        category: sum(item.category == category for item in items)
        for category in {item.category for item in items}
    } == {
        "currency": 24,
        "experimental_base": 48,
        "replacement_unique": 9,
        "replica_unique": 92,
        "scarab": 86,
    }
    assert any(item.name_ja == "信者のチェーンメイル" for item in items)


def test_bundled_unique_mod_templates_cover_all_101_heist_uniques():
    templates = load_curio_unique_mod_templates()
    unique_items = {
        item.stable_id: item
        for item in load_curio_items()
        if item.category in {"replica_unique", "replacement_unique"}
    }

    assert templates.keys() == unique_items.keys()
    assert (
        sum(item.category == "replica_unique" for item in unique_items.values()) == 92
    )
    assert (
        sum(item.category == "replacement_unique" for item in unique_items.values())
        == 9
    )

    abyssus_id = next(
        item.stable_id
        for item in unique_items.values()
        if item.name_en == "Replica Abyssus"
    )
    abyssus = templates[abyssus_id]
    assert abyssus.status == "fixed"
    assert len(abyssus.filters) == 7
    assert {row["stat_id"] for row in abyssus.filters} >= {
        "explicit.stat_1379411836",
        "explicit.stat_1573130764",
        "explicit.stat_1062208444",
        "explicit.stat_2734809852",
    }

    paradoxica_id = next(
        item.stable_id
        for item in unique_items.values()
        if item.name_en == "Replica Paradoxica"
    )
    assert templates[paradoxica_id].status == "random_veiled"
    assert templates[paradoxica_id].filters == ()


def test_dictionary_match_uses_name_and_base_and_keeps_verified_thresholds():
    exact = trusted_curio_match("ヴォルカーの導き（レプリカ）\n狂信者のグローブ")
    noisy = trusted_curio_match("ヴォルカーの導き(レプリカ)\n15\n10\n狂信者のグローブ")

    assert exact is not None
    assert exact.item.name_en == "Replica Volkuur's Guidance"
    assert exact.score == 1.0
    assert noisy is not None
    assert noisy.item.stable_id == exact.item.stable_id
    assert trusted_curio_match("レプリカ") is None


def test_ranked_matches_expose_runner_up_margin():
    ranked = rank_curio_matches("カオスオーブ")

    assert ranked[0].item.name_en == "Chaos Orb"
    assert ranked[0].score == 1.0
    assert ranked[0].margin >= 0.15


def test_curio_item_text_parses_into_existing_poetore_categories():
    items = {item.category: item for item in load_curio_items()}

    assert parse_item_text(curio_item_text(items["currency"])).category == "currency"
    assert parse_item_text(curio_item_text(items["scarab"])).category == "scarab"
    assert parse_item_text(curio_item_text(items["experimental_base"])).category in {
        "weapon",
        "armour",
        "accessory",
    }
    assert (
        parse_item_text(curio_item_text(items["replica_unique"])).rarity == "ユニーク"
    )


def _synthetic_curio_image() -> QImage:
    image = QImage(1200, 700, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#101010"))
    painter = QPainter(image)
    painter.setPen(QPen(QColor("#d8a347"), 2))
    for y in (160, 192, 225):
        painter.drawLine(220, y, 760, y)
    for y in (310, 348):
        painter.drawLine(820, y, 1160, y)
    painter.end()
    return image


def test_detect_and_select_cursor_targeted_header_band():
    bands = detect_header_bands(_synthetic_curio_image())

    left = select_header_band(bands, QPoint(500, 190))
    right = select_header_band(bands, QPoint(900, 330))

    assert left is not None
    assert abs(left.top - 160) <= 1
    assert abs(left.bottom - 225) <= 1
    assert left.line_count == 3
    assert right is not None
    assert abs(right.top - 310) <= 1
    assert abs(right.bottom - 348) <= 1
    assert right.line_count == 2
    assert select_header_band(bands, QPoint(790, 250)) is None


def test_select_header_prefers_the_band_nearest_the_cursor_vertically():
    bands = (
        CurioHeaderBand(100, 600, 100, 165, 3),
        CurioHeaderBand(100, 600, 400, 465, 3),
    )

    assert select_header_band(bands, QPoint(300, 430)) == bands[1]


def test_cursor_is_mapped_from_qt_logical_coordinates_to_capture_pixels():
    capture_rect = QRect(200, 100, 1000, 500)
    capture_image = QImage(2000, 1000, QImage.Format.Format_RGBA8888)

    mapped = image_point_for_capture(
        QPoint(700, 325),
        capture_rect,
        capture_image,
    )

    assert mapped == QPoint(1000, 450)
    band = CurioHeaderBand(800, 1400, 400, 500, 3)
    assert select_header_band((band,), mapped) == band
    assert select_header_band((band,), QPoint(500, 225)) is None


class _WindowsOcr:
    def start(self):
        return None

    def recognize(self, _images):
        return ["判定できない文字"]


class _NdlOcr:
    is_available = True

    def recognize(self, _images):
        return [Mock(text="カオスオーブ", confidence=0.9)]

    def close(self):
        return None


def test_controller_uses_ndlocr_only_after_windows_result_is_untrusted(qapp):
    coordinator = Mock()
    controller = HeistCurioController(
        ocr_server=_WindowsOcr(),
        ndl_ocr_server=_NdlOcr(),
        scan_coordinator=coordinator,
    )
    resolved = []
    controller.resolved.connect(
        lambda match, placement: resolved.append((match, placement))
    )
    controller._running = True
    controller._generation = 1
    placement = PlacementContext(QRect(0, 0, 1200, 700), QPoint(400, 200))

    controller._process(b"image", placement, QRect(100, 100, 500, 100), 1)

    assert resolved[0][0].item.name_en == "Chaos Orb"
    assert resolved[0][1] == placement
    coordinator.finish.assert_called_once_with("heist_curio")


def _left_mouse_release(position: QPoint) -> QMouseEvent:
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(position),
        QPointF(position),
        QPointF(position),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_region_selector_accepts_valid_selection_on_mouse_release(qapp):
    selector = CurioRegionSelector(QRect(100, 200, 1000, 800))
    selector._origin = QPoint(10, 10)

    selector.mouseReleaseEvent(_left_mouse_release(QPoint(210, 110)))

    assert selector.result() == QDialog.DialogCode.Accepted
    assert selector.selected_rect == QRect(110, 210, 201, 101)
    selector.close()


def test_region_selector_keeps_tiny_selection_open_for_retry(qapp):
    selector = CurioRegionSelector(QRect(100, 200, 1000, 800))
    selector._origin = QPoint(10, 10)

    selector.mouseReleaseEvent(_left_mouse_release(QPoint(30, 20)))

    assert selector.result() != QDialog.DialogCode.Accepted
    assert selector.selected_rect is None
    assert selector._origin is None
    selector.close()


def test_controller_scan_always_opens_manual_region_selector(qapp):
    controller = HeistCurioController(
        ocr_server=_WindowsOcr(),
        ndl_ocr_server=_NdlOcr(),
    )
    selected = QRect(120, 180, 640, 110)
    image = QImage(640, 110, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#202020"))

    with (
        patch(
            "src.poetore.heist_curio.path_of_exile_client_rect",
            return_value=QRect(0, 0, 1920, 1080),
        ),
        patch("src.poetore.heist_curio.CurioRegionSelector") as selector_class,
        patch.object(controller, "_grab", return_value=image) as grab,
        patch("src.poetore.heist_curio.prepare_curio_ocr_image", return_value=b"image"),
        patch("src.poetore.heist_curio.threading.Thread") as thread_class,
    ):
        selector = selector_class.return_value
        selector.exec.return_value = QDialog.Accepted
        selector.selected_rect = selected

        assert controller.request_scan()

    selector_class.assert_called_once()
    grab.assert_called_once_with(selected)
    assert thread_class.call_args.kwargs["args"][2] == selected
    thread_class.return_value.start.assert_called_once_with()


def test_high_accuracy_status_explains_cold_start(qapp):
    controller = HeistCurioController(
        ocr_server=_WindowsOcr(),
        ndl_ocr_server=_NdlOcr(),
    )
    overlay = Mock()
    controller._high_accuracy_overlay = overlay
    client_rect = QRect(0, 0, 1920, 1080)
    capture_rect = QRect(400, 300, 700, 120)

    controller._show_high_accuracy_status(True, client_rect, capture_rect)

    lines = overlay.show_status.call_args.args[2]
    assert "高精度OCRを準備しています…" in lines
    assert "初回のみ10～15秒ほどかかります" in lines


def test_experimental_base_opens_existing_search_with_empty_optional_ilvl(qapp):
    item = next(
        item for item in load_curio_items() if item.name_ja == "信者のチェーンメイル"
    )
    match = Mock(item=item)
    placement = PlacementContext(QRect(0, 0, 1200, 700), QPoint(400, 200))
    window = PoetoreWindow(app_config={"poe_version": "poe1"})
    window.search_current_item = Mock()
    window._queue_poe_ninja_price = Mock()
    try:
        window.show_heist_curio_match(match, placement)
        qapp.processEvents()

        assert window._parsed_item.name == "信者のチェーンメイル"
        assert window._trade_base_type == "Devout Chainmail"
        assert not window.item_level_tag.isHidden()
        assert window.item_level_edit.text() == ""
        assert not window._item_level_filter_enabled

        window.item_level_edit.setText("83")
        window.item_level_edit.textEdited.emit("83")
        qapp.processEvents()
        assert window._item_level_filter_enabled
        assert window._selected_item_level_range() == (83, None)
        window.search_current_item.assert_called_once_with()
    finally:
        window.close()


def test_heist_unique_opens_fixed_mod_candidates_blank_and_disabled(qapp):
    item = next(
        item for item in load_curio_items() if item.name_en == "Replica Abyssus"
    )
    match = Mock(item=item)
    placement = PlacementContext(QRect(0, 0, 1200, 700), QPoint(400, 200))
    window = PoetoreWindow(app_config={"poe_version": "poe1"})
    window.search_current_item = Mock()
    window._queue_poe_ninja_price = Mock()
    try:
        window.show_heist_curio_match(match, placement)
        qapp.processEvents()

        filters = window._selected_stat_filters()
        assert len(filters) == 7
        assert all(row.kind == "explicit" for row in filters)
        assert all(not row.enabled for row in filters)
        assert all(row.min_value is None and row.max_value is None for row in filters)
        assert all(
            row.selection_reason == "ハイストユニーク固定Mod候補" for row in filters
        )
        window.parse_current_text()
        assert len(window._selected_stat_filters()) == 7
        window.search_current_item.assert_called_once_with()
    finally:
        window.close()
