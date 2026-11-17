"""Inspect the actual text/path commands issued by custom paintEvent methods."""

import ast
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QLabel

from tests.test_theme_geometry_audit import maximum_font, geometry_failures


def inspect_paint(widget, expected_text=()):
    """Record real paint commands on an image of the widget's actual size.

    This measures what is painted, independently of implementation helpers.
    Both the drawing rectangle and its text must fit the widget's canvas.
    """
    failures, painters, commands = [], [], []

    class RecordingPainter(QPainter):
        def __init__(self, target):
            self.canvas = QImage(target.size(), QImage.Format_ARGB32_Premultiplied)
            self.canvas.fill(Qt.transparent)
            super().__init__(self.canvas)
            self.setFont(target.font())
            painters.append(self)

        def drawText(self, rect, flags, text):
            rect = QRectF(rect)
            metrics = self.fontMetrics()
            bounds = metrics.boundingRect(rect.toRect(), int(flags), text)
            commands.append(text)
            if bounds.width() > rect.width() + .01 or bounds.height() > rect.height() + .01:
                failures.append(f"{type(widget).__name__} {text!r}: text {bounds.size()}, drawing rect {rect.size()}")
            if not QRectF(widget.rect()).contains(rect):
                failures.append(f"{type(widget).__name__} {text!r}: drawing rect outside canvas: {rect}")
            return super().drawText(rect, flags, text)

        def _inspect_path(self, path):
            commands.append("outlined text path")
            if not QRectF(widget.rect()).contains(path.boundingRect()):
                failures.append(f"{type(widget).__name__}: text path outside canvas: {path.boundingRect()}")

        def strokePath(self, path, pen):
            self._inspect_path(path)
            radius = pen.widthF() / 2
            if not QRectF(widget.rect()).contains(path.boundingRect().adjusted(-radius, -radius, radius, radius)):
                failures.append(f"{type(widget).__name__}: outlined text outside canvas")
            return super().strokePath(path, pen)

        def fillPath(self, path, brush):
            self._inspect_path(path)
            return super().fillPath(path, brush)

    with patch.object(importlib.import_module(widget.paintEvent.__module__), "QPainter", RecordingPainter):
        try:
            widget.paintEvent(None)
        finally:
            for painter in painters:
                painter.end()
    assert commands, type(widget).__name__
    assert set(expected_text) <= set(commands), (expected_text, commands)
    return failures


def inspect_desecration(qapp, *, narrow=False):
    from src.poetore.poe2.desecration_overlay import DesecrationTierOverlay, STATUS_LABELS
    from src.poetore.poe2.desecration_ocr import ChoiceBand
    from src.poetore.poe2.desecration_tiers import AffixTierOption
    overlay = DesecrationTierOverlay()
    overlay.show_tiers(QRect(0, 0, 1100 if narrow else 1920, 1080), QRect(250, 100, 700, 800), (700, 800),
                       [ChoiceBand(y, y + 80) for y in (20, 140, 260, 380, 500, 660)],
                       (None, None, None, None, (1, 2, 3), 1),
                       statuses=(*STATUS_LABELS, "matched", "matched"),
                       range_labels=((), (), (), (), ("最大エナジーシールド (100–200)%", "(300–400)"), ()),
                       affix_options=((), (), (), (), (), (AffixTierOption("prefix", 1), AffixTierOption("suffix", (2, 3)))),
                       show_ranges=True)
    qapp.processEvents()
    return inspect_paint(overlay, (*STATUS_LABELS.values(), "最大エナジーシールド (100–200)%", "(300–400)"))


@pytest.mark.parametrize("narrow", [False, True])
def test_desecration_painted_text_fits(qapp, narrow):
    assert not (failures := inspect_desecration(qapp, narrow=narrow)), "\n".join(failures)


def inspect_ocr_status(qapp):
    from src.poetore.poe2.desecration_overlay import HighAccuracyOcrStatusOverlay
    failures = []
    overlay = HighAccuracyOcrStatusOverlay()
    for width in (800, 1920):
        overlay.show_status(QRect(0, 0, width, 1080), QRect(50, 400, 620, 290), (
            "通常の読み取りで一部の数値を確認できませんでした", "高精度OCRを準備しています…", "初回のみ10～15秒ほどかかります"))
        qapp.processEvents()
        failures.extend(geometry_failures(overlay))
        failures.extend(inspect_paint(overlay._message))
    return failures


def test_ocr_status_painted_text_fits(qapp):
    assert not (failures := inspect_ocr_status(qapp)), "\n".join(failures)


