from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from src.poetore.heist_curio import (
    CurioHeaderBand,
    HeistCurioController,
    curio_item_text,
    detect_header_bands,
    load_curio_items,
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

    controller._process(b"image", placement, 1)

    assert resolved[0][0].item.name_en == "Chaos Orb"
    assert resolved[0][1] == placement
    coordinator.finish.assert_called_once_with("heist_curio")


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