def inspect_region_selectors(qapp):
    from src.ui.expedition_settings_dialog import ExpeditionRegionSelector, RegionPreview
    from src.ui.desecration_settings_dialog import DesecrationRegionSelector
    from src.poetore.heist_curio import CurioRegionSelector
    failures = []
    for cls in (ExpeditionRegionSelector, DesecrationRegionSelector, CurioRegionSelector):
        widget = cls(QRect(0, 0, 1920, 1080))
        widget.show()
        qapp.processEvents()
        failures.extend(inspect_paint(widget))
    preview = RegionPreview()
    preview.resize(500, 120)
    failures.extend(inspect_paint(preview))
    return failures


def test_region_selector_painted_text_fits(qapp):
    assert not (failures := inspect_region_selectors(qapp)), "\n".join(failures)


def inspect_rate_labels(qapp):
    from src.ui.custom_exchange_rate_panel import DecimalAlignedRateLabel, ElidedLabel
    failures = []
    rate = DecimalAlignedRateLabel("1 ＝ 999,999.000001")
    rate.resize(rate.minimum_rate_width(), rate.sizeHint().height())
    failures.extend(inspect_paint(rate))
    label = ElidedLabel("非常に長いカレンシーの名称を省略表示")
    label.resize(200, label.sizeHint().height())
    failures.extend(inspect_paint(label))
    return failures


def test_rate_label_painted_text_fits(qapp):
    assert not (failures := inspect_rate_labels(qapp)), "\n".join(failures)


def inspect_expedition_price(qapp):
    from src.poetore.expedition_rewards import ExpeditionPriceOverlay, RewardPriceRow
    overlay = ExpeditionPriceOverlay()
    overlay.show_prices(QRect(0, 0, 1920, 1080), 1920, 1080, 600, [RewardPriceRow(200, 260, "9999.5", 9999.5)])
    return inspect_paint(overlay)


def test_expedition_price_painted_text_fits(qapp):
    assert not (failures := inspect_expedition_price(qapp)), "\n".join(failures)


@pytest.mark.parametrize("profile", ["small", "medium", "large"])
def test_unique_roll_painted_text_fits(qapp, profile):
    from dataclasses import replace
    from src.poetore.parser import parse_item_text
    from src.poetore.trade import TradeStatFilter
    from src.poetore.ui import PoetoreWindow, _UniqueRollSlider
    window = PoetoreWindow(app_config={"poetore": {"result_font_size": profile}})
    item = parse_item_text("Item Class: Body Armours\nRarity: Rare\nTest Armour\nSacred Chainmail\n--------\nItem Level: 100")
    window._parsed_item = replace(item, rarity="Unique")
    window._populate_stat_filters((TradeStatFilter("explicit.test", "最大ライフ +#", 100, "explicit", True, read_value=100, roll_min=10, roll_max=100, better=1),))
    window.show()
    qapp.processEvents()
    slider = window.findChild(_UniqueRollSlider)
    assert slider is not None
    for dragging in (False, True):
        slider._dragging, slider._preview = dragging, 55 if dragging else None
        assert not (failures := inspect_paint(slider)), "\n".join(failures)


# Every custom painter is explicitly accounted for. Adding one requires an
# inspector, so a new chip/overlay cannot silently escape this audit.
PAINTERS = {
    "DesecrationTierOverlay": "inspect_desecration",
    "OutlinedLabel": "inspect_ocr_status",
    "ExpeditionRegionSelector": "inspect_region_selectors",
    "CurioRegionSelector": "inspect_region_selectors",
    "RegionPreview": "inspect_region_selectors",
    "DecimalAlignedRateLabel": "inspect_rate_labels",
    "ElidedLabel": "inspect_rate_labels (intentional elision)",
    "ExpeditionPriceOverlay": "inspect_expedition_price",
    "_UniqueRollSlider": "test_unique_roll_painted_text_fits",
    "_SparklineWidget": "No text: only a baseline and a price-trend polyline.",
    "CheatSheetOverlay": "No painter text: frame only; child labels use the window audit.",
}


def test_custom_painter_inventory_is_complete():
    found = set()
    for file in (Path(__file__).resolve().parents[1] / "src").rglob("*.py"):
        for cls in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):
            if isinstance(cls, ast.ClassDef) and any(isinstance(method, ast.FunctionDef) and method.name == "paintEvent" for method in cls.body):
                found.add(cls.name)
                if cls.name in ("_SparklineWidget", "CheatSheetOverlay"):
                    method = next(method for method in cls.body if isinstance(method, ast.FunctionDef) and method.name == "paintEvent")
                    assert not any(isinstance(call, ast.Attribute) and call.attr in ("drawText", "addText") for call in ast.walk(method))
    assert found == PAINTERS.keys()
