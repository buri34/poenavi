from __future__ import annotations

import math
import re
import sys
import threading
import time
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QFontMetrics, QIcon, QIntValidator, QLinearGradient, QPainter,
    QPalette, QPen, QPixmap, QPolygonF,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QLayout,
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QMenu, QScrollArea, QSizeGrip, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    QPlainTextEdit,
    QHeaderView, QWidgetAction,
)

from src.ui.styles import Styles
from src.utils.window_focus import (
    focus_window, get_foreground_window, is_path_of_exile_window,
)

from .parser import ItemParseError, parse_item_text
from .clipboard import clipboard_change_token, read_item_clipboard
from .window_position import (
    PlacementContext,
    capture_placement_context,
    placement_side,
    position_for_context,
    position_from_relative,
    relative_panel_position,
)
from .trade import (
    PRESET_BASE, PRESET_FINISHED, PriceResult, TradeApiError, TradeStatFilter,
    available_pc_leagues, available_trade_presets, default_pc_league, default_trade_currency,
    apply_search_range, english_trade_identity, gem_metadata,
    elemental_dps, physical_dps_at_20_quality,
    japanese_trade_item_label,
    preset_item_level_filter, resolve_trade_stat_filters, search_prices, unique_candidate_details,
    unique_variants, unresolved_modifier_warnings, uses_dedicated_exact_preset,
    is_inscribed_ultimatum,
)
from .poe_ninja import PoeNinjaPrice, default_poe_ninja_service
from .metadata import related_item_group
from .performance import SearchPerformanceTrace, start_search_trace


class _TradeSignals(QObject):
    completed = Signal(object, object, int)
    partial_completed = Signal(object, int)
    failed = Signal(str, int)
    unique_candidates_ready = Signal(object)
    unique_variants_ready = Signal(object)
    leagues_ready = Signal(object)
    poe_ninja_ready = Signal(object, object)
    poe_ninja_failed = Signal(object)
    related_items_ready = Signal(object, object)
    related_items_failed = Signal(object)
    divine_rate_ready = Signal(object, object)
    divine_rate_failed = Signal(object)
    global_mouse_pressed = Signal(int, int)
    global_mouse_moved = Signal(int, int)


_INFLUENCE_CHIPS = {
    "shaper": ("Shaper", "pseudo.pseudo_has_shaper_influence", "influence:shaper"),
    "elder": ("Elder", "pseudo.pseudo_has_elder_influence", "influence:elder"),
    "crusader": ("Crusader", "pseudo.pseudo_has_crusader_influence", "influence:crusader"),
    "hunter": ("Hunter", "pseudo.pseudo_has_hunter_influence", "influence:hunter"),
    "redeemer": ("Redeemer", "pseudo.pseudo_has_redeemer_influence", "influence:redeemer"),
    "warlord": ("Warlord", "pseudo.pseudo_has_warlord_influence", "influence:warlord"),
    "eater": ("Eater", None, "tangled_item"),
    "exarch": ("Exarch", None, "searing_item"),
}

_MOD_COLUMN_CHECK = 0
_MOD_COLUMN_KIND = 1
_MOD_COLUMN_TIER = 2
_MOD_COLUMN_TEXT = 3
_MOD_COLUMN_MIN = 4
_MOD_COLUMN_MAX = 5
_MOD_CHECK_COLUMN_WIDTH = 40
_MOD_TIER_COLUMN_WIDTH = 62
_MOD_TEXT_COLUMN_WIDTH = 320
_MOD_VALUE_EDITOR_WIDTH = 48
_MOD_VALUE_LEADING_GAP = 8
_MOD_ROW_HEIGHT = 36
_UNIQUE_ROLL_ROW_HEIGHT = 62
_UNIQUE_CANDIDATE_ROW_HEIGHT = 64
_UNIQUE_CANDIDATE_ROW_SPACING = 6
_UNIQUE_CANDIDATE_VISIBLE_ROWS = 3
_UNIQUE_CANDIDATE_VIEWPORT_HEIGHT = (
    _UNIQUE_CANDIDATE_ROW_HEIGHT * _UNIQUE_CANDIDATE_VISIBLE_ROWS
    + _UNIQUE_CANDIDATE_ROW_SPACING * (_UNIQUE_CANDIDATE_VISIBLE_ROWS - 1)
)
_RELATED_ITEMS_TREE_HEIGHT = 180
_RELATED_ITEMS_PRICE_HEIGHT_REDUCTION = 180
_DISPLAY_SIZE_PROFILES = {
    "small": {
        "font": 12, "width": 560, "height": 1039,
        "mod_value_font": 11,
        "search_button_width": 105,
        "minimum_width": 540, "minimum_height": 620,
        "mod_height": 230, "price_height": 434,
        "button_v_padding": 5, "button_h_padding": 9,
    },
    "medium": {
        "font": 14, "width": 650, "height": 1039,
        "mod_value_font": 12,
        "search_button_width": 122,
        "minimum_width": 610, "minimum_height": 620,
        "mod_height": 250, "price_height": 434,
        "button_v_padding": 6, "button_h_padding": 11,
    },
    "large": {
        "font": 16, "width": 740, "height": 1039,
        "mod_value_font": 14,
        "search_button_width": 140,
        "minimum_width": 680, "minimum_height": 620,
        "mod_height": 270, "price_height": 434,
        "button_v_padding": 7, "button_h_padding": 13,
    },
}


def normalize_result_font_size(value) -> str:
    normalized = str(value or "medium").casefold()
    return normalized if normalized in _DISPLAY_SIZE_PROFILES else "medium"


def _auto_mod_layout_sizes(
    *, profile_height: int, profile_mod_height: int,
    profile_price_height: int, minimum_price_height: int,
    content_height: int, available_height: int, minimum_height: int,
) -> tuple[int, int, int]:
    """Mod行へ価格欄の高さも振り替え、ウィンドウを作業領域内へ収める。"""
    wanted_mod_height = max(profile_mod_height, content_height)
    fixed_height = profile_height - profile_mod_height - profile_price_height
    wanted_window_height = fixed_height + wanted_mod_height + profile_price_height
    window_height = min(
        wanted_window_height,
        max(minimum_height, available_height - 16),
    )
    flexible_height = max(
        80 + minimum_price_height,
        window_height - fixed_height,
    )
    # Mod条件を優先する。ただし検索結果が操作不能にならない最低高は残す。
    mod_height = min(
        wanted_mod_height,
        max(80, flexible_height - minimum_price_height),
    )
    price_height = max(
        minimum_price_height,
        min(profile_price_height, flexible_height - mod_height),
    )
    return mod_height, price_height, window_height
_SPECIAL_CHIP_FILTER_IDS = {
    "property.map_tier", "property.area_level", "property.heist_wings",
    "property.base_percentile",
    "property.map_blighted", "property.map_uberblighted",
    "property.map_completion_reward",
}


def _roll_decimal_places(value: float, decimal: bool) -> int:
    """Match Awakened's stat-specific display precision."""
    if not decimal or abs(value) >= 10:
        return 0
    return 2 if abs(value) < 2.3 else 1


def _rounded_slider_value(value: float, decimal: bool, *, upper: bool) -> float:
    places = _roll_decimal_places(value, decimal)
    scale = 10 ** places
    adjusted = value * scale
    rounded = math.ceil(adjusted - 1e-9) if upper else math.floor(adjusted + 1e-9)
    return rounded / scale


class _UniqueRollSlider(QWidget):
    """Qt counterpart of Awakened's StatRollSlider for comparable unique rolls."""

    valueCommitted = Signal(object, object)

    def __init__(
        self, bounds: tuple[float, float], roll: float, better: int,
        decimal: bool, parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._low, self._high = bounds
        self._roll = min(max(roll, self._low), self._high)
        self._better = better
        self._decimal = decimal
        self._minimum: float | None = None
        self._maximum: float | None = None
        self._preview: float | None = None
        self._dragging = False
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("クリックまたはドラッグで検索値を調整")

    def searchValues(self) -> tuple[float | None, float | None]:
        return self._minimum, self._maximum

    def setSearchValues(self, minimum: float | None, maximum: float | None):
        self._minimum = minimum
        self._maximum = maximum
        self.update()

    def _value_at(self, x: float) -> float:
        width = max(1.0, float(self.width()))
        ratio = min(1.0, max(0.0, x / width))
        raw = self._low + (self._high - self._low) * ratio
        value = _rounded_slider_value(
            raw, self._decimal, upper=self._better < 0,
        )
        return min(self._high, max(self._low, value))

    def _position(self, value: float) -> float:
        span = self._high - self._low
        if span <= 0:
            return 0.0
        return min(
            float(self.width()),
            max(0.0, (value - self._low) / span * self.width()),
        )

    @staticmethod
    def _format(value: float) -> str:
        return f"{value:g}"

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self._dragging = True
        self._preview = self._value_at(event.position().x())
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return super().mouseMoveEvent(event)
        self._preview = self._value_at(event.position().x())
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._dragging:
            return super().mouseReleaseEvent(event)
        self._preview = self._value_at(event.position().x())
        if self._better > 0:
            self._minimum, self._maximum = self._preview, None
        else:
            self._minimum, self._maximum = None, self._preview
        self._dragging = False
        self._preview = None
        self.update()
        self.valueCommitted.emit(self._minimum, self._maximum)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 3, -1, -3)
        painter.setPen(QPen(QColor("#46504D"), 1))
        painter.setBrush(QColor("#202628"))
        painter.drawRoundedRect(rect, 3, 3)

        active = self._preview
        if active is None:
            active = self._minimum if self._better > 0 else self._maximum
        if active is not None:
            x = int(self._position(active))
            fill = QRect(
                x if self._better > 0 else 0,
                rect.top(),
                max(1, rect.right() - x + 1) if self._better > 0 else max(1, x),
                rect.height(),
            )
            painter.setPen(Qt.NoPen)
            gradient = QLinearGradient(fill.left(), 0, fill.right(), 0)
            if self._better > 0:
                gradient.setColorAt(0.0, QColor("#7f8781"))
                gradient.setColorAt(1.0, QColor("#eef1ed"))
            else:
                gradient.setColorAt(0.0, QColor("#eef1ed"))
                gradient.setColorAt(1.0, QColor("#7f8781"))
            painter.setBrush(gradient)
            painter.drawRoundedRect(fill, 3, 3)

        roll_x = int(self._position(self._roll))
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawLine(roll_x, rect.top(), roll_x, rect.bottom())

        painter.setPen(QColor("#c6cec1"))
        painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignLeft | Qt.AlignVCenter, self._format(self._low))
        painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignRight | Qt.AlignVCenter, self._format(self._high))
        if self._dragging and self._preview is not None:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect, Qt.AlignCenter, self._format(self._preview))


def _is_valdo_map(item) -> bool:
    return (
        item.category == "map"
        and (item.base_type or "").strip().casefold()
        in {"valdo map", "ヴァルドマップ"}
    )


_FILTER_KIND_LABELS = {
    "explicit": "明示",
    "prefix": "プレフィックス",
    "suffix": "サフィックス",
    "crafted": "クラフト",
    "fractured": "フラクチャー",
    "implicit": "暗黙",
    "enchant": "エンチャント",
    "veiled": "ヴェール",
    "desecrated": "冒涜",
    "necropolis": "ネクロポリス",
    "imbued": "注入",
    "foulborn": "ファウルボーン",
    "vestigial": "痕跡",
    "essence": "エッセンス",
    "infamous": "悪名高い",
    "corrupted": "コラプト",
    "eldritch": "エルドリッチ",
    "synthesised": "シンセシス",
    "delve": "デルブ",
    "incursion": "インカージョン",
    "veiled": "ヴェール",
    "shaper": "シェイパー",
    "elder": "エルダー",
    "hunter": "ハンター",
    "warlord": "ウォーロード",
    "redeemer": "リディーマー",
    "crusader": "クルセーダー",
    "pseudo": "疑似",
    "property": "アイテム特性",
    "base": "ベース",
    "cluster": "クラスター",
    "craft": "クラフト",
    "expedition": "エクスペディション",
    "flask hybrid": "フラスコ複合",
    "gem": "ジェム",
    "heist": "ハイスト",
    "influence": "インフルエンス",
    "map": "マップ",
    "map pseudo": "マップ",
    "map safety": "マップ危険",
    "sanctum": "サンクタム",
    "socket": "ソケット",
    "special": "特殊",
    "unique exception": "ユニーク例外",
    "mercenary": "MERCENARY",
}


def _filter_kind_label(stat_filter: TradeStatFilter) -> str:
    kind = (
        stat_filter.generation
        if stat_filter.generation in _FILTER_KIND_LABELS
        else stat_filter.kind
    )
    return _FILTER_KIND_LABELS.get(kind, "特殊")


def _replace_filters_with_special_chips(
    filters: tuple[TradeStatFilter, ...],
    influence_filters: tuple[TradeStatFilter, ...],
    special_filters: tuple[TradeStatFilter, ...],
) -> tuple[TradeStatFilter, ...]:
    """専用チップへ移した条件を、元のフィルターと二重送信しない。"""
    replaced_ids = _SPECIAL_CHIP_FILTER_IDS | {
        row.stat_id for row in influence_filters + special_filters
    }
    return tuple(
        row for row in filters
        if row.stat_id not in replaced_ids and row.kind != "influence"
    ) + influence_filters + special_filters


def _influence_chip_icon(label: str, active: bool) -> QIcon:
    """チェック、Influence画像の順で1つのボタンアイコンへ合成する。"""
    result = QPixmap(38, 20)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#E6ECEA" if active else "#737D79"))
    painter.drawText(QRect(0, 0, 16, 20), Qt.AlignCenter, "☑" if active else "☐")
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "icons" / f"{label}.png"
    influence = QPixmap(str(icon_path))
    if not influence.isNull():
        painter.drawPixmap(18, 0, 20, 20, influence)
    painter.end()
    return QIcon(result)


_PRICE_CURRENCY_ICONS = {
    "chaos": "ChaosOrb.png",
    "divine": "DivineOrb.png",
}


def _asset_icon_path(filename: str) -> Path | None:
    """開発実行・配布EXEのどちらでも同梱アイコンを解決する。"""
    source_root = Path(__file__).resolve().parents[2]
    executable_root = Path(sys.executable).resolve().parent
    roots = (executable_root, Path(getattr(sys, "_MEIPASS", source_root)), source_root)
    for root in roots:
        path = root / "assets" / "icons" / filename
        if path.is_file():
            return path
    return None


class _FlowLayout(QLayout):
    """表示中の検索チップを利用可能な横幅で自動折り返しするレイアウト。"""

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def ordered_widgets(self) -> tuple[QWidget, ...]:
        return tuple(item.widget() for item in self._items if item.widget() is not None)

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        available = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = available.x()
        y = available.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width()
            if line_height and next_x > available.right() + 1:
                x = available.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h_spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class _BinaryToggle(QWidget):
    """2つの状態をプルダウンなしで切り替えるセグメント型トグル。"""

    currentIndexChanged = Signal(int)

    def __init__(self, first: tuple[str, object], second: tuple[str, object], parent=None):
        super().__init__(parent)
        self._options = (first, second)
        self._current_index = 0
        self._second_available = True
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._buttons = []
        for index, (label, _) in enumerate(self._options):
            button = QPushButton(label)
            button.setObjectName("binaryToggle")
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.clicked.connect(lambda checked=False, value=index: self.setCurrentIndex(value))
            layout.addWidget(button, 1)
            self._buttons.append(button)
        # 片側しか使わない場合も、2択時の1セグメントと同じ幅を保つ。
        # 非表示にした第2ボタンの代わりに、同じ伸縮率の空領域を置く。
        self._empty_segment = QWidget()
        self._empty_segment.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._empty_segment.hide()
        layout.addWidget(self._empty_segment, 1)
        self._sync_buttons()

    def _sync_buttons(self):
        for index, button in enumerate(self._buttons):
            button.setChecked(index == self._current_index)

    def setCurrentIndex(self, index: int):
        index = 1 if index == 1 and self._second_available else 0
        if index == self._current_index:
            self._sync_buttons()
            return
        self._current_index = index
        self._sync_buttons()
        self.currentIndexChanged.emit(index)

    def currentData(self):
        return self._options[self._current_index][1]

    def currentText(self) -> str:
        return self._options[self._current_index][0]

    def itemData(self, index: int):
        return self._options[index][1]

    def itemText(self, index: int) -> str:
        return self._options[index][0]

    def setItemText(self, index: int, text: str):
        if index not in (0, 1):
            raise IndexError(index)
        options = list(self._options)
        options[index] = (str(text), options[index][1])
        self._options = tuple(options)
        self._buttons[index].setText(str(text))

    def count(self) -> int:
        return 2 if self._second_available else 1

    def setSecondAvailable(self, available: bool):
        self._second_available = available
        self._buttons[1].setVisible(available)
        self._empty_segment.setVisible(not available)
        if not available and self._current_index == 1:
            self.setCurrentIndex(0)


class _CycleButton(QPushButton):
    """1つのボタンで複数の検索状態を順番に切り替える。"""

    currentIndexChanged = Signal(int)

    def __init__(self, options: tuple[tuple[str, object, bool], ...], parent=None):
        super().__init__(parent)
        if not options:
            raise ValueError("options must not be empty")
        self._options = options
        self._current_index = 0
        self.setObjectName("cycleToggle")
        self.clicked.connect(self._advance)
        self._sync_state()

    def _advance(self):
        self.setCurrentIndex((self._current_index + 1) % len(self._options))

    def _sync_state(self):
        label, _, alert = self._options[self._current_index]
        self.setText(label)
        # チェック表示を持たない状態チップも、現在選択中の検索方針として
        # 常に有効色で表示する。状態によってAPI条件が未指定になる場合でも、
        # UI上ではユーザーが選んだ方針であることを明確にする。
        self.setProperty("active", True)
        self.setProperty("alert", alert)
        self.style().unpolish(self)
        self.style().polish(self)

    def setCurrentIndex(self, index: int):
        index = int(index) % len(self._options)
        if index == self._current_index:
            self._sync_state()
            return
        self._current_index = index
        self._sync_state()
        self.currentIndexChanged.emit(index)

    def currentData(self):
        return self._options[self._current_index][1]

    def currentText(self) -> str:
        return self._options[self._current_index][0]

    def itemData(self, index: int):
        return self._options[index][1]

    def itemText(self, index: int) -> str:
        return self._options[index][0]

    def count(self) -> int:
        return len(self._options)


class _AreaSegmentedControl(QWidget):
    """Logbookの最大5エリアを横並びで選ぶ専用セグメント。"""

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._buttons = []
        self._current = 0
        self.hide()

    def setLabels(self, labels):
        while self._buttons:
            self._buttons.pop().deleteLater()
        for index, label in enumerate(tuple(labels)[:5]):
            button = QPushButton(str(label))
            button.setObjectName("binaryToggle")
            button.setCheckable(True)
            button.setMinimumWidth(
                button.fontMetrics().horizontalAdvance(str(label)) + 24
            )
            button.clicked.connect(lambda checked=False, value=index: self.setCurrentIndex(value))
            self._layout.addWidget(button)
            self._buttons.append(button)
        self._current = 0
        self._sync()
        self.setVisible(bool(self._buttons))

    def setCurrentIndex(self, index):
        if not self._buttons:
            return
        index = max(0, min(int(index), len(self._buttons) - 1))
        changed = index != self._current
        self._current = index
        self._sync()
        if changed:
            self.currentIndexChanged.emit(index)

    def _sync(self):
        for index, button in enumerate(self._buttons):
            button.setChecked(index == self._current)
            button.ensurePolished()
            button.setMinimumWidth(
                button.fontMetrics().horizontalAdvance(button.text()) + 24
            )


class _NumericFilterChip(QFrame):
    """ON/OFFと最小値（必要なら最大値）を持つ共通検索チップ。"""

    def __init__(
        self, label: str, minimum: int, maximum: int, parent=None, suffix: str = "",
    ):
        super().__init__(parent)
        self.setObjectName("numericFilterTag")
        self._active = True
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(1)
        self.toggle = QPushButton()
        self.toggle.setObjectName("numericFilterToggle")
        self._label = label
        self.toggle.clicked.connect(lambda: self.setActive(not self._active))
        layout.addWidget(self.toggle)
        self.minimum_edit = QLineEdit()
        self.minimum_edit.setObjectName("numericFilterEdit")
        self.minimum_edit.setValidator(QIntValidator(minimum, maximum, self.minimum_edit))
        self.minimum_edit.setAlignment(Qt.AlignCenter)
        self.minimum_edit.setFixedWidth(30)
        self.minimum_edit.textEdited.connect(lambda _text: self.setActive(True))
        layout.addWidget(self.minimum_edit)
        self.separator = QLabel("～")
        self.maximum_edit = QLineEdit()
        self.maximum_edit.setObjectName("numericFilterEdit")
        self.maximum_edit.setValidator(QIntValidator(minimum, maximum, self.maximum_edit))
        self.maximum_edit.setAlignment(Qt.AlignCenter)
        self.maximum_edit.setFixedWidth(30)
        self.maximum_edit.textEdited.connect(lambda _text: self.setActive(True))
        layout.addWidget(self.separator)
        layout.addWidget(self.maximum_edit)
        self.suffix_label = QLabel(suffix)
        self.suffix_label.setVisible(bool(suffix))
        layout.addWidget(self.suffix_label)
        self.setRangeVisible(False)
        self.setActive(True)

    def setValues(self, minimum: float | None, maximum: float | None = None):
        self.minimum_edit.setText("" if minimum is None else f"{minimum:g}")
        self.maximum_edit.setText("" if maximum is None else f"{maximum:g}")
        self.setRangeVisible(maximum is not None)

    def values(self) -> tuple[float | None, float | None]:
        minimum = self.minimum_edit.text().strip()
        maximum = self.maximum_edit.text().strip() if not self.maximum_edit.isHidden() else ""
        return (float(minimum) if minimum else None, float(maximum) if maximum else None)

    def setRangeVisible(self, visible: bool):
        self.separator.setVisible(visible)
        self.maximum_edit.setVisible(visible)

    def setActive(self, active: bool):
        self._active = bool(active)
        self.setProperty("active", self._active)
        self.toggle.setText(f"{'☑' if self._active else '☐'} {self._label}：")
        for editor in (self.minimum_edit, self.maximum_edit):
            font = editor.font()
            font.setStrikeOut(not self._active)
            editor.setFont(font)
        self.style().unpolish(self)
        self.style().polish(self)

    def isActive(self) -> bool:
        return self._active


class _SparklineWidget(QWidget):
    """poe.ninjaの7日変動率を追加依存なしで描画する。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: tuple[float, ...] = ()
        self.setFixedSize(116, 24)
        self.setToolTip("poe.ninja 7日推移")

    def setPoints(self, points: tuple[float, ...]):
        self._points = tuple(points)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#56615D"), 1, Qt.DashLine))
        middle = self.height() / 2
        painter.drawLine(0, round(middle), self.width(), round(middle))
        if len(self._points) < 2:
            return
        low, high = min(self._points), max(self._points)
        spread = max(high - low, 1.0)
        polygon = QPolygonF()
        for index, value in enumerate(self._points):
            x = index * (self.width() - 2) / (len(self._points) - 1) + 1
            y = 1 + (high - value) * (self.height() - 2) / spread
            polygon.append(QPointF(x, y))
        color = "#49D6B0" if self._points[-1] >= self._points[0] else "#ff6b6b"
        painter.setPen(QPen(QColor(color), 1.5))
        painter.drawPolyline(polygon)


class _PoetoreTitleBar(QWidget):
    """Small draggable title bar for the frameless price-check panel."""

    def __init__(self, window: "PoetoreWindow"):
        super().__init__(window)
        self.setObjectName("poetoreTitleBar")
        self._window = window
        self._drag_offset: QPoint | None = None
        self._drag_start_position: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        title = QLabel("ぽえとれ")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        window.divine_rate_button = QPushButton("⇄ …")
        window.divine_rate_button.setObjectName("divineRateButton")
        window.divine_rate_button.setToolTip("Divine OrbのChaos換算早見表")
        window.divine_rate_button.setEnabled(False)
        window.divine_rate_button.hide()
        window.divine_rate_menu = QMenu(window.divine_rate_button)
        window.divine_rate_menu.setObjectName("divineRateMenu")
        window.divine_rate_button.setMenu(window.divine_rate_menu)
        layout.addWidget(window.divine_rate_button)
        layout.addStretch()
        layout.addWidget(window.trade_league_combo)
        window.league_popup_button = QPushButton("▼")
        window.league_popup_button.setObjectName("leaguePopupButton")
        window.league_popup_button.setToolTip("リーグ一覧を開く")
        window.league_popup_button.setFixedSize(28, 28)
        window.league_popup_button.clicked.connect(window.trade_league_combo.showPopup)
        layout.addWidget(window.league_popup_button)
        layout.addStretch()
        window.poetore_close_button = QPushButton("×")
        window.poetore_close_button.setToolTip("閉じる")
        window.poetore_close_button.setFixedSize(28, 24)
        window.poetore_close_button.clicked.connect(window._close_and_return_to_poe)
        layout.addWidget(window.poetore_close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            self._drag_start_position = self._window.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        moved = (
            self._drag_offset is not None
            and self._drag_start_position is not None
            and self._window.pos() != self._drag_start_position
        )
        self._drag_offset = None
        self._drag_start_position = None
        if moved:
            self._window._persist_manual_result_position()
        super().mouseReleaseEvent(event)


class PoetoreWindow(QWidget):
    """貼り付け解析だけを行う、Trade API未接続のローカル試作画面。"""

    def __init__(self, parent=None, app_config=None, save_config=None):
        super().__init__(parent)
        self._app_config = app_config if isinstance(app_config, dict) else {}
        self._save_app_config = save_config
        self._league_refresh_started = False
        self._auto_league: str | None = None
        self._has_searched_current_item = False
        self._search_dirty = False
        self._search_generation = 0
        self._active_item_key: str | None = None
        self._auto_search_queued = False
        self._unique_icon_manager = QNetworkAccessManager(self)
        self._unique_icon_manager.finished.connect(self._unique_icon_downloaded)
        self._unique_icon_requests: dict[QNetworkReply, tuple[int, str]] = {}
        self._unique_icon_cache: dict[str, QIcon] = {}
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # PoENavi本体には入力透過（クリックスルー）機能があるため、
        # ぽえとれ側では常にマウス入力を受け取れる状態を明示する。
        self.setWindowFlag(Qt.WindowTransparentForInput, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # 非アクティブ表示を明示した場合だけフォーカスを奪わない。
        # Alt+Dの検索結果はAwakenedの操作可能モード同様、明示的にactivateWindow()する。
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setEnabled(True)
        # Alt+Dで表示した直後に編集欄へ文字が入らないよう、ウィンドウ自身を
        # 安全なフォーカス先にする。各入力欄は必要な時だけ個別にフォーカスする。
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("ぽえとれ")
        self._result_font_size = normalize_result_font_size(
            self._app_config.get("poetore", {}).get("result_font_size", "medium")
        )
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        self.resize(profile["width"], profile["height"])
        self.setMinimumSize(profile["minimum_width"], profile["minimum_height"])
        self.trade_league_combo = QComboBox()
        self.trade_league_combo.setEditable(True)
        # Private Leagueの直接入力は維持しつつ、ウィンドウ表示時やTab移動では
        # リーグ欄を自動フォーカス対象にしない。
        self.trade_league_combo.setFocusPolicy(Qt.ClickFocus)
        self.trade_league_combo.lineEdit().setFocusPolicy(Qt.ClickFocus)
        self.trade_league_combo.setFixedWidth(290)
        self.trade_league_combo.setMinimumContentsLength(12)
        self.trade_league_combo.setToolTip("一覧から選択、またはPrivate League IDを直接入力")
        self.trade_league_combo.addItem("自動（現行SCを取得中）", "auto")
        saved_league = str(self._app_config.get("poetore", {}).get("league", "auto"))
        if saved_league != "auto":
            self.trade_league_combo.addItem(saved_league, saved_league)
            self.trade_league_combo.setCurrentIndex(1)
        self.trade_league_combo.currentIndexChanged.connect(self._persist_trade_league)
        self.trade_league_combo.lineEdit().editingFinished.connect(self._persist_trade_league)
        self._placement_context: PlacementContext | None = None
        self._poe_window_hwnd: int | None = None
        self._focus_signal_connected = False
        self._outside_click_listener = None
        self._passive_hotkey_display = False
        self._capture_auto_hide = False
        self._auto_hide_hotkey_released = False
        self._auto_hide_origin: QPoint | None = None
        self._auto_hide_interactive = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._panel = QFrame(self)
        self._panel.setObjectName("poetorePanel")
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(10, 5, 10, 9)
        panel_layout.setSpacing(7)
        panel_layout.addWidget(_PoetoreTitleBar(self))
        layout.addWidget(self._panel)

        self.item_header = QFrame()
        self.item_header.setObjectName("itemHeader")
        item_header_layout = QVBoxLayout(self.item_header)
        item_header_layout.setContentsMargins(10, 7, 10, 7)
        item_header_layout.setSpacing(1)
        self.item_name_label = QLabel("アイテムを読み取ってください")
        self.item_name_label.setObjectName("itemName")
        self.base_scope_toggle = _BinaryToggle(("ベース名", True), ("同一クラスすべて", False))
        self.base_scope_toggle.setToolTip(
            "読み取ったベースタイプに絞るか、同じアイテムクラス全体から探すかを切り替えます。"
        )
        self.base_scope_toggle.currentIndexChanged.connect(self._base_scope_changed)
        self.base_scope_toggle.hide()
        self.corrupted_combo = _CycleButton((
            ("コラプトのみ", "only", True),
            ("非コラプトのみ", False, False),
            ("コラプト品含む", True, False),
        ))
        self.corrupted_combo.setToolTip("クリックするたびにコラプト条件を切り替えます")
        self.corrupted_combo.setCurrentIndex(1)
        item_header_layout.addWidget(self.item_name_label)
        item_scope_layout = QHBoxLayout()
        item_scope_layout.setContentsMargins(0, 0, 0, 0)
        item_scope_layout.setSpacing(6)
        item_scope_layout.addWidget(self.base_scope_toggle, stretch=1)
        item_scope_layout.addStretch()
        item_scope_layout.addWidget(self.corrupted_combo)
        item_header_layout.addLayout(item_scope_layout)
        panel_layout.addWidget(self.item_header)

        # poe.ninjaデータ取得は後続タスク。先に共通情報階層と差し込み口を固定する。
        self.poe_ninja_price_panel = QFrame()
        self.poe_ninja_price_panel.setObjectName("poeNinjaPricePanel")
        ninja_layout = QHBoxLayout(self.poe_ninja_price_panel)
        ninja_layout.setContentsMargins(8, 5, 8, 5)
        ninja_layout.setSpacing(8)
        self.poe_ninja_price_label = QLabel("poe.ninja 参考価格")
        self.poe_ninja_price_label.setObjectName("poeNinjaPriceLabel")
        self.poe_ninja_price_value = QLabel("—")
        self.poe_ninja_price_value.setObjectName("poeNinjaPriceValue")
        self.poe_ninja_price_multiplier = QLabel("×")
        self.poe_ninja_price_multiplier.setObjectName("poeNinjaPriceMultiplier")
        self.poe_ninja_currency_icon = QLabel()
        self.poe_ninja_currency_icon.setObjectName("poeNinjaCurrencyIcon")
        self.poe_ninja_currency_icon.setFixedSize(28, 28)
        self.poe_ninja_currency_icon.setAlignment(Qt.AlignCenter)
        self.poe_ninja_trend_label = QLabel("")
        self.poe_ninja_trend_label.setObjectName("poeNinjaTrendLabel")
        self.poe_ninja_trend_chart = _SparklineWidget()
        # 旧テスト・後続実装から差し込み口を参照できる別名。
        self.poe_ninja_trend_placeholder = self.poe_ninja_trend_chart
        self.poe_ninja_open_button = QPushButton("poe.ninja  ↗")
        self.poe_ninja_open_button.setObjectName("poeNinjaOpenButton")
        self.poe_ninja_open_button.clicked.connect(self._open_poe_ninja_url)
        ninja_layout.addStretch()
        ninja_layout.addWidget(self.poe_ninja_price_label)
        ninja_layout.addWidget(self.poe_ninja_price_value)
        ninja_layout.addWidget(self.poe_ninja_price_multiplier)
        ninja_layout.addWidget(self.poe_ninja_currency_icon)
        ninja_layout.addWidget(self.poe_ninja_trend_label)
        ninja_layout.addWidget(self.poe_ninja_trend_chart)
        ninja_layout.addWidget(self.poe_ninja_open_button)
        self.poe_ninja_price_panel.hide()
        panel_layout.addWidget(self.poe_ninja_price_panel)

        self.related_items_panel = QFrame()
        self.related_items_panel.setObjectName("relatedItemsPanel")
        related_layout = QVBoxLayout(self.related_items_panel)
        related_layout.setContentsMargins(8, 6, 8, 6)
        related_layout.setSpacing(4)
        related_title = QLabel("関連アイテムのpoe.ninja参考価格")
        related_title.setObjectName("relatedItemsTitle")
        related_layout.addWidget(related_title)
        self.related_items_tree = QTreeWidget()
        self.related_items_tree.setObjectName("relatedItemsTree")
        self.related_items_tree.setColumnCount(2)
        self.related_items_tree.setHeaderLabels(("アイテム", "価格"))
        self.related_items_tree.setRootIsDecorated(True)
        self.related_items_tree.setAlternatingRowColors(True)
        self.related_items_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.related_items_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.related_items_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.related_items_tree.setMaximumHeight(_RELATED_ITEMS_TREE_HEIGHT)
        related_layout.addWidget(self.related_items_tree)
        self.related_items_panel.hide()
        panel_layout.addWidget(self.related_items_panel)

        top_options = QHBoxLayout()
        top_options.setSpacing(6)
        self.trade_preset_combo = _BinaryToggle(
            ("完成品", PRESET_FINISHED), ("ベースアイテム", PRESET_BASE),
        )
        self.trade_preset_combo.currentIndexChanged.connect(self._trade_preset_changed)
        # 検索プリセットは左半分だけを使い、下のMod表との視線移動を短くする。
        # 切替候補がない場合は固定状態を説明するだけのボタンを出さず、同じ幅の空白を
        # 残して右側のMod数値コントロールの位置を動かさない。
        top_options.addWidget(self.trade_preset_combo, 1)
        self.trade_preset_placeholder = QWidget()
        self.trade_preset_placeholder.hide()
        top_options.addWidget(self.trade_preset_placeholder, 1)
        top_options.addStretch(1)
        self.search_range_combo = QComboBox()
        self.search_range_combo.setObjectName("filterControl")
        for percent in (0, 5, 10, 15, 20, 30, 50):
            label = (
                "Mod数値：完全一致"
                if percent == 0
                else f"Mod数値：-{percent}%まで許容"
            )
            self.search_range_combo.addItem(label, percent)
        saved_range = self._app_config.get("poetore", {}).get("search_stat_range", 10)
        try:
            saved_range = int(saved_range)
        except (TypeError, ValueError):
            saved_range = 10
        index = self.search_range_combo.findData(saved_range)
        self.search_range_combo.setCurrentIndex(index if index >= 0 else 2)
        self.search_range_combo.setToolTip(
            "各Modの読取値を基準に、どこまで低い数値を検索に含めるか設定します。\n"
            "例：読取値100・-10%まで許容 → 最小値90で検索\n"
            "ユニーク品はModの可変範囲を基準に調整します。"
        )
        self.search_range_combo.currentIndexChanged.connect(self._search_range_changed)
        top_options.addWidget(self.search_range_combo)
        self.magic_rarity_toggle = _BinaryToggle(
            ("ユニーク以外", False), ("マジック完全一致", True),
        )
        self.magic_rarity_toggle.setToolTip(
            "マジックのベースアイテムだけに絞る場合は「マジック完全一致」を選択"
        )
        self.magic_rarity_toggle.hide()

        self.trade_status_combo = QComboBox()
        self.trade_status_combo.setObjectName("filterControl")
        self.trade_status_combo.setProperty("compactAction", True)
        self.trade_status_combo.addItem("インスタントバイアウトのみ", "instant")
        self.trade_status_combo.addItem("インスタント＋対面", "available")
        self.trade_status_combo.addItem("対面トレードのみ", "online")
        self.trade_status_combo.addItem("オフライン出品も含む", "offline")
        self.trade_currency_combo = QComboBox()
        self.trade_currency_combo.setObjectName("filterControl")
        self.trade_currency_combo.setProperty("compactAction", True)
        self.trade_currency_combo.addItem("すべての通貨", "any")
        self.trade_currency_combo.addItem("カオスオーブのみ", "chaos")
        self.trade_currency_combo.addItem("神のオーブのみ", "divine")
        self.trade_currency_combo.addItem(
            "カオスまたは神のオーブ", "chaos_divine"
        )
        self.listed_within_combo = QComboBox()
        self.listed_within_combo.setObjectName("filterControl")
        self.listed_within_combo.setProperty("compactAction", True)
        for label, value in (
            ("期間指定なし", "any"), ("24時間以内", "1day"), ("3日以内", "3days"),
            ("1週間以内", "1week"), ("2週間以内", "2weeks"),
            ("1か月以内", "1month"), ("2か月以内", "2months"),
        ):
            self.listed_within_combo.addItem(label, value)

        unique_options = QVBoxLayout()
        self.unique_name_label = QLabel("未鑑定ユニーク候補:")
        self.unique_name_container = QWidget()
        self.unique_name_container.setObjectName("uniqueCandidateContainer")
        self.unique_name_layout = _FlowLayout(
            self.unique_name_container,
            h_spacing=6,
            v_spacing=_UNIQUE_CANDIDATE_ROW_SPACING,
        )
        self.unique_name_scroll = QScrollArea()
        self.unique_name_scroll.setObjectName("uniqueCandidateScroll")
        self.unique_name_scroll.setWidgetResizable(True)
        self.unique_name_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.unique_name_scroll.setFixedHeight(_UNIQUE_CANDIDATE_VIEWPORT_HEIGHT)
        self.unique_name_scroll.setFrameShape(QFrame.NoFrame)
        self.unique_name_scroll.setWidget(self.unique_name_container)
        self.unique_name_group = QButtonGroup(self)
        self.unique_name_group.setExclusive(True)
        self.unique_name_label.hide()
        self.unique_name_container.hide()
        self.unique_name_scroll.hide()
        unique_options.addWidget(self.unique_name_label)
        unique_options.addWidget(self.unique_name_scroll)
        variant_options = QHBoxLayout()
        self.unique_variant_label = QLabel("ユニークVariant:")
        self.unique_variant_combo = QComboBox()
        self.unique_variant_label.hide()
        self.unique_variant_combo.hide()
        variant_options.addWidget(self.unique_variant_label)
        variant_options.addWidget(self.unique_variant_combo)
        variant_options.addStretch()
        unique_options.addLayout(variant_options)
        panel_layout.addLayout(unique_options)

        self.filter_chip_container = QWidget()
        self.filter_chip_container.setObjectName("filterChipContainer")
        self.filter_chip_layout = _FlowLayout(self.filter_chip_container, h_spacing=6, v_spacing=6)
        self.item_level_tag = QFrame()
        self.item_level_tag.setObjectName("itemLevelTag")
        self.item_level_tag.setFixedWidth(92)
        item_level_layout = QHBoxLayout(self.item_level_tag)
        item_level_layout.setContentsMargins(8, 2, 6, 2)
        item_level_layout.setSpacing(1)
        self.item_level_toggle = QPushButton("☑ ilvl：")
        self.item_level_toggle.setObjectName("itemLevelToggle")
        self.item_level_toggle.setToolTip("クリックしてアイテムレベル条件を有効／無効にします")
        self.item_level_toggle.clicked.connect(self._toggle_item_level_filter)
        item_level_layout.addWidget(self.item_level_toggle)
        self.item_level_edit = QLineEdit()
        self.item_level_edit.setObjectName("itemLevelEdit")
        self.item_level_edit.setValidator(QIntValidator(1, 100, self.item_level_edit))
        self.item_level_edit.setAlignment(Qt.AlignCenter)
        self.item_level_edit.setFixedWidth(34)
        self.item_level_edit.setToolTip("検索対象の最小アイテムレベル（1～100）")
        self.item_level_edit.textEdited.connect(self._enable_item_level_filter)
        item_level_layout.addWidget(self.item_level_edit)
        self.item_level_range_separator = QLabel("～")
        self.item_level_range_separator.hide()
        item_level_layout.addWidget(self.item_level_range_separator)
        self.item_level_max_edit = QLineEdit()
        self.item_level_max_edit.setObjectName("itemLevelMaxEdit")
        self.item_level_max_edit.setValidator(QIntValidator(1, 100, self.item_level_max_edit))
        self.item_level_max_edit.setAlignment(Qt.AlignCenter)
        self.item_level_max_edit.setFixedWidth(34)
        self.item_level_max_edit.setToolTip("検索対象の最大アイテムレベル（1～100）")
        self.item_level_max_edit.textEdited.connect(self._enable_item_level_filter)
        self.item_level_max_edit.hide()
        item_level_layout.addWidget(self.item_level_max_edit)
        self.item_level_tag.hide()
        self.gem_level_tag = QFrame()
        self.gem_level_tag.setObjectName("gemLevelTag")
        self.gem_level_tag.setFixedWidth(132)
        gem_level_layout = QHBoxLayout(self.gem_level_tag)
        gem_level_layout.setContentsMargins(8, 2, 6, 2)
        gem_level_layout.setSpacing(1)
        self.gem_level_toggle = QPushButton("☑ ジェムLv：")
        self.gem_level_toggle.setObjectName("gemLevelToggle")
        self.gem_level_toggle.clicked.connect(self._toggle_gem_level_filter)
        gem_level_layout.addWidget(self.gem_level_toggle)
        self.gem_level_edit = QLineEdit()
        self.gem_level_edit.setObjectName("gemLevelEdit")
        self.gem_level_edit.setValidator(QIntValidator(1, 40, self.gem_level_edit))
        self.gem_level_edit.setAlignment(Qt.AlignCenter)
        self.gem_level_edit.setFixedWidth(30)
        self.gem_level_edit.textEdited.connect(self._enable_gem_level_filter)
        gem_level_layout.addWidget(self.gem_level_edit)
        self.gem_level_tag.hide()
        self.gem_quality_tag = QFrame()
        self.gem_quality_tag.setObjectName("gemQualityTag")
        self.gem_quality_tag.setFixedWidth(116)
        gem_quality_layout = QHBoxLayout(self.gem_quality_tag)
        gem_quality_layout.setContentsMargins(8, 2, 6, 2)
        gem_quality_layout.setSpacing(1)
        self.gem_quality_toggle = QPushButton("☑ 品質：")
        self.gem_quality_toggle.setObjectName("gemQualityToggle")
        self.gem_quality_toggle.clicked.connect(self._toggle_gem_quality_filter)
        gem_quality_layout.addWidget(self.gem_quality_toggle)
        self.gem_quality_edit = QLineEdit()
        self.gem_quality_edit.setObjectName("gemQualityEdit")
        self.gem_quality_edit.setValidator(QIntValidator(0, 100, self.gem_quality_edit))
        self.gem_quality_edit.setAlignment(Qt.AlignCenter)
        self.gem_quality_edit.setFixedWidth(30)
        self.gem_quality_edit.textEdited.connect(self._enable_gem_quality_filter)
        gem_quality_layout.addWidget(self.gem_quality_edit)
        self.gem_quality_tag.hide()
        self.links_tag = QFrame()
        self.links_tag.setObjectName("linksTag")
        self.links_tag.setFixedWidth(116)
        links_layout = QHBoxLayout(self.links_tag)
        links_layout.setContentsMargins(8, 2, 6, 2)
        links_layout.setSpacing(1)
        self.links_toggle = QPushButton("☑ リンク：")
        self.links_toggle.setObjectName("linksToggle")
        self.links_toggle.clicked.connect(self._toggle_links_filter)
        links_layout.addWidget(self.links_toggle)
        self.links_edit = QLineEdit()
        self.links_edit.setObjectName("linksEdit")
        self.links_edit.setValidator(QIntValidator(1, 6, self.links_edit))
        self.links_edit.setAlignment(Qt.AlignCenter)
        self.links_edit.setFixedWidth(24)
        self.links_edit.textEdited.connect(self._enable_links_filter)
        links_layout.addWidget(self.links_edit)
        self.links_tag.hide()
        self.influence_chips = {}
        self._influence_chip_enabled = {}
        for influence, (label, _stat_id, _item_flag) in _INFLUENCE_CHIPS.items():
            button = QPushButton(label)
            button.setObjectName("influenceChip")
            button.setIcon(_influence_chip_icon(label, False))
            button.setIconSize(QSize(38, 20))
            button.clicked.connect(
                lambda checked=False, value=influence: self._toggle_influence_filter(value)
            )
            button.hide()
            self.influence_chips[influence] = button
        self.unidentified_chip = _CycleButton(
            (("未鑑定", True, False), ("未鑑定を含む", False, False)),
        )
        self.unidentified_chip.hide()
        self.veiled_chip = _CycleButton(
            (("Veiled", True, False), ("Veiledを含む", False, False)),
        )
        self.veiled_chip.hide()
        self.foil_chip = _CycleButton(
            (("Foil Unique", True, False), ("通常Unique", False, False)),
        )
        self.foil_chip.hide()
        self.map_tier_chip = _NumericFilterChip("Tier", 1, 17)
        self.map_tier_chip.setFixedWidth(116)
        self.nightmare_map_chip = QPushButton("ナイトメア")
        self.nightmare_map_chip.setObjectName("readonlyFilterChip")
        self.nightmare_map_chip.setEnabled(False)
        self.nightmare_map_chip.hide()
        self.base_percentile_chip = _NumericFilterChip(
            "ベース防御値", 0, 100, suffix="%",
        )
        self.base_percentile_chip.setFixedWidth(174)
        self.area_level_chip = _NumericFilterChip("Area Lv", 1, 100)
        self.heist_wings_chip = _NumericFilterChip("公開Wing", 1, 4)
        self.heist_job_chip = _NumericFilterChip("Job Lv", 1, 5)
        self.cluster_passives_chip = _NumericFilterChip("パッシブ数", 1, 35)
        for chip in (
            self.map_tier_chip, self.base_percentile_chip,
            self.area_level_chip, self.heist_wings_chip, self.heist_job_chip,
            self.cluster_passives_chip,
        ):
            chip.hide()
        self.blighted_chip = QPushButton()
        self.blighted_chip.setObjectName("readonlyFilterChip")
        self.blighted_chip.hide()
        self.completion_reward_chip = QPushButton()
        self.completion_reward_chip.setObjectName("readonlyFilterChip")
        self.completion_reward_chip.hide()
        self.gem_variant_chip = QPushButton()
        self.gem_variant_chip.setObjectName("readonlyFilterChip")
        self.gem_variant_chip.setEnabled(False)
        self.gem_variant_chip.hide()
        self.heist_target_chip = QPushButton()
        self.heist_target_chip.setObjectName("readonlyFilterChip")
        self.heist_target_chip.setEnabled(False)
        self.heist_target_chip.hide()
        self.cluster_enchant_chip = QPushButton()
        self.cluster_enchant_chip.setObjectName("readonlyFilterChip")
        self.cluster_enchant_chip.setEnabled(False)
        self.cluster_enchant_chip.hide()
        self.cluster_socket_chip = QPushButton()
        self.cluster_socket_chip.setObjectName("readonlyFilterChip")
        self.cluster_socket_chip.setEnabled(False)
        self.cluster_socket_chip.hide()
        self.logbook_area_selector = _AreaSegmentedControl()
        self.logbook_area_selector.currentIndexChanged.connect(self._logbook_area_changed)
        self.logbook_area_container = QWidget()
        self.logbook_area_container.setObjectName("logbookAreaContainer")
        logbook_area_layout = QHBoxLayout(self.logbook_area_container)
        logbook_area_layout.setContentsMargins(0, 0, 0, 0)
        logbook_area_layout.setSpacing(0)
        logbook_area_layout.addWidget(self.logbook_area_selector, 0, Qt.AlignLeft)
        logbook_area_layout.addStretch()
        self.logbook_area_container.hide()
        self.split_combo = _CycleButton(
            (("スプリット品含む", True, False), ("非スプリット", False, False)),
        )
        self.split_combo.hide()
        self.mirrored_combo = _CycleButton(
            (("ミラー化", True, False), ("非ミラー化", False, False)),
        )
        self.mirrored_combo.hide()
        self._filter_chips = (
            ("links", self.links_tag),
            ("nightmare_map", self.nightmare_map_chip),
            ("map_tier", self.map_tier_chip),
            ("completion_reward", self.completion_reward_chip),
            ("area_level", self.area_level_chip),
            ("heist_wings", self.heist_wings_chip),
            ("heist_job", self.heist_job_chip),
            ("heist_target", self.heist_target_chip),
            ("cluster_enchant", self.cluster_enchant_chip),
            ("cluster_passives", self.cluster_passives_chip),
            ("cluster_sockets", self.cluster_socket_chip),
            ("blighted", self.blighted_chip),
            ("item_level", self.item_level_tag),
            ("base_percentile", self.base_percentile_chip),
            ("gem_variant", self.gem_variant_chip),
            ("gem_level", self.gem_level_tag),
            ("quality", self.gem_quality_tag),
            *((f"influence_{name}", self.influence_chips[name]) for name in _INFLUENCE_CHIPS),
            ("magic_rarity", self.magic_rarity_toggle),
            ("unidentified", self.unidentified_chip),
            ("veiled", self.veiled_chip),
            ("foil", self.foil_chip),
            ("mirrored", self.mirrored_combo),
            ("split", self.split_combo),
        )
        for _name, chip in self._filter_chips:
            self.filter_chip_layout.addWidget(chip)
        panel_layout.addWidget(self.filter_chip_container)
        panel_layout.addLayout(top_options)
        panel_layout.addWidget(self.logbook_area_container)

        self.weapon_property_label = QLabel("武器性能・検索Mod")
        self.weapon_property_label.setObjectName("sectionTitle")
        self.weapon_dps_label = QLabel()
        self.weapon_dps_label.setObjectName("weaponDpsSummary")
        self.weapon_dps_label.hide()
        weapon_property_header = QHBoxLayout()
        weapon_property_header.setContentsMargins(0, 0, 0, 0)
        weapon_property_header.setSpacing(8)
        weapon_property_header.addWidget(self.weapon_property_label)
        weapon_property_header.addWidget(self.weapon_dps_label)
        weapon_property_header.addStretch(1)
        panel_layout.addLayout(weapon_property_header)
        self.clear_mod_conditions_button = QPushButton("一覧のチェックを全て選択")
        self.clear_mod_conditions_button.setObjectName("secondaryActionButton")
        self.clear_mod_conditions_button.setToolTip(
            "上の条件一覧のみ。ilvlなどの基本条件は変更しません"
        )
        self.clear_mod_conditions_button.clicked.connect(
            self._toggle_all_mod_condition_checks
        )

        self._debug_parse_area = QWidget()
        self._debug_parse_area.hide()
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("ここにアイテムの詳細コピー文を貼り付けます")
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["項目", "解析結果"])
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.setRootIsDecorated(True)
        self.result_tree.setUniformRowHeights(True)
        self.result_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.result_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        debug_layout = QVBoxLayout(self._debug_parse_area)
        debug_layout.addWidget(self.input_edit)
        debug_layout.addWidget(self.result_tree)
        panel_layout.addWidget(self._debug_parse_area)
        self.mod_filter_tree = QTreeWidget()
        self.mod_filter_tree.setHeaderLabels([
            "", "種別", "ティア", "検索条件", "最小", "最大",
        ])
        self.mod_filter_tree.setRootIsDecorated(False)
        self.mod_filter_tree.setAlternatingRowColors(True)
        # 行選択は使わない。Mod文章クリックはチェック切替だけを行い、
        # セルウィジェット（最小・最大欄）と選択背景の見た目が分離しないようにする。
        self.mod_filter_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.mod_filter_tree.setMinimumHeight(profile["mod_height"])
        mod_header = self.mod_filter_tree.header()
        mod_header.hide()
        # Qtは既定で最終列を余白まで伸ばす。最大欄ではなくMod文章欄へ
        # 余った幅を渡すため、最終列の自動伸長を無効化する。
        mod_header.setStretchLastSection(False)
        mod_header.setSectionResizeMode(_MOD_COLUMN_CHECK, QHeaderView.Fixed)
        self.mod_filter_tree.setColumnWidth(
            _MOD_COLUMN_CHECK, _MOD_CHECK_COLUMN_WIDTH
        )
        mod_header.setSectionResizeMode(_MOD_COLUMN_KIND, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(_MOD_COLUMN_TIER, QHeaderView.Fixed)
        self.mod_filter_tree.setColumnWidth(_MOD_COLUMN_TIER, _MOD_TIER_COLUMN_WIDTH)
        # 操作列を常に表示領域内へ収め、余った幅だけをMod文章へ割り当てる。
        # 固定幅の文章列は狭い画面で横スクロールを発生させ、最大欄へ
        # フォーカスした際に一覧全体が右へ移動する原因になる。
        mod_header.setSectionResizeMode(_MOD_COLUMN_TEXT, QHeaderView.Stretch)
        mod_header.setSectionResizeMode(_MOD_COLUMN_MIN, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(_MOD_COLUMN_MAX, QHeaderView.ResizeToContents)
        self.mod_filter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mod_filter_tree.itemClicked.connect(
            self._toggle_mod_condition_from_text
        )
        panel_layout.addWidget(self.mod_filter_tree, stretch=3)
        self.mod_conditions_toggle = QPushButton("mod条件をたたむ∧")
        self.mod_conditions_toggle.setObjectName("secondaryActionButton")
        self.mod_conditions_toggle.setToolTip("Mod検索条件の一覧を折りたたむ")
        self.mod_conditions_toggle.clicked.connect(self._toggle_mod_conditions)
        self.hidden_mods_toggle = QPushButton("隠し候補を表示")
        self.hidden_mods_toggle.setObjectName("secondaryActionButton")
        self.hidden_mods_toggle.setCheckable(True)
        self.hidden_mods_toggle.setToolTip(
            "数値が固定され、同じアイテム同士の価格比較に影響しないため、\n"
            "通常は隠している検索候補を表示します。"
        )
        self.hidden_mods_toggle.toggled.connect(self._toggle_hidden_mods)
        self.mod_sources_toggle = QPushButton("Mod構成を表示")
        self.mod_sources_toggle.setObjectName("secondaryActionButton")
        self.mod_sources_toggle.setCheckable(True)
        self.mod_sources_toggle.setToolTip(
            "合計ライフや防御力など、複数の数値をまとめた検索条件について、\n"
            "計算に使われた元のMod文章を表示します。"
        )
        self.mod_sources_toggle.toggled.connect(self._toggle_mod_sources)
        self.mercenary_supports_toggle = QPushButton("傭兵のサポートジェムを表示")
        self.mercenary_supports_toggle.setObjectName("mercenarySupportsToggle")
        self.mercenary_supports_toggle.setCheckable(True)
        self.mercenary_supports_toggle.setToolTip(
            "傭兵の召喚状に含まれるサポートジェムの検索条件を表示します"
        )
        self.mercenary_supports_toggle.toggled.connect(
            self._toggle_mercenary_supports
        )
        self.mercenary_supports_toggle.hide()
        mod_conditions_actions = QHBoxLayout()
        mod_conditions_actions.addWidget(self.mod_conditions_toggle)
        mod_conditions_actions.addWidget(self.clear_mod_conditions_button)
        mod_conditions_actions.addWidget(self.hidden_mods_toggle)
        mod_conditions_actions.addWidget(self.mod_sources_toggle)
        mod_conditions_actions.addWidget(self.mercenary_supports_toggle)
        mod_conditions_actions.addStretch()
        panel_layout.addLayout(mod_conditions_actions)
        self.mod_warning = QLabel("")
        self.mod_warning.setWordWrap(True)
        self.mod_warning.setStyleSheet("color: #d6a84b;")
        self.mod_warning.hide()
        panel_layout.addWidget(self.mod_warning)
        self.search_scope_notice = QLabel("")
        self.search_scope_notice.setWordWrap(True)
        self.search_scope_notice.setStyleSheet("color: #d6a84b;")
        self.search_scope_notice.hide()
        panel_layout.addWidget(self.search_scope_notice)

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        self.price_button = QPushButton("検索")
        self.price_button.setObjectName("primaryButton")
        self.price_button.clicked.connect(self.search_current_item)
        action_row.addWidget(self.price_button)
        action_row.addWidget(self.trade_status_combo)
        action_row.addWidget(self.trade_currency_combo)
        action_row.addWidget(self.listed_within_combo)
        self.trade_url_button = QPushButton("公式トレード  ↗")
        self.trade_url_button.setObjectName("filterActionButton")
        self.trade_url_button.setProperty("compactAction", True)
        self.trade_url_button.setToolTip("日本語公式Tradeをブラウザで開く")
        self.trade_url_button.setEnabled(False)
        self.trade_url_button.clicked.connect(self._open_trade_url)
        action_row.addWidget(self.trade_url_button)
        panel_layout.addLayout(action_row)

        self.price_status = QLabel("検索条件を読み取っています…")
        self.price_status.setWordWrap(True)
        self.price_status.setObjectName("priceStatus")
        panel_layout.addWidget(self.price_status)
        self.price_list = QTreeWidget()
        self.price_list.setObjectName("priceList")
        self.price_list.setHeaderLabels(["価格", "出品日時"])
        self.price_list.setRootIsDecorated(False)
        self.price_list.setAlternatingRowColors(True)
        self.price_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.price_list.setMinimumHeight(profile["price_height"])
        price_header = self.price_list.header()
        price_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        price_header.setSectionResizeMode(1, QHeaderView.Stretch)
        panel_layout.addWidget(self.price_list, stretch=2)
        resize_row = QHBoxLayout()
        resize_row.addStretch()
        resize_row.addWidget(QSizeGrip(self))
        panel_layout.addLayout(resize_row)
        self.apply_result_display_size()
        self._trade_signals = _TradeSignals(self)
        self._trade_signals.completed.connect(self._search_completed)
        self._trade_signals.partial_completed.connect(self._search_partially_completed)
        self._trade_signals.failed.connect(self._show_price_error)
        self._trade_signals.unique_candidates_ready.connect(self._show_unique_candidates)
        self._trade_signals.unique_variants_ready.connect(self._show_unique_variants)
        self._trade_signals.leagues_ready.connect(self._show_trade_leagues)
        self._trade_signals.poe_ninja_ready.connect(self._show_poe_ninja_price)
        self._trade_signals.poe_ninja_failed.connect(self._hide_poe_ninja_price)
        self._trade_signals.related_items_ready.connect(self._show_related_items)
        self._trade_signals.related_items_failed.connect(self._hide_related_items)
        self._trade_signals.divine_rate_ready.connect(self._show_divine_rate)
        self._trade_signals.divine_rate_failed.connect(self._hide_divine_rate)
        self._trade_signals.global_mouse_pressed.connect(self._handle_global_mouse_press)
        self._trade_signals.global_mouse_moved.connect(self._handle_global_mouse_move)
        self._trade_base_type = None
        self._trade_item_name = None
        self._preset_item_key = None
        self._currency_item_key = None
        self._state_item_key = None
        self._base_scope_item_key = None
        self._unique_selector_item_key = None
        self._last_trade_url = ""
        self._last_poe_ninja_url = ""
        self._poe_ninja_item_key = None
        self._poe_ninja_performance_traces = {}
        self._pending_performance_trace = None
        self._current_performance_trace = None
        self._search_performance_traces = {}
        self._divine_rate_key = None
        self._divine_rate_retry_after = 0.0
        self._connect_search_trigger_signals()
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def _connect_search_trigger_signals(self):
        """Awakened準拠の検索待ち・即時再検索トリガーを接続する。"""
        for control in (
            self.trade_preset_combo, self.base_scope_toggle, self.magic_rarity_toggle,
            self.corrupted_combo, self.unidentified_chip, self.veiled_chip,
            self.foil_chip, self.split_combo, self.mirrored_combo,
            self.logbook_area_selector,
        ):
            control.currentIndexChanged.connect(self._mark_search_dirty)
        for button in (
            self.item_level_toggle, self.gem_level_toggle, self.gem_quality_toggle,
            self.links_toggle, *self.influence_chips.values(),
        ):
            button.clicked.connect(self._mark_search_dirty)
        for editor in (
            self.item_level_edit, self.item_level_max_edit, self.gem_level_edit,
            self.gem_quality_edit, self.links_edit,
        ):
            editor.textEdited.connect(self._mark_search_dirty)
        for chip in (
            self.map_tier_chip, self.base_percentile_chip, self.area_level_chip,
            self.heist_wings_chip, self.heist_job_chip, self.cluster_passives_chip,
        ):
            chip.toggle.clicked.connect(self._mark_search_dirty)
            chip.minimum_edit.textEdited.connect(self._mark_search_dirty)
            chip.maximum_edit.textEdited.connect(self._mark_search_dirty)
        self.unique_name_group.buttonClicked.connect(self._mark_search_dirty)
        self.unique_variant_combo.currentIndexChanged.connect(self._mark_search_dirty)
        for combo in (
            self.trade_status_combo, self.trade_currency_combo, self.listed_within_combo,
        ):
            combo.currentIndexChanged.connect(self._auto_search_after_trade_option_change)
            combo.currentIndexChanged.connect(self._fit_compact_action_widths)
        self.trade_league_combo.currentIndexChanged.connect(
            self._auto_search_after_trade_option_change
        )
        self.trade_league_combo.lineEdit().editingFinished.connect(
            self._auto_search_after_trade_option_change
        )

    def _mark_search_dirty(self, *_args):
        if not self._has_searched_current_item or getattr(self, "_parsed_item", None) is None:
            return
        self._search_generation += 1
        self._search_dirty = True
        self.price_list.clear()
        self._last_trade_url = ""
        self.trade_url_button.setEnabled(False)
        self.price_status.clear()
        self.price_button.setEnabled(True)

    def _auto_search_after_trade_option_change(self, *_args):
        if not self._has_searched_current_item or getattr(self, "_parsed_item", None) is None:
            return
        self._search_generation += 1
        self._search_dirty = False
        self.price_list.clear()
        self._last_trade_url = ""
        self.trade_url_button.setEnabled(False)
        if self._auto_search_queued:
            return
        self._auto_search_queued = True
        QTimer.singleShot(0, self._run_queued_auto_search)

    def _run_queued_auto_search(self):
        self._auto_search_queued = False
        self.search_current_item()

    def _apply_poetore_style(self):
        """情報はニュートラル面に載せ、選択・操作だけ青緑で示す。"""
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        style = """
            QWidget {
                color: #E6ECEA;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
            }
            QFrame#poetorePanel {
                background: rgba(17, 20, 22, 246);
                border: 1px solid #343B3E;
                border-radius: 5px;
            }
            QFrame#itemHeader {
                background: rgba(20, 24, 26, 220);
                border: none;
                border-radius: 4px;
            }
            QFrame#poeNinjaPricePanel {
                background: rgba(26, 31, 33, 220);
                border: none;
                border-radius: 4px;
            }
            QLabel#poeNinjaPriceLabel { color: #98A39F; font-weight: 700; }
            QLabel#poeNinjaPriceValue { color: #E6ECEA; font-size: 14px; font-weight: 700; }
            QLabel#poeNinjaPriceMultiplier { color: #E6ECEA; font-size: 13px; }
            QLabel#poeNinjaTrendLabel { color: #98A39F; font-size: 10px; }
            QPushButton#poeNinjaOpenButton { padding: 3px 7px; }
            QPushButton#divineRateButton {
                color: #E6ECEA;
                padding: 2px 7px;
                font-weight: 700;
                border: none;
            }
            QMenu#divineRateMenu {
                background: #1A1F21;
                color: #E6ECEA;
                border: 1px solid #3A4245;
                padding: 4px;
            }
            QMenu#divineRateMenu::item { padding: 4px 18px 4px 10px; }
            QMenu#divineRateMenu::item:selected { background: rgba(73, 214, 176, 45); }
            QPushButton#leaguePopupButton {
                color: #D8E3DF;
                padding: 0;
                font-size: 11px;
                border: none;
            }
            QLabel#itemName {
                color: #D8E3DF;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#itemBase { color: #98A39F; font-size: 11px; }
            QLabel#sectionTitle {
                color: #49D6B0;
                font-weight: 700;
                border-bottom: 1px solid rgba(73, 214, 176, 70);
                padding: 4px 2px;
            }
            QLabel#weaponDpsSummary {
                color: #E6ECEA;
                padding: 4px 2px;
            }
            QLabel#priceStatus { color: #98A39F; padding: 1px 2px; }
            QPushButton {
                background: rgba(26, 31, 33, 225);
                color: #E6ECEA;
                border: none;
                border-radius: 3px;
                padding: 5px 9px;
            }
            QPushButton:hover { background: rgba(37, 51, 47, 230); }
            QPushButton:pressed { background: #111; }
            QPushButton:disabled { color: #66706C; background: rgba(23, 27, 29, 180); }
            QPushButton#secondaryActionButton,
            QPushButton#filterActionButton {
                border: 1px solid #465154;
            }
            QPushButton#secondaryActionButton:hover,
            QPushButton#filterActionButton:hover {
                border-color: #49D6B0;
            }
            QPushButton#secondaryActionButton:checked {
                background: rgba(35, 118, 100, 135);
                border-color: #49D6B0;
            }
            QPushButton#filterActionButton:disabled {
                border-color: #343B3E;
            }
            QPushButton#binaryToggle {
                border: 1px solid #465154;
                border-radius: 0;
                padding: 4px 7px;
            }
            QPushButton#binaryToggle:hover {
                border-color: #49D6B0;
            }
            QPushButton#binaryToggle:first-child { border-radius: 3px 0 0 3px; }
            QPushButton#binaryToggle:last-child { border-radius: 0 3px 3px 0; }
            QPushButton#binaryToggle:checked {
                background: rgba(35, 118, 100, 225);
                border-color: #49D6B0;
                color: #E6ECEA;
                font-weight: 700;
            }
            QPushButton#cycleToggle {
                background: rgba(28, 83, 73, 210);
                color: #E6ECEA;
                border: none;
                min-width: 112px;
                font-weight: 700;
            }
            QPushButton#cycleToggle[alert="true"] { color: #ff5757; }
            QPushButton#influenceChip {
                background: rgba(20, 20, 20, 180);
                color: #737D79;
                border: none;
                padding: 3px 7px;
                font-weight: 700;
            }
            QPushButton#influenceChip[active="true"] {
                background: rgba(28, 83, 73, 210);
                color: #E6ECEA;
                border: 1px solid #49D6B0;
            }
            QFrame#numericFilterTag {
                background: rgba(28, 83, 73, 210);
                border: 1px solid #49D6B0;
                border-radius: 3px;
            }
            QFrame#numericFilterTag[active="false"] {
                background: rgba(20, 20, 20, 180);
                border: none;
            }
            QPushButton#numericFilterToggle, QLineEdit#numericFilterEdit {
                background: transparent;
                color: #E6ECEA;
                border: none;
                padding: 0;
                font-weight: 700;
            }
            QFrame#numericFilterTag[active="false"] QPushButton,
            QFrame#numericFilterTag[active="false"] QLineEdit,
            QFrame#numericFilterTag[active="false"] QLabel { color: #737D79; }
            QPushButton#readonlyFilterChip {
                background: rgba(28, 83, 73, 210);
                color: #E6ECEA;
                border: 1px solid #49D6B0;
                padding: 3px 7px;
                font-weight: 700;
            }
            QFrame#itemLevelTag {
                background: rgba(28, 83, 73, 210);
                border: 1px solid #49D6B0;
                border-radius: 3px;
            }
            QFrame#gemLevelTag {
                background: rgba(28, 83, 73, 210);
                border: 1px solid #49D6B0;
                border-radius: 3px;
            }
            QFrame#gemQualityTag {
                background: rgba(28, 83, 73, 210);
                border: 1px solid #49D6B0;
                border-radius: 3px;
            }
            QFrame#linksTag {
                background: rgba(28, 83, 73, 210);
                border: 1px solid #49D6B0;
                border-radius: 3px;
            }
            QFrame#itemLevelTag QLabel {
                color: #E6ECEA;
                font-weight: 700;
            }
            QPushButton#itemLevelToggle, QPushButton#gemLevelToggle, QPushButton#gemQualityToggle, QPushButton#linksToggle {
                background: transparent;
                color: #E6ECEA;
                border: none;
                padding: 0;
                font-weight: 700;
            }
            QLineEdit#itemLevelEdit, QLineEdit#itemLevelMaxEdit, QLineEdit#gemLevelEdit, QLineEdit#gemQualityEdit, QLineEdit#linksEdit {
                background: transparent;
                color: #E6ECEA;
                border: none;
                padding: 0;
                min-height: 20px;
                font-weight: 700;
            }
            QLineEdit#itemLevelEdit:focus, QLineEdit#itemLevelMaxEdit:focus, QLineEdit#gemLevelEdit:focus, QLineEdit#gemQualityEdit:focus, QLineEdit#linksEdit:focus {
                border: none;
                color: #D8E3DF;
            }
            QFrame#itemLevelTag[active="false"] {
                border: none;
                background: rgba(20, 20, 20, 180);
            }
            QFrame#gemLevelTag[active="false"] {
                border: none;
                background: rgba(20, 20, 20, 180);
            }
            QFrame#gemQualityTag[active="false"] {
                border: none;
                background: rgba(20, 20, 20, 180);
            }
            QFrame#linksTag[active="false"] {
                border: none;
                background: rgba(20, 20, 20, 180);
            }
            QFrame#itemLevelTag[active="false"] QPushButton,
            QFrame#itemLevelTag[active="false"] QLineEdit,
            QFrame#itemLevelTag[active="false"] QLabel {
                color: #737D79;
            }
            QFrame#gemLevelTag[active="false"] QPushButton,
            QFrame#gemLevelTag[active="false"] QLineEdit {
                color: #737D79;
            }
            QFrame#gemQualityTag[active="false"] QPushButton,
            QFrame#gemQualityTag[active="false"] QLineEdit {
                color: #737D79;
            }
            QFrame#linksTag[active="false"] QPushButton,
            QFrame#linksTag[active="false"] QLineEdit {
                color: #737D79;
            }
            QPushButton#primaryButton {
                background: rgba(35, 118, 100, 225);
                color: #E6ECEA;
                font-weight: 700;
                min-width: 0;
            }
            QComboBox, QLineEdit {
                background: rgba(26, 31, 33, 235);
                color: #D8E3DF;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 4px 6px;
                min-height: 20px;
                selection-background-color: rgba(35, 118, 100, 220);
            }
            QComboBox:hover, QLineEdit:focus { border-color: #49D6B0; }
            QComboBox#filterControl {
                border: 1px solid #465154;
            }
            QComboBox#filterControl:hover,
            QComboBox#filterControl:on {
                border-color: #49D6B0;
            }
            QComboBox#filterControl[compactAction="true"] {
                font-size: __COMPACT_ACTION_FONT__px;
                padding: 2px 1px;
                min-height: 18px;
            }
            QComboBox#filterControl[compactAction="true"]::drop-down {
                width: 8px;
            }
            QPushButton#filterActionButton[compactAction="true"] {
                font-size: __COMPACT_ACTION_FONT__px;
                padding: 3px 5px;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #1b1b1b;
                color: #D8E3DF;
                border: 1px solid #3D8F7B;
                selection-background-color: #286C5D;
            }
            QTreeWidget {
                background: rgba(17, 20, 22, 235);
                alternate-background-color: rgba(25, 30, 32, 205);
                color: #D5DDDA;
                border: none;
                border-radius: 3px;
                gridline-color: #2A3033;
                outline: none;
            }
            QTreeWidget::item { padding: 4px 2px; border-bottom: 1px solid #272D30; }
            QTreeWidget::item:selected { background: rgba(35, 118, 100, 125); color: white; }
            QTreeWidget#priceList::item { padding: 4px 7px; }
            QScrollArea#uniqueCandidateScroll,
            QScrollArea#uniqueCandidateScroll > QWidget > QWidget,
            QWidget#uniqueCandidateContainer {
                background: #111416;
            }
            QHeaderView::section {
                background: rgba(28, 34, 36, 245);
                color: #D5DDDA;
                border: none;
                border-right: none;
                border-bottom: 1px solid #343B3E;
                padding: 5px 4px;
                font-weight: 600;
            }
            QTreeWidget#priceList QHeaderView::section { padding: 5px 7px; }
            QScrollBar:vertical { background: #15191B; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: rgba(73, 214, 176, 125); min-height: 26px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QSizeGrip { background: transparent; }
        """
        font = profile["font"]
        font_sizes = {
            10: max(10, font - 2),
            11: max(11, font - 1),
            12: font,
            13: font + 1,
            14: font + 2,
            15: font + 3,
        }
        style = re.sub(
            r"font-size: (10|11|12|13|14|15)px;",
            lambda match: f"font-size: {font_sizes[int(match.group(1))]}px;",
            style,
        )
        style = style.replace(
            "padding: 5px 9px;",
            f"padding: {profile['button_v_padding']}px "
            f"{profile['button_h_padding']}px;",
        )
        style = style.replace(
            "__COMPACT_ACTION_FONT__", str(profile["mod_value_font"])
        )
        self.setStyleSheet(style)

    def _display_scale(self) -> float:
        return _DISPLAY_SIZE_PROFILES[self._result_font_size]["font"] / 12

    def _scaled_display_value(self, value: int) -> int:
        return round(value * self._display_scale())

    def _apply_mod_value_editor_size(
        self, editor: QLineEdit, *, leading_gap: bool = False,
    ):
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        gap = self._scaled_display_value(_MOD_VALUE_LEADING_GAP) if leading_gap else 0
        editor.setFixedWidth(
            self._scaled_display_value(_MOD_VALUE_EDITOR_WIDTH) + gap
        )
        editor.setStyleSheet(
            f"font-size: {profile['mod_value_font']}px;"
            + (f" border-left: {gap}px solid #111416;" if gap else "")
        )

    def _fit_search_range_width(self):
        """Mod数値コンボを全選択肢が収まる内容幅へ詰める。"""
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        font = self.search_range_combo.font()
        font.setPixelSize(profile["font"])
        metrics = QFontMetrics(font)
        text_width = max(
            (metrics.horizontalAdvance(self.search_range_combo.itemText(index))
             for index in range(self.search_range_combo.count())),
            default=0,
        )
        self.search_range_combo.setFixedWidth(text_width + 28)

    def _fit_compact_action_widths(self, *_args):
        """検索操作列を、現在表示中の文言に合う最小幅へ揃える。"""
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        for combo in (
            self.trade_status_combo,
            self.trade_currency_combo,
            self.listed_within_combo,
        ):
            font = combo.font()
            font.setPixelSize(profile["mod_value_font"])
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(combo.currentText())
            # コンパクト操作列用の左右パディング、矢印、境界分を確保する。
            combo.setFixedWidth(text_width + 12)

        button_font = self.trade_url_button.font()
        button_font.setPixelSize(profile["mod_value_font"])
        button_metrics = QFontMetrics(button_font)
        self.trade_url_button.setFixedWidth(
            button_metrics.horizontalAdvance(self.trade_url_button.text()) + 12
        )

    def apply_result_display_size(self):
        """設定済みの小／中／大を既存の検索画面へ即時反映する。"""
        selected = normalize_result_font_size(
            self._app_config.get("poetore", {}).get("result_font_size", "medium")
        )
        profile = _DISPLAY_SIZE_PROFILES[selected]
        self._result_font_size = selected
        self.setMinimumSize(profile["minimum_width"], profile["minimum_height"])
        self.resize(profile["width"], profile["height"])
        self.mod_filter_tree.setMinimumHeight(profile["mod_height"])
        self._apply_related_items_layout(
            not self.related_items_panel.isHidden()
        )
        self.trade_league_combo.setFixedWidth(self._scaled_display_value(290))
        self.league_popup_button.setFixedSize(
            self._scaled_display_value(28), self._scaled_display_value(28)
        )
        self.poetore_close_button.setFixedSize(
            self._scaled_display_value(28), self._scaled_display_value(24)
        )
        self.poe_ninja_currency_icon.setFixedSize(
            self._scaled_display_value(28), self._scaled_display_value(28)
        )
        self._fit_search_range_width()
        self._fit_compact_action_widths()
        self.mod_filter_tree.setColumnWidth(
            _MOD_COLUMN_CHECK, self._scaled_display_value(_MOD_CHECK_COLUMN_WIDTH)
        )
        self.mod_filter_tree.setColumnWidth(
            _MOD_COLUMN_TIER, self._scaled_display_value(_MOD_TIER_COLUMN_WIDTH)
        )
        for column in (_MOD_COLUMN_MIN, _MOD_COLUMN_MAX):
            for index in range(self.mod_filter_tree.topLevelItemCount()):
                editor = self.mod_filter_tree.itemWidget(
                    self.mod_filter_tree.topLevelItem(index), column
                )
                if isinstance(editor, QLineEdit):
                    self._apply_mod_value_editor_size(
                        editor, leading_gap=column == _MOD_COLUMN_MIN,
                    )
        self._apply_poetore_style()
        # スタイルのmin-width適用後に固定し、レイアウトによる再拡張を防ぐ。
        self.price_button.setFixedWidth(profile["search_button_width"])
        self._adjust_window_height_to_mod_rows()
    def _toggle_mod_conditions(self):
        collapsed = self.mod_filter_tree.isVisible()
        self._set_mod_conditions_collapsed(collapsed)

    def _set_mod_conditions_collapsed(self, collapsed: bool):
        self.mod_filter_tree.setVisible(not collapsed)
        self.mod_conditions_toggle.setText(
            "mod条件をひらく∨" if collapsed else "mod条件をたたむ∧"
        )
        self.mod_conditions_toggle.setToolTip(
            "Mod検索条件の一覧を展開する" if collapsed
            else "Mod検索条件の一覧を折りたたむ"
        )
        self._adjust_window_height_to_mod_rows()

    def _reset_mod_conditions_for_item(self):
        has_visible_conditions = any(
            not self.mod_filter_tree.topLevelItem(index).isHidden()
            for index in range(self.mod_filter_tree.topLevelItemCount())
        )
        self._set_mod_conditions_collapsed(not has_visible_conditions)

    def _toggle_hidden_mods(self, visible: bool):
        self.hidden_mods_toggle.setText(
            "通常候補を表示" if visible else "隠し候補を表示"
        )
        for index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(index)
            stat_filter = row.data(_MOD_COLUMN_CHECK, Qt.UserRole + 4)
            is_hidden_candidate = bool(
                getattr(stat_filter, "hidden_reason", "")
            )
            checkbox_container = self.mod_filter_tree.itemWidget(
                row, _MOD_COLUMN_CHECK
            )
            checkbox = (
                checkbox_container.findChild(QCheckBox, "modFilterCheckbox")
                if checkbox_container is not None else None
            )
            is_checked = checkbox is not None and checkbox.isChecked()
            hidden_by_candidate_filter = (
                is_hidden_candidate != visible
                and not (is_hidden_candidate and is_checked)
            )
            row.setHidden(
                hidden_by_candidate_filter or self._mercenary_support_row_is_hidden(row)
            )
        self._adjust_window_height_to_mod_rows()

    def _mercenary_support_row_is_hidden(self, row: QTreeWidgetItem) -> bool:
        stat_filter = row.data(_MOD_COLUMN_CHECK, Qt.UserRole + 4)
        return bool(
            isinstance(stat_filter, TradeStatFilter)
            and stat_filter.stat_id.startswith("mercenary.support")
            and not self.mercenary_supports_toggle.isChecked()
        )

    def _toggle_mercenary_supports(self, visible: bool):
        self.mercenary_supports_toggle.setText(
            "傭兵のサポートジェムを隠す"
            if visible else "傭兵のサポートジェムを表示"
        )
        self._toggle_hidden_mods(self.hidden_mods_toggle.isChecked())

    def _toggle_mod_sources(self, visible: bool):
        self.mod_sources_toggle.setText(
            "Mod構成を隠す" if visible else "Mod構成を表示"
        )
        for index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(index)
            row.setExpanded(visible and row.childCount() > 0)
        self._adjust_window_height_to_mod_rows()

    def _visible_mod_content_height(self) -> int:
        if not self.mod_filter_tree.isVisible():
            return 0
        height = self.mod_filter_tree.frameWidth() * 2 + 4
        default_row_height = self._scaled_display_value(_MOD_ROW_HEIGHT)
        for index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(index)
            if row.isHidden():
                continue
            height += max(row.sizeHint(_MOD_COLUMN_TEXT).height(), default_row_height)
            if row.isExpanded():
                for child_index in range(row.childCount()):
                    child = row.child(child_index)
                    height += max(child.sizeHint(0).height(), default_row_height)
        return height

    def _adjust_window_height_to_mod_rows(self):
        """通常候補が収まる分だけ縦へ拡張し、画面超過時だけスクロールを残す。"""
        if not hasattr(self, "mod_filter_tree"):
            return
        # 初期表示サイズは従来どおり維持し、アイテム解析後だけ内容に合わせる。
        if self.mod_filter_tree.topLevelItemCount() == 0:
            return
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else self.screen().availableGeometry()
        content_height = (
            self._visible_mod_content_height()
            if self.mod_filter_tree.isVisible() else profile["mod_height"]
        )
        related_visible = not self.related_items_panel.isHidden()
        price_height = profile["price_height"]
        if related_visible:
            price_height = max(
                120,
                price_height
                - self._scaled_display_value(_RELATED_ITEMS_PRICE_HEIGHT_REDUCTION),
            )
        mod_height, price_height, window_height = _auto_mod_layout_sizes(
            profile_height=profile["height"],
            profile_mod_height=profile["mod_height"],
            profile_price_height=price_height,
            minimum_price_height=self._scaled_display_value(120),
            content_height=content_height,
            available_height=available.height(),
            minimum_height=profile["minimum_height"],
        )
        self.mod_filter_tree.setMinimumHeight(mod_height)
        self.mod_filter_tree.setMaximumHeight(mod_height)
        self.price_list.setMinimumHeight(price_height)
        self.resize(max(self.width(), profile["width"]), window_height)
        if self.y() < available.top():
            self.move(self.x(), available.top())
        elif self.frameGeometry().bottom() > available.bottom():
            self.move(self.x(), available.bottom() - self.frameGeometry().height() + 1)

    def _mod_condition_checkboxes(self) -> tuple[QCheckBox, ...]:
        """Mod条件一覧にある検索可能なチェックボックスを返す。"""
        checkboxes = []
        for index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(index)
            checkbox_container = self.mod_filter_tree.itemWidget(
                row, _MOD_COLUMN_CHECK
            )
            checkbox = (
                checkbox_container.findChild(QCheckBox, "modFilterCheckbox")
                if checkbox_container is not None else None
            )
            if checkbox is not None:
                checkboxes.append(checkbox)
        return tuple(checkboxes)

    def _update_all_mod_conditions_button(self):
        """1件でも選択中なら解除、全解除時なら選択を次の操作にする。"""
        has_checked_condition = any(
            checkbox.isChecked()
            for checkbox in self._mod_condition_checkboxes()
        )
        self.clear_mod_conditions_button.setText(
            "一覧のチェックを全て解除"
            if has_checked_condition else "一覧のチェックを全て選択"
        )

    def _toggle_all_mod_condition_checks(self):
        """Mod条件だけを一括選択／解除し、基本条件チップは変更しない。"""
        checkboxes = self._mod_condition_checkboxes()
        should_check = not any(checkbox.isChecked() for checkbox in checkboxes)
        for checkbox in checkboxes:
            checkbox.setChecked(should_check)
        self._update_all_mod_conditions_button()

    def _update_item_header(self, item):
        is_nonunique_equipment = (
            item.category in {"weapon", "armour", "accessory"}
            and item.rarity.casefold() not in {"unique", "ユニーク"}
        )
        display_name = (
            self._display_base_type(item)
            if is_nonunique_equipment or item.category in {"captured_beast", "chart"}
            else self._display_item_name(item)
        )
        if item.name.strip() == "傭兵の召喚状":
            build = str(item.properties.get("ビルド") or "").strip()
            if build:
                display_name = f"{display_name} ({build})"
        self.item_name_label.setText(display_name)
        show_base_scope = is_nonunique_equipment or item.category == "chart"
        self.item_name_label.setVisible(not show_base_scope)
        self.base_scope_toggle.setVisible(show_base_scope)
        if show_base_scope:
            key = item.raw_text
            self.base_scope_toggle.setItemText(0, display_name)
            self.base_scope_toggle.setItemText(
                1,
                f"同じ海域（{item.properties.get('マップエリア', '海域不明')}）"
                if item.category == "chart"
                else f"すべての{self._item_class_label(item.item_class)}",
            )
            if key != self._base_scope_item_key:
                self._base_scope_item_key = key
                self.base_scope_toggle.setCurrentIndex(0)
        self.weapon_property_label.setText(
            "武器性能・検索Mod" if item.category == "weapon" else "検索条件一覧"
        )
        self._update_weapon_dps_summary(item)

    @staticmethod
    def _display_item_name(item) -> str:
        """検索identityは変えず、コピー元に対応する日本語表示名を返す。"""
        if item.category == "currency" and item.base_type in {"透視のオーブ", "Scrying Orb"}:
            area = str(
                item.properties.get("マップエリア")
                or item.properties.get("Map Area")
                or ""
            ).strip()
            if area:
                return f"透視のオーブ ({area})"

        identity = str(item.base_type or item.name or "").strip()
        if item.category == "gem" and identity.casefold().startswith("vaal "):
            from src.utils.gem_resolver import load_gem_names_ja

            normal_english = identity[5:].strip()
            normal_japanese = load_gem_names_ja().get(normal_english.casefold())
            if normal_japanese:
                return f"ヴァール{normal_japanese}"

        return item.name or item.base_type or "名称不明"

    def _update_weapon_dps_summary(self, item):
        if item.category != "weapon":
            self.weapon_dps_label.clear()
            self.weapon_dps_label.hide()
            return
        pdps = physical_dps_at_20_quality(item) or 0.0
        edps = elemental_dps(item) or 0.0
        if pdps and edps:
            self.weapon_dps_label.setText(
                f"合計DPS：{pdps + edps:.1f}（pDPS {pdps:.1f} / eDPS {edps:.1f}、"
                "pDPSは品質20%換算）"
            )
        elif pdps:
            self.weapon_dps_label.setText(f"pDPS：{pdps:.1f}（品質20%換算）")
        elif edps:
            self.weapon_dps_label.setText(f"eDPS：{edps:.1f}")
        else:
            self.weapon_dps_label.clear()
            self.weapon_dps_label.hide()
            return
        self.weapon_dps_label.show()

    def _display_base_type(self, item) -> str:
        """日本語Magicの1行名から表示用ベース名を取り出す。

        詳細コピー側で復元した英語ベースは検索用に保持し、
        表示は通常コピーの日本語名を優先する。
        """
        candidate = str(item.base_type or item.name or "").strip()
        if not candidate:
            return "ベース名"
        if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", candidate):
            return candidate.split()[-1]
        if item.name == item.base_type and self._trade_base_type:
            return self._trade_base_type
        return candidate

    @staticmethod
    def _item_class_label(item_class: str) -> str:
        labels = {
            "Body Armours": "鎧", "Boots": "ブーツ", "Gloves": "グローブ",
            "Helmets": "ヘルメット", "Shields": "盾", "Bows": "弓",
            "Claws": "鉤爪", "Daggers": "短剣", "Rune Daggers": "ルーンの短剣",
            "Fishing Rods": "釣り竿", "One Hand Axes": "片手斧",
            "One Hand Maces": "片手メイス", "Sceptres": "セプター",
            "One Hand Swords": "片手剣", "Staves": "スタッフ",
            "Warstaves": "ウォースタッフ", "Two Hand Axes": "両手斧",
            "Two Hand Maces": "両手メイス", "Two Hand Swords": "両手剣",
            "Wands": "ワンド", "Rings": "指輪", "Amulets": "アミュレット",
            "Belts": "ベルト", "指輪": "指輪", "アミュレット": "アミュレット",
            "ベルト": "ベルト",
        }
        return labels.get(item_class.strip(), item_class.strip() or "同一クラス")

    def _base_scope_changed(self, _index):
        if not hasattr(self, "price_list"):
            return
        self.price_list.clear()
        self.trade_url_button.setEnabled(False)
        self.price_status.setText(
            "ベースタイプを限定して検索します。"
            if self.base_scope_toggle.currentData()
            else "同じアイテムクラスの全ベースを対象に検索します。"
        )

    def _searches_exact_base_type(self, item) -> bool:
        if self.base_scope_toggle.isVisible():
            return bool(self.base_scope_toggle.currentData())
        nonunique_jewel_group = (
            item.category in {"jewel", "abyss_jewel"}
            and item.rarity.casefold() not in {"unique", "ユニーク"}
        )
        return not nonunique_jewel_group

    def eventFilter(self, watched, event):
        condition_checkbox = getattr(
            watched, "_mod_condition_checkbox", None
        )
        if (
            condition_checkbox is not None
            and event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            condition_checkbox.toggle()
            event.accept()
            return True
        if event.type() == QEvent.KeyPress and self.isVisible():
            is_escape = event.key() == Qt.Key_Escape
            is_alt_w = event.key() == Qt.Key_W and event.modifiers() == Qt.AltModifier
            if is_escape or is_alt_w:
                event.accept()
                self._close_and_return_to_poe()
                return True
            if (
                self._search_dirty
                and isinstance(watched, QLineEdit)
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
            ):
                event.accept()
                self.search_current_item()
                return True
        if (
            event.type() == QEvent.Enter
            and watched is self.price_button
            and self._search_dirty
        ):
            self.search_current_item()
            return True
        return super().eventFilter(watched, event)

    def _toggle_mod_condition_from_text(self, row, column):
        """Awakened同様、Mod文章のクリックでも条件をON/OFFする。"""
        if column != _MOD_COLUMN_TEXT:
            return
        # ユニークロール行の文章はセル内QLabelが直接処理する。
        if self.mod_filter_tree.itemWidget(row, _MOD_COLUMN_TEXT) is not None:
            return
        checkbox_container = self.mod_filter_tree.itemWidget(
            row, _MOD_COLUMN_CHECK
        )
        checkbox = (
            checkbox_container.findChild(QCheckBox, "modFilterCheckbox")
            if checkbox_container is not None else None
        )
        if checkbox is not None:
            checkbox.toggle()

    def _close_when_focus_leaves_panel(self, old, new):
        old_belongs = self._widget_belongs_to_panel(old)
        new_belongs = self._widget_belongs_to_panel(new)
        if new is None and self._widget_is_panel_popup(old):
            return
        if self.isVisible() and old_belongs and not new_belongs:
            if new is not None:
                self.close()
                return
            # Popupを閉じる瞬間は一時的にnew=Noneになる。次のイベントループで
            # 実際のフォーカス先がパネル外かを確定する。
            QTimer.singleShot(0, self._close_if_focus_is_still_outside)

    def _close_if_focus_is_still_outside(self):
        app = QApplication.instance()
        if not self.isVisible():
            return
        if self._widget_belongs_to_panel(app.focusWidget()):
            return
        if self._widget_belongs_to_panel(app.activePopupWidget()):
            return
        if app.activeWindow() is self:
            return
        self.close()

    def _widget_belongs_to_panel(self, widget) -> bool:
        """QComboBoxの別ウィンドウPopupも、親コンボ経由でパネル内とみなす。"""
        current = widget if isinstance(widget, QWidget) else None
        visited = set()
        while current is not None and id(current) not in visited:
            if current is self:
                return True
            visited.add(id(current))
            current = current.parentWidget()
        return False

    def _widget_is_panel_popup(self, widget) -> bool:
        return bool(
            isinstance(widget, QWidget) and
            widget.window().windowType() == Qt.Popup and
            self._widget_belongs_to_panel(widget)
        )

    def refresh_trade_leagues(self):
        if self._league_refresh_started:
            return
        self._league_refresh_started = True

        def run():
            try:
                leagues = available_pc_leagues()
            except TradeApiError:
                leagues = ()
            self._trade_signals.leagues_ready.emit(leagues)

        threading.Thread(target=run, daemon=True).start()

    def _show_trade_leagues(self, leagues):
        saved = str(self._app_config.get("poetore", {}).get("league", "auto"))
        self._auto_league = default_pc_league(tuple(leagues))
        listed_ids = {league.id for league in leagues}
        is_private = bool(re.search(r"\(PL\d+\)$", saved))
        if saved != "auto" and saved not in listed_ids and not is_private:
            saved = "auto"

        self.trade_league_combo.blockSignals(True)
        self.trade_league_combo.clear()
        self.trade_league_combo.addItem(f"自動（現行SC: {self._auto_league}）", "auto")
        for league in leagues:
            label = f"{league.id}（HC）" if league.hardcore else league.id
            self.trade_league_combo.addItem(label, league.id)
        if is_private and self.trade_league_combo.findData(saved) < 0:
            self.trade_league_combo.addItem(saved, saved)
        index = self.trade_league_combo.findData(saved)
        self.trade_league_combo.setCurrentIndex(max(0, index))
        self.trade_league_combo.blockSignals(False)
        if saved == "auto":
            self._persist_trade_league()

    def _selected_trade_league(self) -> str | None:
        selected = self._league_selection_value()
        if selected == "auto":
            return self._auto_league
        return selected or self._auto_league

    def _persist_trade_league(self):
        value = self._league_selection_value()
        if not value:
            value = "auto"
        self._app_config.setdefault("poetore", {})["league"] = value
        if self._save_app_config is not None:
            self._save_app_config(self._app_config)
        item = getattr(self, "_parsed_item", None)
        if item is not None:
            self._refresh_hidden_split_default(item)
            self._poe_ninja_item_key = None
            self._queue_poe_ninja_price(item)

    def _selected_search_range(self) -> int:
        return int(self.search_range_combo.currentData() or 0)

    def _resolved_trade_filters(self, item, preset):
        return apply_search_range(
            resolve_trade_stat_filters(
                item, preset, self._trade_base_type, self._trade_item_name,
            ),
            self._selected_search_range(),
            item,
        )

    def _search_range_changed(self):
        value = self._selected_search_range()
        self._app_config.setdefault("poetore", {})["search_stat_range"] = value
        if self._save_app_config is not None:
            self._save_app_config(self._app_config)
        item = getattr(self, "_parsed_item", None)
        if item is not None:
            previous_filters = self._selected_stat_filters()
            preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
            resolved_filters = self._resolved_trade_filters(item, preset)
            enabled_by_key: dict[tuple, list[bool]] = {}
            for row in previous_filters:
                key = self._stat_filter_identity(row)
                enabled_by_key.setdefault(key, []).append(row.enabled)
            adjusted_filters = []
            for row in resolved_filters:
                states = enabled_by_key.get(self._stat_filter_identity(row))
                adjusted_filters.append(
                    replace(row, enabled=states.pop(0)) if states else row
                )
            self._populate_stat_filters(tuple(adjusted_filters))
            self._mark_search_dirty()

    @staticmethod
    def _stat_filter_identity(row: TradeStatFilter) -> tuple:
        """数値範囲と選択状態を除いた、再生成前後で安定する行識別子。"""
        return (
            row.stat_id,
            row.ref,
            row.text,
            row.kind,
            row.option_value,
            row.group_type,
            row.group_key,
            row.selection_reason,
        )

    def _league_selection_value(self) -> str:
        index = self.trade_league_combo.currentIndex()
        text = self.trade_league_combo.currentText().strip()
        if index >= 0 and text == self.trade_league_combo.itemText(index):
            selected = self.trade_league_combo.itemData(index)
            if selected:
                return str(selected)
        return text

    def _queue_poe_ninja_price(self, item):
        league = self._selected_trade_league()
        key = (
            item.raw_text, league, str(self._trade_item_name or ""),
            str(self._trade_base_type or ""),
        )
        if key == self._poe_ninja_item_key:
            return
        self._poe_ninja_item_key = key
        trace = self._current_performance_trace
        self._hide_poe_ninja_price(key)
        self._hide_related_items(key)
        self._queue_divine_rate(league)
        if trace is not None:
            self._poe_ninja_performance_traces[key] = trace
            trace.mark("poe_ninja_queued", league=league)
        if not league:
            return

        def run():
            if trace is not None:
                trace.mark("poe_ninja_lookup_started")
            try:
                result = default_poe_ninja_service.lookup(
                    item, league,
                    trade_name=self._trade_item_name,
                    trade_base_type=self._trade_base_type,
                )
                related = self._lookup_related_items(item, league, result)
            except Exception:
                if trace is not None:
                    trace.mark("poe_ninja_lookup_failed")
                self._trade_signals.poe_ninja_failed.emit(key)
                self._trade_signals.related_items_failed.emit(key)
            else:
                if trace is not None:
                    trace.mark(
                        "poe_ninja_lookup_completed",
                        matched=result is not None,
                        related=bool(related),
                    )
                if result is None:
                    self._trade_signals.poe_ninja_failed.emit(key)
                else:
                    self._trade_signals.poe_ninja_ready.emit(key, result)
                if related:
                    self._trade_signals.related_items_ready.emit(key, related)
                else:
                    self._trade_signals.related_items_failed.emit(key)

        threading.Thread(target=run, daemon=True).start()

    def _lookup_related_items(self, item, league, primary_price=None):
        namespace = (
            "UNIQUE" if item.rarity.casefold() in {"unique", "ユニーク"}
            else "GEM" if item.category == "gem"
            else "DIVINATION_CARD" if item.category == "divination_card"
            else "ITEM"
        )
        names = tuple(dict.fromkeys(
            str(value).strip() for value in (
                self._trade_item_name, self._trade_base_type,
                getattr(primary_price, "name", None), item.name, item.base_type,
            ) if value and str(value).strip()
        ))
        variant = str(
            getattr(primary_price, "variant", None) or self._trade_base_type or ""
        ) if namespace == "UNIQUE" else None
        group = next(
            (found for name in names
             if (found := related_item_group(namespace, name, variant)) is not None),
            None,
        )
        if group is None:
            return None

        all_rows = tuple(group.get("query", ())) + tuple(group.get("items", ()))
        identities = tuple(
            (
                str(row.get("namespace", "")),
                str(row.get("name", "")),
                row.get("variant"),
            )
            for row in all_rows
        )
        prices = default_poe_ninja_service.lookup_identities(identities, league)
        price_by_id = {
            str(row.get("id", "")): price for row, price in zip(all_rows, prices)
        }

        def priced(rows):
            return tuple(
                ({
                    **dict(row),
                    "display_name": japanese_trade_item_label(
                        str(row.get("namespace", "")),
                        str(row.get("name", "")),
                        row.get("variant"),
                    ),
                }, price_by_id.get(str(row.get("id", ""))))
                for row in rows
            )

        return {
            "query": priced(group.get("query", ())),
            "items": priced(group.get("items", ())),
            "query_label": str(group.get("query_label") or "関連素材・同系統"),
            "current": (namespace, names[0].casefold()),
        }

    def _queue_divine_rate(self, league):
        key = str(league or "")
        if (
            key == self._divine_rate_key
            and (self.divine_rate_button.isEnabled() or time.monotonic() < self._divine_rate_retry_after)
        ):
            return
        self._divine_rate_key = key
        self._divine_rate_retry_after = float("inf")
        self.divine_rate_button.setText("⇄ …")
        self.divine_rate_button.setEnabled(False)
        self.divine_rate_button.setVisible(bool(league))
        self.divine_rate_menu.clear()
        if not league:
            return

        def run():
            try:
                rate = default_poe_ninja_service.divine_chaos_rate(league)
            except Exception:
                self._trade_signals.divine_rate_failed.emit(key)
            else:
                if rate is None:
                    self._trade_signals.divine_rate_failed.emit(key)
                else:
                    self._trade_signals.divine_rate_ready.emit(key, rate)

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _awakened_round(value: float) -> int:
        return math.floor(value + 0.5)

    def _show_divine_rate(self, key, rate):
        if key != self._divine_rate_key:
            return
        rate = float(rate)
        self.divine_rate_button.setText(f"⇄ {self._awakened_round(rate)}")
        self.divine_rate_button.setEnabled(True)
        self.divine_rate_button.show()
        self.divine_rate_menu.clear()
        divine_icon_path = _asset_icon_path(_PRICE_CURRENCY_ICONS["divine"])
        chaos_icon_path = _asset_icon_path(_PRICE_CURRENCY_ICONS["chaos"])
        for step in range(1, 10):
            divine = step / 10
            chaos = self._awakened_round(rate * divine)
            action = QWidgetAction(self.divine_rate_menu)
            action.setText(f"{divine:.1f} div  →  {chaos} c")
            row = QWidget(self.divine_rate_menu)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 3, 14, 3)
            layout.setSpacing(5)
            for icon_path, text in (
                (divine_icon_path, f"{divine:.1f}"),
                (None, "→"),
                (chaos_icon_path, str(chaos)),
            ):
                if icon_path is not None:
                    icon = QLabel()
                    pixmap = QPixmap(str(icon_path))
                    icon.setPixmap(pixmap.scaled(
                        18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation,
                    ))
                    layout.addWidget(icon)
                label = QLabel(text)
                label.setStyleSheet("color: #E6ECEA; background: transparent;")
                layout.addWidget(label)
            action.setDefaultWidget(row)
            self.divine_rate_menu.addAction(action)

    def _hide_divine_rate(self, key=None):
        if key is not None and key != self._divine_rate_key:
            return
        self.divine_rate_button.hide()
        self.divine_rate_button.setEnabled(False)
        self.divine_rate_menu.clear()
        self._divine_rate_retry_after = time.monotonic() + 4 * 60

    def _show_poe_ninja_price(self, key, price: PoeNinjaPrice):
        if key != self._poe_ninja_item_key:
            trace = self._poe_ninja_performance_traces.pop(key, None)
            if trace is not None:
                trace.mark("stale_poe_ninja_result_discarded")
            return
        amount, currency = price.display_price_parts()
        self.poe_ninja_price_value.setText(amount)
        icon_path = _asset_icon_path(_PRICE_CURRENCY_ICONS[currency])
        pixmap = QPixmap(str(icon_path)) if icon_path else QPixmap()
        self.poe_ninja_currency_icon.setPixmap(
            pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not pixmap.isNull() else QPixmap()
        )
        currency_name = "Divine Orb" if currency == "divine" else "Chaos Orb"
        self.poe_ninja_currency_icon.setToolTip(currency_name)
        self.poe_ninja_price_multiplier.setVisible(not pixmap.isNull())
        self.poe_ninja_currency_icon.setVisible(not pixmap.isNull())
        if pixmap.isNull():
            self.poe_ninja_price_value.setText(price.display_price())
        trend = price.trend_summary()
        self.poe_ninja_trend_label.setText(
            f"{trend[0]} {trend[1]}\n7日推移" if trend else "7日データなし"
        )
        self.poe_ninja_trend_chart.setPoints(price.graph_points())
        self._last_poe_ninja_url = price.url
        self.poe_ninja_price_panel.show()
        trace = self._poe_ninja_performance_traces.pop(key, None)
        if trace is not None:
            trace.mark("poe_ninja_result_displayed")

    def _hide_poe_ninja_price(self, key=None):
        if key is not None and key != self._poe_ninja_item_key:
            trace = self._poe_ninja_performance_traces.pop(key, None)
            if trace is not None:
                trace.mark("stale_poe_ninja_error_discarded")
            return
        trace = self._poe_ninja_performance_traces.pop(key, None) if key is not None else None
        if trace is not None:
            trace.mark("poe_ninja_result_unavailable")
        self.poe_ninja_price_panel.hide()
        self.poe_ninja_price_value.setText("—")
        self.poe_ninja_price_multiplier.show()
        self.poe_ninja_currency_icon.clear()
        self.poe_ninja_currency_icon.setToolTip("")
        self.poe_ninja_trend_label.clear()
        self.poe_ninja_trend_chart.setPoints(())
        self._last_poe_ninja_url = ""

    def _show_related_items(self, key, result):
        if key != self._poe_ninja_item_key:
            return
        self.related_items_tree.clear()
        current = result.get("current")
        for title, rows in (
            (str(result.get("query_label") or "関連素材・同系統"), result.get("query", ())),
            ("報酬・派生品", result.get("items", ())),
        ):
            if not rows:
                continue
            parent = QTreeWidgetItem([title, ""])
            self.related_items_tree.addTopLevelItem(parent)
            for row, price in rows:
                is_current = (
                    str(row.get("namespace", "")), str(row.get("name", "")).casefold()
                ) == current
                display_name = str(row.get("display_name") or row["name"])
                label = f"● {display_name}" if is_current else display_name
                child = QTreeWidgetItem([
                    label, price.display_price() if price is not None else "—",
                ])
                if price is not None:
                    child.setToolTip(1, "poe.ninja参考価格")
                parent.addChild(child)
            parent.setExpanded(True)
        visible = self.related_items_tree.topLevelItemCount() > 0
        self.related_items_panel.setVisible(visible)
        self._apply_related_items_layout(visible)

    def _hide_related_items(self, key=None):
        if key is not None and key != self._poe_ninja_item_key:
            return
        self.related_items_tree.clear()
        self.related_items_panel.hide()
        self._apply_related_items_layout(False)

    def _apply_related_items_layout(self, visible: bool):
        """関連品がある時だけ価格結果欄の一部を関連品一覧へ割り当てる。"""
        profile = _DISPLAY_SIZE_PROFILES[self._result_font_size]
        related_height = self._scaled_display_value(_RELATED_ITEMS_TREE_HEIGHT)
        self.related_items_tree.setMinimumHeight(related_height if visible else 0)
        self.related_items_tree.setMaximumHeight(related_height)
        price_height = profile["price_height"]
        if visible:
            price_height = max(
                120,
                price_height
                - self._scaled_display_value(_RELATED_ITEMS_PRICE_HEIGHT_REDUCTION),
            )
        self.price_list.setMinimumHeight(price_height)
        self._adjust_window_height_to_mod_rows()

    def _open_poe_ninja_url(self):
        if self._last_poe_ninja_url:
            QDesktopServices.openUrl(QUrl(self._last_poe_ninja_url))

    def showEvent(self, event):
        if not self._focus_signal_connected:
            QApplication.instance().focusChanged.connect(self._close_when_focus_leaves_panel)
            self._focus_signal_connected = True
        item = getattr(self, "_parsed_item", None)
        if item is not None:
            self._queue_poe_ninja_price(item)
        super().showEvent(event)

    def closeEvent(self, event):
        self._passive_hotkey_display = False
        self._auto_hide_interactive = False
        self._stop_outside_click_listener()
        if self._focus_signal_connected:
            QApplication.instance().focusChanged.disconnect(self._close_when_focus_leaves_panel)
            self._focus_signal_connected = False
        super().closeEvent(event)

    def capture_from_poe(
        self,
        performance_trace: SearchPerformanceTrace | None = None,
        *,
        auto_hide: bool = False,
        capture_hotkey: str | None = None,
    ):
        """PoE 3.29以降の詳細形式コピーを一度だけ取得して解析する。"""
        from pynput.keyboard import Controller, Key

        trace = performance_trace or start_search_trace("alt_d_direct")
        self._pending_performance_trace = trace
        trace.mark("capture_started")

        # この時点ではPoEが前面。コピー後にぽえとれがフォーカスを取る前に保存する。
        self._placement_context = capture_placement_context()
        self._capture_auto_hide = auto_hide
        self._auto_hide_hotkey_released = False
        self._auto_hide_origin = self._placement_context.cursor_pos
        self._auto_hide_interactive = False
        foreground = get_foreground_window()
        self._poe_window_hwnd = (
            foreground if is_path_of_exile_window(foreground) else None
        )
        self._capture_keyboard = Controller()
        generation = getattr(self, "_capture_release_generation", 0) + 1
        self._capture_release_generation = generation
        self._capture_copy_started = False
        hold_modifier = next(
            (
                token.strip().casefold()
                for token in str(capture_hotkey or "").split("+")
                if token.strip().casefold() in {"ctrl", "control", "alt"}
            ),
            None,
        )
        self._capture_copy_keys = (
            ("c",) if auto_hide and hold_modifier in {"ctrl", "control"}
            else (Key.ctrl, "c")
        )
        if auto_hide and self._release_auto_hide_trigger_key(capture_hotkey, Key):
            trace.mark("copy_scheduled", release_wait_timeout_ms=30)
            QTimer.singleShot(
                30,
                lambda: self._start_capture_copy(generation, "trigger_key_released"),
            )
        trace.mark("copy_scheduled", release_wait_timeout_ms=250)
        QTimer.singleShot(
            250,
            lambda: self._start_capture_copy(generation, "release_timeout"),
        )

    def _release_auto_hide_trigger_key(self, hotkey: str | None, key_enum) -> bool:
        """Release only the non-modifier key, matching Awakened's hold-key mode."""
        tokens = [token.strip().casefold() for token in str(hotkey or "").split("+")]
        trigger_keys = [
            token for token in tokens
            if token and token not in {"ctrl", "control", "alt", "shift", "win", "meta"}
        ]
        if len(trigger_keys) != 1:
            return False
        token = trigger_keys[0]
        key = token if len(token) == 1 else getattr(key_enum, token, None)
        if key is None:
            return False
        from src.utils.internal_key_input import internal_key_input

        try:
            with internal_key_input():
                self._capture_keyboard.release(key)
        except Exception:
            return False
        return True

    def capture_hotkey_released(self):
        """Start copying once every key in the configured capture hotkey is up."""
        if self._capture_auto_hide:
            self._auto_hide_hotkey_released = True
        generation = getattr(self, "_capture_release_generation", None)
        if generation is not None:
            self._start_capture_copy(generation, "hotkey_released")

    def _start_capture_copy(self, generation: int, source: str):
        if generation != getattr(self, "_capture_release_generation", None):
            return
        if getattr(self, "_capture_copy_started", False):
            return
        self._capture_copy_started = True
        trace = self._pending_performance_trace
        if trace is not None:
            trace.mark("copy_triggered", source=source)
        self._send_copy(self._capture_copy_keys, self._capture_item_copy)

    def _send_copy(self, keys, callback):
        from src.utils.internal_key_input import internal_key_input

        trace = self._pending_performance_trace
        if trace is not None:
            trace.mark("copy_keys_started")
        previous_token = clipboard_change_token(QApplication.clipboard())
        with internal_key_input(
            cooldown_seconds=0 if self._capture_auto_hide else 0.12,
        ):
            for key in keys:
                self._capture_keyboard.press(key)
            for key in reversed(keys):
                self._capture_keyboard.release(key)
        if trace is not None:
            trace.mark(
                "copy_keys_sent", clipboard_poll_ms=10, callback_timeout_ms=300,
            )
        generation = getattr(self, "_clipboard_wait_generation", 0) + 1
        self._clipboard_wait_generation = generation
        self._wait_for_clipboard_update(previous_token, callback, generation, 0)

    def _wait_for_clipboard_update(self, previous_token, callback, generation, elapsed_ms):
        """Continue as soon as Ctrl+C rewrites the clipboard, with a safe timeout."""
        if generation != getattr(self, "_clipboard_wait_generation", None):
            return
        current_token = clipboard_change_token(QApplication.clipboard())
        trace = self._pending_performance_trace
        if current_token != previous_token:
            if trace is not None:
                trace.mark("clipboard_change_detected", wait_ms=elapsed_ms)
            callback()
            return
        if elapsed_ms >= 300:
            if trace is not None:
                trace.mark("clipboard_change_timeout", wait_ms=elapsed_ms)
            callback()
            return
        delay_ms = min(10, 300 - elapsed_ms)
        QTimer.singleShot(
            delay_ms,
            lambda: self._wait_for_clipboard_update(
                previous_token, callback, generation, elapsed_ms + delay_ms,
            ),
        )

    def _build_capture_error_dialog(self) -> QMessageBox:
        """Create a readable error dialog that matches the dark poetore theme."""
        message = QMessageBox(self)
        message.setObjectName("poetoreCaptureError")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText(
            "アイテムを取得できませんでした。\n"
            "PoEがアクティブでない可能性があります。\n"
            "PoEを前面にしてアイテムへカーソルを合わせ、\n"
            "もう一度 Alt+D を押してください。"
        )
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        # QMessageBox may reset an empty application title while configuring its buttons.
        message.setWindowTitle("取り込めませんでした")
        message.setStyleSheet("""
            QMessageBox {
                background-color: #111111;
                color: #E6ECEA;
            }
            QMessageBox QLabel {
                background-color: transparent;
                color: #E6ECEA;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
            }
            QMessageBox QPushButton {
                min-width: 54px;
                padding: 5px 12px;
                background-color: #1a1a1a;
                color: #49D6B0;
                border: 1px solid #49D6B0;
                border-radius: 3px;
                font-weight: 700;
            }
            QMessageBox QPushButton:hover {
                background-color: #2a2a2a;
                border-color: #ffffff;
            }
            QMessageBox QPushButton:pressed {
                background-color: #000000;
            }
        """)
        return message

    def _capture_item_copy(self):
        trace = self._pending_performance_trace
        copied_text = read_item_clipboard(QApplication.clipboard())
        if trace is not None:
            trace.mark("clipboard_read", characters=len(copied_text))
        try:
            item = parse_item_text(copied_text)
        except ItemParseError:
            if trace is not None:
                trace.mark("clipboard_parse_failed")
            self._pending_performance_trace = None
            self._build_capture_error_dialog().exec()
            return
        if trace is not None:
            trace.mark(
                "clipboard_parsed", category=item.category, modifiers=len(item.modifiers),
            )
        copied_name = item.name if item.rarity.casefold() in {"unique", "ユニーク"} else None
        try:
            self._trade_base_type, self._trade_item_name = english_trade_identity(
                item, item.base_type, copied_name,
            )
        except TradeApiError:
            # 公式items取得が一時的に失敗しても、検索スレッド側で再試行できる。
            self._trade_base_type, self._trade_item_name = item.base_type, copied_name
        if trace is not None:
            trace.mark("capture_identity_resolved")
        self._preset_item_key = None
        self._reset_unique_candidates()
        self.mod_filter_tree.clear()
        self.input_edit.setPlainText(copied_text)
        self.parse_current_text()
        if trace is not None:
            trace.mark("capture_ui_populated")
        self.show_at_context(
            self._placement_context, activate=not self._capture_auto_hide,
        )
        if trace is not None:
            trace.mark("window_shown")
        self.search_current_item()

    def _close_and_return_to_poe(self):
        """操作可能なぽえとれを閉じ、Alt+D取得元のPoEへ戻る。"""
        target_hwnd = self._poe_window_hwnd
        self._poe_window_hwnd = None
        self.close()
        if target_hwnd is not None:
            QTimer.singleShot(0, lambda: focus_window(target_hwnd))

    def show_at_context(self, context: PlacementContext | None = None, activate: bool = True):
        context = context or capture_placement_context()
        self._placement_context = context
        poetore_config = self._app_config.get("poetore", {})
        saved_positions = (
            poetore_config.get("result_positions", {})
            if isinstance(poetore_config, dict) else {}
        )
        saved_position = (
            saved_positions.get(placement_side(context))
            if isinstance(saved_positions, dict) else None
        )
        position = position_from_relative(context, self.size(), saved_position)
        self.move(position or position_for_context(context, self.size()))
        self._passive_hotkey_display = not activate
        self.show()
        self.raise_()
        if activate:
            self._stop_outside_click_listener()
            self.activateWindow()
            self.setFocus(Qt.OtherFocusReason)
        else:
            self._start_outside_click_listener()

    def _persist_manual_result_position(self):
        """タイトルバーのドラッグ終了時だけ、検索元の側へ位置を保存する。"""
        context = self._placement_context
        if context is None:
            return
        poetore_config = self._app_config.setdefault("poetore", {})
        positions = poetore_config.setdefault("result_positions", {})
        if not isinstance(positions, dict):
            positions = {}
            poetore_config["result_positions"] = positions
        positions[placement_side(context)] = relative_panel_position(
            context, self.pos(), self.size(),
        )
        if self._save_app_config is not None:
            self._save_app_config(self._app_config)

    def _start_outside_click_listener(self):
        """Alt+D表示中だけ、ぽえとれ外のクリックを検知する。"""
        if sys.platform != "win32" or self._outside_click_listener is not None:
            return
        from pynput import mouse

        def on_click(x, y, _button, pressed):
            if pressed:
                self._trade_signals.global_mouse_pressed.emit(round(x), round(y))

        def on_move(x, y):
            self._trade_signals.global_mouse_moved.emit(round(x), round(y))

        self._outside_click_listener = mouse.Listener(
            on_click=on_click, on_move=on_move,
        )
        self._outside_click_listener.start()

    def _stop_outside_click_listener(self):
        listener = self._outside_click_listener
        self._outside_click_listener = None
        if listener is not None:
            listener.stop()

    def _handle_global_mouse_press(self, x: int, y: int):
        if not self.isVisible() or not self._passive_hotkey_display:
            return
        if self._auto_hide_area_contains(self._global_cursor_point(x, y)):
            if self._capture_auto_hide:
                self._enter_auto_hide_interactive()
        else:
            self.close()

    def _handle_global_mouse_move(self, x: int, y: int):
        """Mirror Awakened's AUTO-HIDE behavior without stealing PoE focus."""
        if not self.isVisible() or not (
            self._passive_hotkey_display or self._auto_hide_interactive
        ):
            return
        point = self._global_cursor_point(x, y)
        if self._auto_hide_interactive:
            if not self._auto_hide_area_contains(point):
                self._stop_outside_click_listener()
                self._close_and_return_to_poe()
            return
        if not self._auto_hide_hotkey_released:
            if self._auto_hide_area_contains(point):
                self._enter_auto_hide_interactive()
            return
        origin = self._auto_hide_origin
        if origin is not None and (
            (point.x() - origin.x()) ** 2 + (point.y() - origin.y()) ** 2
        ) >= 40 ** 2:
            self.close()

    def _enter_auto_hide_interactive(self):
        self._passive_hotkey_display = False
        self._auto_hide_interactive = True
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)

    def _global_cursor_point(self, x: int, y: int) -> QPoint:
        """Use Qt's coordinate space on Windows to avoid per-monitor DPI drift."""
        if sys.platform == "win32":
            return QCursor.pos()
        return QPoint(x, y)

    def _auto_hide_area_contains(self, point: QPoint) -> bool:
        if self.frameGeometry().contains(point):
            return True
        popup = QApplication.instance().activePopupWidget()
        return bool(
            popup is not None
            and self._widget_belongs_to_panel(popup)
            and popup.window().frameGeometry().contains(point)
        )

    def parse_current_text(self):
        trace = self._current_performance_trace or self._pending_performance_trace
        if trace is not None:
            trace.mark("ui_parse_started")
        self._parsed_item = None
        try:
            item = parse_item_text(self.input_edit.toPlainText())
        except ItemParseError as exc:
            if trace is not None:
                trace.mark("ui_parse_failed")
            QMessageBox.warning(self, "解析できませんでした", str(exc))
            return
        if trace is not None:
            trace.mark("ui_parse_completed", modifiers=len(item.modifiers))
        is_new_item = item.raw_text != self._active_item_key
        if is_new_item:
            self._active_item_key = item.raw_text
            self._has_searched_current_item = False
            self._search_dirty = False
            self._search_generation += 1
        if item.raw_text != self._unique_selector_item_key:
            self._reset_unique_candidates()
            self._unique_selector_item_key = item.raw_text
        self._configure_trade_presets(item)
        self._configure_trade_currency(item)
        self._configure_item_state_filters(item)
        self._configure_item_level(item, force=is_new_item)
        self._configure_gem_level(item)
        self._configure_quality(item)
        self._configure_links(item)
        self._configure_influence_chips(item)
        self._configure_special_filter_chips(item)
        self._update_item_header(item)
        self.result_tree.clear()
        for label, value in (
            ("アイテムクラス", item.item_class), ("レアリティ", item.rarity),
            ("名前", item.name), ("ベースタイプ", item.base_type),
            ("カテゴリ", item.category), ("アイテムレベル", item.item_level),
            ("状態", ", ".join(item.flags) or "なし"),
        ):
            QTreeWidgetItem(self.result_tree, [label, "" if value is None else str(value)])
        properties = QTreeWidgetItem(self.result_tree, ["プロパティ", str(len(item.properties))])
        for label, value in item.properties.items():
            QTreeWidgetItem(properties, [label, value])
        modifiers = QTreeWidgetItem(self.result_tree, ["Mod", str(len(item.modifiers))])
        for mod in item.modifiers:
            values = ", ".join(f"{value:g}" for value in mod.values)
            QTreeWidgetItem(modifiers, [mod.kind, f"{mod.text}" + (f"  [{values}]" if values else "")])
        self.result_tree.expandAll()
        self.result_tree.scrollToTop()
        self._parsed_item = item
        if self.mod_filter_tree.topLevelItemCount() == 0:
            preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
            if trace is not None:
                trace.mark("initial_filter_resolution_started")
            initial_filters = self._resolved_trade_filters(item, preset)
            if trace is not None:
                trace.mark(
                    "initial_filter_resolution_completed", filters=len(initial_filters),
                )
            self._populate_stat_filters(initial_filters)
        if is_new_item:
            self._reset_mod_conditions_for_item()
        warnings = unresolved_modifier_warnings(
            item, tuple(getattr(self, "_special_chip_rows", {}).values()),
        )
        if warnings:
            preview = " / ".join(warnings[:3])
            suffix = f" ほか{len(warnings) - 3}件" if len(warnings) > 3 else ""
            self.mod_warning.setText(
                f"⚠ メタデータ未解決 {len(warnings)}件（検索時に公式API照合を試行）: {preview}{suffix}"
            )
            self.mod_warning.show()
        else:
            self.mod_warning.clear()
            self.mod_warning.hide()
        if _is_valdo_map(item) and (
            item.properties.get("報酬") or item.properties.get("Reward")
            or item.properties.get("マップ完了報酬")
            or item.properties.get("Map Completion Reward")
        ):
            self.search_scope_notice.setText(
                "⚠ Valdo Mapの報酬条件を使った検索は初版では対応していません。"
                "報酬を除く条件で検索します。"
            )
            self.search_scope_notice.show()
            self.price_button.setEnabled(True)
        elif is_inscribed_ultimatum(item):
            self.search_scope_notice.setText(
                "⚠ チャレンジタイプ・報酬種類・必要なアイテム・報酬などの条件を使った検索には対応しておりません。"
            )
            self.search_scope_notice.show()
            self.price_button.setEnabled(True)
        else:
            self.search_scope_notice.clear()
            self.search_scope_notice.hide()
            self.price_button.setEnabled(True)
        if self.isVisible():
            self._queue_poe_ninja_price(item)
        if trace is not None:
            trace.mark("ui_parse_applied")

    def search_current_item(self):
        trace = self._pending_performance_trace or start_search_trace("manual_search")
        self._pending_performance_trace = None
        self._current_performance_trace = trace
        trace.mark("search_invoked")
        # 前回のUniqueで隠し候補を開いたまま次を検索すると、通常候補が
        # 空に見えて誤解を招く。チェック状態は検索へ残し、表示だけ戻す。
        self.hidden_mods_toggle.setChecked(False)
        self.parse_current_text()
        item = getattr(self, "_parsed_item", None)
        if item is None:
            trace.mark("search_parse_failed")
            self._current_performance_trace = None
            return
        trace.mark("search_ui_prepared")
        self._has_searched_current_item = True
        self._search_dirty = False
        self._search_generation += 1
        search_generation = self._search_generation
        self._search_performance_traces[search_generation] = trace
        self.price_button.setEnabled(False)
        self.trade_url_button.setEnabled(False)
        self.price_list.clear()
        trade_status = str(self.trade_status_combo.currentData())
        trade_status_label = self.trade_status_combo.currentText()
        trade_currency = str(self.trade_currency_combo.currentData())
        trade_currency_label = self.trade_currency_combo.currentText()
        listed_within = str(self.listed_within_combo.currentData() or "any")
        listed_within_label = self.listed_within_combo.currentText()
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        preset_label = self.trade_preset_combo.currentText()
        include_corrupted = (
            self.corrupted_combo.currentData()
            if not self.corrupted_combo.isHidden() else None
        )
        include_split = (
            bool(self.split_combo.currentData())
            if not self.split_combo.isHidden()
            else bool(getattr(self, "_hidden_include_split", True))
        )
        include_mirrored = (
            bool(self.mirrored_combo.currentData())
            if not self.mirrored_combo.isHidden()
            else bool(getattr(self, "_hidden_include_mirrored", True))
        )
        item_level_min, item_level_max = self._selected_item_level_range()
        gem_level_min = self._selected_gem_level()
        quality_min = self._selected_quality()
        links_min = self._selected_links()
        links_chip_visible = not self.links_tag.isHidden()
        influence_filters = self._selected_influence_filters()
        include_searing, include_tangled = self._selected_eldritch_influences()
        special_filters = self._selected_special_chip_filters()
        include_unidentified = (
            bool(self.unidentified_chip.currentData())
            if not self.unidentified_chip.isHidden() else None
        )
        include_veiled = bool(self.veiled_chip.currentData()) if not self.veiled_chip.isHidden() else None
        include_foil = bool(self.foil_chip.currentData()) if not self.foil_chip.isHidden() else None
        magic_exact = bool(
            self.magic_rarity_toggle.isVisible() and self.magic_rarity_toggle.currentData()
        )
        league = self._selected_trade_league()
        league_label = league or "現行SC（自動）"
        self.price_status.setText(
            f"{league_label}で「{preset_label} / {trade_status_label} / "
            f"{trade_currency_label} / {listed_within_label}」を検索中…"
        )
        filters = self._selected_stat_filters()
        needs_initial_filters = self.mod_filter_tree.topLevelItemCount() == 0
        selected_button = self.unique_name_group.checkedButton()
        selected_unique_name = (
            selected_button.property("uniqueName")
            if self.unique_name_container.isVisible() and selected_button is not None
            else None
        )
        trade_name = str(selected_unique_name or self._trade_item_name or "").strip() or None
        selected_discriminator = (
            self.unique_variant_combo.currentData() if self.unique_variant_combo.isVisible() else None
        )

        def run():
            try:
                trace.mark("filter_resolution_started")
                initial_filters = self._resolved_trade_filters(
                    item, preset,
                ) if needs_initial_filters else ()
                effective_filters = initial_filters if needs_initial_filters else filters
                # ilvlは上部の共通チップだけを正本にする。Mod一覧が空の専用検索では
                # 初期フィルターのproperty.item_levelが復活し、チップOFFでも送信
                # されていたため、最終送信前に必ず除外する。
                effective_filters = tuple(
                    row for row in effective_filters
                    if row.stat_id != "property.item_level"
                )
                if item.category in {"gem", "weapon", "armour", "flask", "tincture"}:
                    effective_filters = tuple(
                        row for row in effective_filters
                        if row.stat_id not in {"property.gem_level", "property.quality"}
                    )
                if links_chip_visible:
                    effective_filters = tuple(
                        row for row in effective_filters
                        if row.stat_id not in {"property.links", "property.sockets"}
                    )
                effective_filters = _replace_filters_with_special_chips(
                    effective_filters, influence_filters, special_filters,
                )
                trace.mark(
                    "filter_resolution_completed", filters=len(effective_filters),
                )
                if item.rarity.casefold() in {"unique", "ユニーク"} and "unidentified" in item.flags and not trade_name:
                    candidates = unique_candidate_details(self._trade_base_type or item.base_type)
                    if len(candidates) > 1:
                        self._trade_signals.unique_candidates_ready.emit(candidates)
                        return
                    if not candidates:
                        raise TradeApiError("未鑑定ユニークの候補を公式データから特定できませんでした。")
                    resolved_trade_name = candidates[0].name
                else:
                    resolved_trade_name = trade_name
                if resolved_trade_name and item.rarity.casefold() in {"unique", "ユニーク"}:
                    variants = unique_variants(resolved_trade_name, self._trade_base_type or item.base_type)
                    if len(variants) > 1 and not self.unique_variant_combo.isVisible():
                        self._trade_signals.unique_variants_ready.emit(variants)
                        return
                result = search_prices(
                    item, self._trade_base_type, league=league, stat_filters=effective_filters,
                    trade_status=trade_status, trade_name=resolved_trade_name,
                    preset=preset,
                    trade_currency=trade_currency,
                    include_corrupted=include_corrupted,
                    include_split=include_split,
                    include_mirrored=include_mirrored,
                    trade_discriminator=str(selected_discriminator) if selected_discriminator else None,
                    listed_within=listed_within,
                    magic_exact=magic_exact,
                    exact_base_type=self._searches_exact_base_type(item),
                    item_level_min=item_level_min,
                    item_level_max=item_level_max,
                    gem_level_min=gem_level_min,
                    quality_min=quality_min,
                    links_min=links_min,
                    include_unidentified=include_unidentified,
                    include_veiled=include_veiled,
                    include_foil=include_foil,
                    include_searing=include_searing,
                    include_tangled=include_tangled,
                    performance_trace=trace,
                    partial_result_callback=lambda partial: (
                        self._trade_signals.partial_completed.emit(
                            partial, search_generation,
                        )
                    ),
                )
            except (TradeApiError, ValueError) as exc:
                trace.mark("search_failed", error_type=type(exc).__name__)
                self._trade_signals.failed.emit(str(exc), search_generation)
            else:
                trace.mark("search_result_signal_emitted")
                self._trade_signals.completed.emit(result, initial_filters, search_generation)

        threading.Thread(target=run, daemon=True).start()
        self._current_performance_trace = None

    def _configure_trade_presets(self, item):
        key = item.raw_text
        if key == self._preset_item_key:
            return
        self._preset_item_key = key
        presets = available_trade_presets(item)
        dedicated_exact = uses_dedicated_exact_preset(item)
        self.trade_preset_combo.blockSignals(True)
        rarity = (item.rarity or "").strip().casefold()
        if dedicated_exact and rarity in {"normal", "ノーマル"}:
            primary_label = "ベースアイテム"
        elif dedicated_exact:
            primary_label = "専用検索"
        else:
            primary_label = "完成品"
        self.trade_preset_combo.setItemText(0, primary_label)
        self.trade_preset_combo.setSecondAvailable(PRESET_BASE in presets)
        self.trade_preset_combo.setCurrentIndex(0)
        has_choice = len(presets) > 1
        self.trade_preset_combo.setEnabled(has_choice)
        self.trade_preset_combo.setVisible(has_choice)
        self.trade_preset_placeholder.setVisible(not has_choice)
        if dedicated_exact:
            self.trade_preset_combo.setToolTip(
                "このアイテム種別に必要な条件だけを使う専用検索です。"
            )
        else:
            self.trade_preset_combo.setToolTip(
                "未完成でクラフト価値がある装備は、完成品とベースアイテムを切り替えて検索できます。"
            )
        self.trade_preset_combo.blockSignals(False)
        self._configure_magic_rarity_toggle(item)
        self.mod_filter_tree.clear()

    def _configure_magic_rarity_toggle(self, item=None):
        item = item or getattr(self, "_parsed_item", None)
        show = bool(
            item is not None
            and self.trade_preset_combo.currentData() == PRESET_BASE
            and item.rarity.casefold() in {"magic", "マジック"}
            and item.category in {
                "weapon", "armour", "accessory", "cluster_jewel", "jewel", "abyss_jewel",
            }
        )
        self.magic_rarity_toggle.setVisible(show)
        if show:
            # AwakenedはAdorned用途のMagic Jewel／Abyss Jewelだけ、
            # Exact（ベース）検索でもrarityをMagic完全一致にする。
            self.magic_rarity_toggle.setCurrentIndex(
                1 if item.category in {"jewel", "abyss_jewel"} else 0
            )

    def _configure_trade_currency(self, item):
        """同じ参照アイテムでは選択を保持し、新しい種類では推奨値へ戻す。"""
        if item.rarity.casefold() in {"unique", "ユニーク"}:
            reference = self._trade_item_name or item.name or item.base_type
        else:
            reference = self._trade_base_type or item.base_type
        key = (item.category, str(reference).strip().casefold())
        if key == self._currency_item_key:
            return
        self._currency_item_key = key
        default_currency = default_trade_currency(item)
        index = self.trade_currency_combo.findData(default_currency)
        self.trade_currency_combo.setCurrentIndex(max(index, 0))

    def _configure_item_state_filters(self, item):
        """元アイテムが変わった時だけ推奨状態へ戻し、再検索時は選択を保持する。"""
        key = item.raw_text
        if key == self._state_item_key:
            return
        self._state_item_key = key
        self.corrupted_combo.setCurrentIndex(0 if "corrupted" in item.flags else 1)
        is_split = "split" in item.flags
        self.split_combo.setCurrentIndex(0)
        self.split_combo.setVisible(is_split)
        supports_corruption_filter = item.category in {
            "weapon", "armour", "accessory", "cluster_jewel", "jewel", "abyss_jewel",
            "gem", "map", "flask", "tincture", "heist_equipment", "sanctum_relic",
            "charm", "idol",
        }
        self.corrupted_combo.setVisible(supports_corruption_filter)
        self.corrupted_combo.setEnabled(supports_corruption_filter)
        rarity = item.rarity.casefold()
        craftable = (
            rarity not in {"unique", "ユニーク"}
            and item.category not in {"gem", "flask", "currency", "divination_card", "captured_beast"}
        )
        has_special_state = (
            "corrupted" in item.flags
            or "mirrored" in item.flags
            or "synthesised" in item.flags
            or any(flag.startswith("influence:") for flag in item.flags)
            or any(modifier.kind == "fractured" for modifier in item.modifiers)
        )
        self._split_item_is_craftable = craftable
        self._split_item_has_special_state = has_special_state
        self._refresh_hidden_split_default(item)
        is_mirrored = "mirrored" in item.flags
        self.mirrored_combo.setCurrentIndex(0)
        self.mirrored_combo.setVisible(is_mirrored)
        self._hidden_include_mirrored = not (craftable and "corrupted" not in item.flags)

    def _refresh_hidden_split_default(self, item):
        """Awakened準拠で、非表示のSplit条件をリーグ・プリセット別に決める。"""
        if "split" in item.flags:
            return
        craftable = bool(getattr(self, "_split_item_is_craftable", False))
        has_special_state = bool(getattr(self, "_split_item_has_special_state", False))
        league = str(self._selected_trade_league() or "")
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        exact = preset == PRESET_BASE or uses_dedicated_exact_preset(item)
        auto_exclude = (
            (league != "Standard" or exact)
            and craftable
            and not has_special_state
        )
        self._hidden_include_split = not auto_exclude

    def _configure_item_level(self, item, *, force: bool = False):
        """Awakenedのプリセット規則に合わせて共通ilvl条件を設定する。"""
        key = item.raw_text
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        state_key = (key, preset)
        if not force and state_key == getattr(self, "_item_level_item_key", None):
            return
        self._item_level_item_key = state_key
        preset_filter = preset_item_level_filter(
            item, preset, self._trade_base_type,
        )
        # 完成品の通常装備とFlask/Tinctureは任意条件として表示するが初期OFF。
        # Exact／クラフトベースはpreset_filterの値・初期状態を正本にする。
        optional_finished = (
            preset == PRESET_FINISHED
            and item.category in {"weapon", "armour", "accessory", "flask", "tincture"}
            and item.rarity.casefold() not in {"unique", "ユニーク"}
        )
        has_item_level = item.item_level is not None and (
            preset_filter is not None or optional_finished
        )
        self.item_level_tag.setVisible(has_item_level)
        self._set_item_level_filter_enabled(
            has_item_level and preset_filter is not None and preset_filter.enabled
        )
        is_cluster = has_item_level and item.category == "cluster_jewel"
        self.item_level_range_separator.setVisible(is_cluster)
        self.item_level_max_edit.setVisible(is_cluster)
        self.item_level_tag.setFixedWidth(157 if is_cluster else 104)
        if preset_filter is not None:
            self.item_level_edit.setText(f"{preset_filter.min_value:g}")
            self.item_level_max_edit.setText(
                f"{preset_filter.max_value:g}"
                if preset_filter.max_value is not None else ""
            )
        else:
            self.item_level_edit.setText(str(item.item_level) if has_item_level else "")
            self.item_level_max_edit.clear()

    def _selected_item_level(self) -> int | None:
        return self._selected_item_level_range()[0]

    def _toggle_item_level_filter(self):
        self._set_item_level_filter_enabled(not getattr(self, "_item_level_filter_enabled", False))

    def _enable_item_level_filter(self, _text: str = ""):
        self._set_item_level_filter_enabled(True)

    def _set_item_level_filter_enabled(self, enabled: bool):
        self._item_level_filter_enabled = bool(enabled)
        self.item_level_tag.setProperty("active", self._item_level_filter_enabled)
        self.item_level_toggle.setText("☑ ilvl：" if self._item_level_filter_enabled else "☐ ilvl：")
        for editor in (self.item_level_edit, self.item_level_max_edit):
            font = editor.font()
            font.setStrikeOut(not self._item_level_filter_enabled)
            editor.setFont(font)
        self.item_level_tag.style().unpolish(self.item_level_tag)
        self.item_level_tag.style().polish(self.item_level_tag)
        self.item_level_toggle.setToolTip(
            "クリックしてアイテムレベル条件を無効にします"
            if self._item_level_filter_enabled else
            "クリックしてアイテムレベル条件を有効にします"
        )

    def _selected_item_level_range(self) -> tuple[int | None, int | None]:
        if self.item_level_tag.isHidden() or not getattr(self, "_item_level_filter_enabled", False):
            return None, None
        minimum_text = self.item_level_edit.text().strip()
        maximum_text = self.item_level_max_edit.text().strip() if not self.item_level_max_edit.isHidden() else ""
        return (
            int(minimum_text) if minimum_text else None,
            int(maximum_text) if maximum_text else None,
        )

    def _configure_gem_level(self, item):
        key = item.raw_text
        if key == getattr(self, "_gem_level_item_key", None):
            return
        self._gem_level_item_key = key
        raw_level = item.properties.get("ジェムレベル") if item.category == "gem" else None
        match = re.search(r"\d+", str(raw_level or ""))
        level = int(match.group()) if match else None
        self.gem_level_tag.setVisible(level is not None)
        self.gem_level_edit.setText(str(level) if level is not None else "")
        self._set_gem_level_filter_enabled(level is not None)

    def _toggle_gem_level_filter(self):
        self._set_gem_level_filter_enabled(not getattr(self, "_gem_level_filter_enabled", False))

    def _enable_gem_level_filter(self, _text: str = ""):
        self._set_gem_level_filter_enabled(True)

    def _set_gem_level_filter_enabled(self, enabled: bool):
        self._gem_level_filter_enabled = bool(enabled)
        self.gem_level_tag.setProperty("active", self._gem_level_filter_enabled)
        self.gem_level_toggle.setText(
            "☑ ジェムLv：" if self._gem_level_filter_enabled else "☐ ジェムLv："
        )
        font = self.gem_level_edit.font()
        font.setStrikeOut(not self._gem_level_filter_enabled)
        self.gem_level_edit.setFont(font)
        self.gem_level_tag.style().unpolish(self.gem_level_tag)
        self.gem_level_tag.style().polish(self.gem_level_tag)
        self.gem_level_toggle.setToolTip(
            "クリックしてジェムレベル条件を無効にします"
            if self._gem_level_filter_enabled else
            "クリックしてジェムレベル条件を有効にします"
        )

    def _selected_gem_level(self) -> int | None:
        if self.gem_level_tag.isHidden() or not getattr(self, "_gem_level_filter_enabled", False):
            return None
        text = self.gem_level_edit.text().strip()
        return int(text) if text else None

    def _configure_quality(self, item):
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        key = (item.raw_text, preset)
        if key == getattr(self, "_gem_quality_item_key", None):
            return
        self._gem_quality_item_key = key
        raw_quality = item.properties.get("品質") or item.properties.get("Quality")
        match = re.search(r"\d+", str(raw_quality or ""))
        quality = int(match.group()) if match else None
        visible = False
        if item.category == "gem":
            visible = quality is not None and quality > 0
        elif item.category in {"weapon", "armour", "accessory"}:
            visible = quality is not None and (
                quality > 20
                or (preset == PRESET_BASE and quality >= 20)
            )
        elif item.category in {"flask", "tincture"}:
            visible = quality is not None and quality >= 20
        self.gem_quality_tag.setVisible(visible)
        self.gem_quality_edit.setText(str(quality) if quality is not None else "")
        enabled = False
        if visible and item.category == "gem":
            info = gem_metadata(self._trade_base_type or item.base_type)
            maximum = int(info.get("max_level", 20))
            enabled = (
                maximum == 1
                or (maximum == 20 and not info.get("transfigured") and quality >= 16)
                or ((maximum != 20 or info.get("transfigured")) and quality >= 20)
            )
        elif visible:
            enabled = quality > 20
        self._set_gem_quality_filter_enabled(enabled)

    def _toggle_gem_quality_filter(self):
        self._set_gem_quality_filter_enabled(not getattr(self, "_gem_quality_filter_enabled", False))

    def _enable_gem_quality_filter(self, _text: str = ""):
        self._set_gem_quality_filter_enabled(True)

    def _set_gem_quality_filter_enabled(self, enabled: bool):
        self._gem_quality_filter_enabled = bool(enabled)
        self.gem_quality_tag.setProperty("active", self._gem_quality_filter_enabled)
        self.gem_quality_toggle.setText(
            "☑ 品質：" if self._gem_quality_filter_enabled else "☐ 品質："
        )
        font = self.gem_quality_edit.font()
        font.setStrikeOut(not self._gem_quality_filter_enabled)
        self.gem_quality_edit.setFont(font)
        self.gem_quality_tag.style().unpolish(self.gem_quality_tag)
        self.gem_quality_tag.style().polish(self.gem_quality_tag)
        self.gem_quality_toggle.setToolTip(
            "クリックして品質条件を無効にします"
            if self._gem_quality_filter_enabled else
            "クリックして品質条件を有効にします"
        )

    def _selected_quality(self) -> int | None:
        if self.gem_quality_tag.isHidden() or not getattr(self, "_gem_quality_filter_enabled", False):
            return None
        text = self.gem_quality_edit.text().strip()
        return int(text) if text else None

    def _configure_links(self, item):
        key = item.raw_text
        if key == getattr(self, "_links_item_key", None):
            return
        self._links_item_key = key
        socket_text = item.properties.get("ソケット") or item.properties.get("Sockets") or ""
        groups = re.findall(r"[RGBW](?:-[RGBW])*", socket_text.upper())
        linked = max((len(group.split("-")) for group in groups), default=0)
        visible = linked >= 1 and item.category in {"weapon", "armour"}
        self.links_tag.setVisible(visible)
        self.links_edit.setText(str(linked) if visible else "")
        self._set_links_filter_enabled(visible and linked in {5, 6})

    def _toggle_links_filter(self):
        self._set_links_filter_enabled(not getattr(self, "_links_filter_enabled", False))

    def _enable_links_filter(self, _text: str = ""):
        self._set_links_filter_enabled(True)

    def _set_links_filter_enabled(self, enabled: bool):
        self._links_filter_enabled = bool(enabled)
        self.links_tag.setProperty("active", self._links_filter_enabled)
        self.links_toggle.setText("☑ リンク：" if enabled else "☐ リンク：")
        font = self.links_edit.font()
        font.setStrikeOut(not enabled)
        self.links_edit.setFont(font)
        self.links_tag.style().unpolish(self.links_tag)
        self.links_tag.style().polish(self.links_tag)
        self.links_toggle.setToolTip(
            "クリックしてリンク条件を無効にします" if enabled
            else "クリックしてリンク条件を有効にします"
        )

    def _selected_links(self) -> int | None:
        if self.links_tag.isHidden() or not getattr(self, "_links_filter_enabled", False):
            return None
        text = self.links_edit.text().strip()
        return int(text) if text else None

    def _configure_influence_chips(self, item):
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        key = (item.raw_text, preset)
        if key == getattr(self, "_influence_item_key", None):
            return
        self._influence_item_key = key
        influences = [
            influence for influence, (_label, _stat_id, item_flag) in _INFLUENCE_CHIPS.items()
            if item_flag in item.flags
        ]
        visible = set(influences) if 1 <= len(influences) <= 2 else set()
        exact = preset == PRESET_BASE or uses_dedicated_exact_preset(item)
        for influence, button in self.influence_chips.items():
            button.setVisible(influence in visible)
            eldritch = influence in {"eater", "exarch"}
            self._set_influence_filter_enabled(
                influence, influence in visible and (exact or eldritch),
            )

    def _toggle_influence_filter(self, influence: str):
        self._set_influence_filter_enabled(
            influence, not self._influence_chip_enabled.get(influence, False),
        )

    def _set_influence_filter_enabled(self, influence: str, enabled: bool):
        self._influence_chip_enabled[influence] = bool(enabled)
        button = self.influence_chips[influence]
        label = _INFLUENCE_CHIPS[influence][0]
        button.setText(label)
        button.setIcon(_influence_chip_icon(label, bool(enabled)))
        button.setProperty("active", bool(enabled))
        button.style().unpolish(button)
        button.style().polish(button)

    def _selected_influence_filters(self) -> tuple[TradeStatFilter, ...]:
        rows = []
        for influence, enabled in self._influence_chip_enabled.items():
            if not enabled or self.influence_chips[influence].isHidden():
                continue
            label, stat_id, _item_flag = _INFLUENCE_CHIPS[influence]
            if stat_id is None:
                continue
            rows.append(TradeStatFilter(stat_id, f"{label}影響", None, "influence", True))
        return tuple(rows)

    def _selected_eldritch_influences(self) -> tuple[bool | None, bool | None]:
        """表示中のEldritchチップをTrade APIのmisc条件へ変換する。"""
        selected = []
        for influence in ("exarch", "eater"):
            button = self.influence_chips[influence]
            selected.append(
                None if button.isHidden()
                else bool(self._influence_chip_enabled.get(influence, False))
            )
        return tuple(selected)

    def _configure_special_filter_chips(self, item):
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        key = (item.raw_text, preset)
        if key == getattr(self, "_special_chip_item_key", None):
            return
        self._special_chip_item_key = key
        rows = self._resolved_trade_filters(item, preset)
        by_id = {row.stat_id: row for row in rows}
        self._special_chip_rows = by_id

        self.unidentified_chip.setVisible("unidentified" in item.flags)
        self.unidentified_chip.setCurrentIndex(
            0 if item.rarity.casefold() in {"unique", "ユニーク"} else 1
        )
        self.veiled_chip.setVisible("veiled" in item.flags)
        self.veiled_chip.setCurrentIndex(0)
        self.foil_chip.setVisible("foil" in item.flags)
        self.foil_chip.setCurrentIndex(0)

        self.gem_variant_chip.setVisible(item.category == "gem")
        if item.category == "gem":
            info = gem_metadata(self._trade_base_type or item.base_type)
            identity = f"{item.name} {item.base_type}".casefold()
            if info.get("transfigured"):
                variant = "変容ジェム"
            elif info.get("vaal") or "vaal " in identity or "ヴァール" in identity:
                variant = "ヴァールジェム"
            elif "awakened " in identity or "覚醒" in identity:
                variant = "覚醒ジェム"
            else:
                variant = "通常ジェム"
            self.gem_variant_chip.setText(f"Variant：{variant}")

        self._configure_logbook_areas(item)

        map_identity = " ".join(filter(None, (
            item.name, item.base_type, self._trade_base_type,
        ))).casefold()
        is_nightmare_map = (
            item.category == "map"
            and ("nightmare map" in map_identity or "ナイトメアマップ" in map_identity)
        )
        self.nightmare_map_chip.setVisible(is_nightmare_map)

        numeric = (
            (self.map_tier_chip, "property.map_tier", True),
            (self.base_percentile_chip, "property.base_percentile", False),
            (self.area_level_chip, "property.area_level", False),
            (self.heist_wings_chip, "property.heist_wings", False),
        )
        for chip, stat_id, exact in numeric:
            row = by_id.get(stat_id)
            chip.setVisible(row is not None and not (
                chip is self.map_tier_chip and is_nightmare_map
            ))
            if row is not None:
                # Map Tierは完全一致だが、同じ値を2欄へ重複表示しない。
                # 選択条件へ戻す段階でmin=maxに復元する。
                maximum = None if exact else row.max_value
                chip.setValues(row.min_value, maximum)
                chip.setActive(row.enabled)

        job = next((row for row in rows if row.stat_id.startswith("property.heist_")
                    and row.stat_id not in {
                        "property.heist_wings", "property.heist_objective_value",
                    }), None)
        self._heist_job_row = job
        self.heist_job_chip.setVisible(job is not None)
        if job is not None:
            self.heist_job_chip.setValues(job.min_value, job.max_value)
            self.heist_job_chip.setActive(job.enabled)
        target = by_id.get("property.heist_objective_value")
        self.heist_target_chip.setVisible(target is not None)
        self.heist_target_chip.setText(target.text if target else "")

        passive = next((row for row in rows if row.ref == "Adds # Passive Skills"), None)
        self._cluster_passive_row = passive
        self.cluster_passives_chip.setVisible(passive is not None)
        if passive is not None:
            self.cluster_passives_chip.setValues(passive.min_value, passive.max_value)
            self.cluster_passives_chip.setActive(passive.enabled)
        enchants = tuple(
            row for row in rows
            if row.kind == "enchant" and row.ref != "Adds # Passive Skills"
        )
        self._cluster_enchant_rows = enchants if item.category == "cluster_jewel" else ()
        self.cluster_enchant_chip.setVisible(bool(self._cluster_enchant_rows))
        self.cluster_enchant_chip.setText(
            "Enchant効果：" + " / ".join(row.text for row in self._cluster_enchant_rows)
            if self._cluster_enchant_rows else ""
        )
        socket_mod = next((mod for mod in item.modifiers
                           if mod.ref == "# Added Passive Skills are Jewel Sockets"), None)
        self.cluster_socket_chip.setVisible(socket_mod is not None)
        if socket_mod is not None:
            count = int(socket_mod.values[0]) if socket_mod.values else 0
            self.cluster_socket_chip.setText(f"ジュエルソケット：{count}")

        blight = by_id.get("property.map_uberblighted") or by_id.get("property.map_blighted")
        self.blighted_chip.setVisible(blight is not None)
        self.blighted_chip.setText(blight.text if blight else "")
        reward = by_id.get("property.map_completion_reward")
        if _is_valdo_map(item):
            reward = None
        self.completion_reward_chip.setVisible(reward is not None)
        self.completion_reward_chip.setText(reward.text if reward else "")

    def _selected_special_chip_filters(self) -> tuple[TradeStatFilter, ...]:
        rows = getattr(self, "_special_chip_rows", {})
        selected = []
        for chip, stat_id in (
            (self.map_tier_chip, "property.map_tier"),
            (self.base_percentile_chip, "property.base_percentile"),
            (self.area_level_chip, "property.area_level"),
            (self.heist_wings_chip, "property.heist_wings"),
        ):
            row = rows.get(stat_id)
            if row is None or chip.isHidden() or not chip.isActive():
                continue
            minimum, maximum = chip.values()
            if stat_id == "property.map_tier":
                maximum = minimum
            selected.append(replace(row, min_value=minimum, max_value=maximum, enabled=True))
        for stat_id in ("property.map_blighted", "property.map_uberblighted"):
            row = rows.get(stat_id)
            if row is not None:
                selected.append(replace(row, enabled=True))
        reward = rows.get("property.map_completion_reward")
        if reward is not None and not self.completion_reward_chip.isHidden():
            selected.append(replace(reward, enabled=True))
        job = getattr(self, "_heist_job_row", None)
        if job is not None and not self.heist_job_chip.isHidden() and self.heist_job_chip.isActive():
            minimum, maximum = self.heist_job_chip.values()
            selected.append(replace(job, min_value=minimum, max_value=maximum, enabled=True))
        target = rows.get("property.heist_objective_value")
        if target is not None and not self.heist_target_chip.isHidden():
            selected.append(replace(target, enabled=True))
        passive = getattr(self, "_cluster_passive_row", None)
        if passive is not None and not self.cluster_passives_chip.isHidden() \
                and self.cluster_passives_chip.isActive():
            minimum, maximum = self.cluster_passives_chip.values()
            selected.append(replace(passive, min_value=minimum, max_value=maximum, enabled=True))
        selected.extend(replace(row, enabled=True) for row in getattr(
            self, "_cluster_enchant_rows", (),
        ))
        return tuple(selected)

    def _configure_logbook_areas(self, item):
        if item.category != "expedition_logbook":
            self._logbook_area_groups = ()
            self.logbook_area_selector.setLabels(())
            self.logbook_area_container.hide()
            return
        groups = []
        for group in sorted({mod.group for mod in item.modifiers if mod.group is not None}):
            mods = tuple(mod for mod in item.modifiers if mod.group == group)
            if not mods:
                continue
            faction = next((mod.text for mod in mods if mod.stat_id and
                            mod.stat_id.startswith("pseudo.pseudo_logbook_faction_")), None)
            groups.append((group, faction or f"エリア{len(groups) + 1}"))
        self._logbook_area_groups = tuple(groups[:5])
        self.logbook_area_selector.setLabels(
            tuple(f"エリア{index + 1}：{label}" for index, (_group, label)
                  in enumerate(self._logbook_area_groups))
        )
        self.logbook_area_container.setVisible(bool(self._logbook_area_groups))

    def _logbook_area_changed(self, index):
        groups = getattr(self, "_logbook_area_groups", ())
        if not groups or index >= len(groups):
            return
        selected_group = groups[index][0]
        for row_index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(row_index)
            original = row.data(0, Qt.UserRole + 4)
            reason = original.selection_reason if isinstance(original, TradeStatFilter) else ""
            if reason.startswith("logbook-area:"):
                checkbox_container = self.mod_filter_tree.itemWidget(
                    row, _MOD_COLUMN_CHECK
                )
                checkbox = (
                    checkbox_container.findChild(QCheckBox, "modFilterCheckbox")
                    if checkbox_container is not None else None
                )
                enabled = reason == f"logbook-area:{selected_group}"
                if checkbox is not None:
                    checkbox.setChecked(enabled)
                row.setData(_MOD_COLUMN_CHECK, Qt.UserRole + 5, enabled)

    def _trade_preset_changed(self):
        if not hasattr(self, "mod_filter_tree"):
            return
        self.mod_filter_tree.clear()
        self.price_list.clear()
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        item = getattr(self, "_parsed_item", None)
        self._configure_magic_rarity_toggle(item)
        if item is not None:
            self._refresh_hidden_split_default(item)
            self._configure_item_level(item, force=True)
            self._configure_quality(item)
            self._configure_influence_chips(item)
            self._configure_special_filter_chips(item)
            self._populate_stat_filters(self._resolved_trade_filters(item, preset))
        if preset == PRESET_BASE:
            self.price_status.setText(
                "ベースアイテムとして、ベースタイプとアイテムレベルを中心に検索します。"
            )
        elif item is not None and uses_dedicated_exact_preset(item):
            self.price_status.setText(
                "アイテム種別に合わせた専用条件で検索します。"
            )
        else:
            self.price_status.setText("完成品として、実際の性能を中心に検索します。")

    def _reset_unique_candidates(self):
        while self.unique_name_layout.count():
            item = self.unique_name_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self.unique_name_group.removeButton(widget)
                widget.deleteLater()
        self.unique_name_container.hide()
        self.unique_name_scroll.hide()
        self.unique_name_label.hide()
        self.unique_variant_combo.clear()
        self.unique_variant_combo.hide()
        self.unique_variant_label.hide()

    def _show_unique_candidates(self, candidates):
        self.price_button.setEnabled(True)
        self._reset_unique_candidates()
        for candidate in candidates:
            name = str(getattr(candidate, "name", candidate))
            display_name = str(getattr(candidate, "display_name", None) or name)
            icon_url = getattr(candidate, "icon_url", None)
            button = QPushButton(display_name)
            button.setObjectName("uniqueCandidateButton")
            button.setCheckable(True)
            button.setProperty("uniqueName", name)
            button.setProperty("iconUrl", icon_url)
            button.setIconSize(QSize(48, 48))
            button.setMinimumSize(150, 64)
            button.setToolTip(
                display_name if display_name == name
                else f"{display_name}\n{name}"
            )
            button.setStyleSheet(
                "QPushButton#uniqueCandidateButton {"
                " text-align: left; padding: 6px; border: 1px solid #555; border-radius: 4px;"
                "}"
                "QPushButton#uniqueCandidateButton:hover { border-color: #49D6B0; }"
                "QPushButton#uniqueCandidateButton:checked {"
                " border: 2px solid #49D6B0; background: #183B34;"
                "}"
            )
            self.unique_name_group.addButton(button)
            self.unique_name_layout.addWidget(button)
            if icon_url:
                cached = self._unique_icon_cache.get(icon_url)
                if cached is not None:
                    button.setIcon(cached)
                else:
                    reply = self._unique_icon_manager.get(QNetworkRequest(QUrl(icon_url)))
                    self._unique_icon_requests[reply] = (button, icon_url)
        first_button = next(iter(self.unique_name_group.buttons()), None)
        if first_button is not None:
            first_button.setChecked(True)
        self.unique_name_label.show()
        self.unique_name_container.show()
        self.unique_name_scroll.show()
        self.price_status.setText(
            f"同じベースの未鑑定ユニークが{len(candidates)}種類あります。候補を選んで「価格を検索」を押してください。"
        )

    def _unique_icon_downloaded(self, reply: QNetworkReply):
        request = self._unique_icon_requests.pop(reply, None)
        try:
            if request is None or reply.error() != QNetworkReply.NoError:
                return
            button, icon_url = request
            pixmap = QPixmap()
            if not pixmap.loadFromData(reply.readAll()):
                return
            icon = QIcon(pixmap)
            self._unique_icon_cache[icon_url] = icon
            if (button in self.unique_name_group.buttons()
                    and button.property("iconUrl") == icon_url):
                button.setIcon(icon)
        finally:
            reply.deleteLater()

    def _show_unique_variants(self, variants):
        self.price_button.setEnabled(True)
        self.unique_variant_combo.clear()
        for label, discriminator in variants:
            self.unique_variant_combo.addItem(str(label), discriminator)
        self.unique_variant_label.show()
        self.unique_variant_combo.show()
        self.price_status.setText(
            f"同名ユニークに{len(variants)}種類のVariantがあります。候補を選んで再検索してください。"
        )

    def _selected_stat_filters(self) -> tuple[TradeStatFilter, ...]:
        filters = []
        for index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(index)
            checkbox_container = self.mod_filter_tree.itemWidget(
                row, _MOD_COLUMN_CHECK
            )
            checkbox = (
                checkbox_container.findChild(QCheckBox, "modFilterCheckbox")
                if checkbox_container is not None else None
            )
            enabled = (
                checkbox.isChecked() if checkbox is not None
                else bool(row.data(_MOD_COLUMN_CHECK, Qt.UserRole + 5))
            )
            editor = self.mod_filter_tree.itemWidget(row, _MOD_COLUMN_MIN)
            max_editor = self.mod_filter_tree.itemWidget(row, _MOD_COLUMN_MAX)
            value_text = (
                editor.text().strip() if isinstance(editor, QLineEdit)
                else row.text(_MOD_COLUMN_MIN).strip()
            )
            max_text = (
                max_editor.text().strip() if isinstance(max_editor, QLineEdit)
                else row.text(_MOD_COLUMN_MAX).strip()
            )
            try:
                value = float(value_text) if value_text else None
            except ValueError:
                value = None
            try:
                maximum = float(max_text) if max_text else None
            except ValueError:
                maximum = None
            original = row.data(0, Qt.UserRole + 4)
            if isinstance(original, TradeStatFilter):
                filters.append(replace(
                    original, min_value=value, max_value=maximum,
                    enabled=enabled,
                ))
            else:
                filters.append(TradeStatFilter(
                    row.data(0, Qt.UserRole), row.text(_MOD_COLUMN_TEXT), value,
                    row.text(_MOD_COLUMN_KIND),
                    enabled,
                    maximum, row.data(0, Qt.UserRole + 1), row.data(0, Qt.UserRole + 2) or 0.0,
                    bool(row.data(0, Qt.UserRole + 3)),
                ))
        return tuple(filters)

    def _populate_stat_filters(self, filters: tuple[TradeStatFilter, ...]):
        self.mod_filter_tree.clear()
        has_mercenary_supports = any(
            stat_filter.stat_id.startswith("mercenary.support")
            for stat_filter in filters
        )
        self.mercenary_supports_toggle.setChecked(False)
        self.mercenary_supports_toggle.setVisible(has_mercenary_supports)
        for stat_filter in filters:
            if stat_filter.stat_id in {"property.item_level", "property.gem_level"}:
                continue
            if (stat_filter.stat_id == "property.quality"
                    and getattr(self, "_parsed_item", None) is not None
                    and self._parsed_item.category in {
                        "gem", "weapon", "armour", "accessory", "flask", "tincture",
                    }):
                continue
            if stat_filter.stat_id == "property.links" and not self.links_tag.isHidden():
                continue
            if stat_filter.stat_id == "property.sockets":
                continue
            if stat_filter.kind == "influence":
                continue
            if stat_filter.stat_id in {
                "property.map_tier", "property.area_level", "property.heist_wings",
                "property.base_percentile",
                "property.map_blighted", "property.map_uberblighted",
                "property.map_completion_reward",
            }:
                continue
            if stat_filter.stat_id == "property.heist_objective_value" or (
                stat_filter.stat_id.startswith("property.heist_")
                and stat_filter.stat_id != "property.heist_wings"
            ):
                continue
            if stat_filter.ref == "Adds # Passive Skills" or (
                getattr(self, "_parsed_item", None) is not None
                and self._parsed_item.category == "cluster_jewel"
                and stat_filter.kind == "enchant"
            ):
                continue
            value = "" if stat_filter.min_value is None else f"{stat_filter.min_value:g}"
            maximum = "" if stat_filter.max_value is None else f"{stat_filter.max_value:g}"
            # The tooltip exists only to reveal text truncated by the compact
            # condition column. Internal matching and selection diagnostics do
            # not help normal price-search operation and make it harder to scan.
            mod_tooltip = stat_filter.text
            tier_tags = stat_filter.tier_tags
            tier_text = " / ".join(f"T{tier}" for tier in tier_tags)
            if not tier_text and stat_filter.tier is not None:
                tier_text = f"T{stat_filter.tier}"
            row = QTreeWidgetItem([
                "", _filter_kind_label(stat_filter),
                "" if tier_tags else tier_text,
                stat_filter.text, "", "",
            ])
            row.setData(0, Qt.UserRole, stat_filter.stat_id)
            row.setData(0, Qt.UserRole + 1, stat_filter.ref)
            row.setData(0, Qt.UserRole + 2, stat_filter.confidence)
            row.setData(0, Qt.UserRole + 3, stat_filter.inverted)
            row.setData(0, Qt.UserRole + 4, stat_filter)
            row.setData(0, Qt.UserRole + 5, stat_filter.enabled)
            row.setToolTip(_MOD_COLUMN_TEXT, mod_tooltip)
            row.setSizeHint(
                _MOD_COLUMN_TEXT,
                QSize(0, self._scaled_display_value(_MOD_ROW_HEIGHT)),
            )
            self.mod_filter_tree.addTopLevelItem(row)
            if stat_filter.source_texts:
                source_item = QTreeWidgetItem(row)
                source_item.setFirstColumnSpanned(True)
                source_widget = QWidget()
                source_widget.setObjectName("modSourceDetails")
                source_layout = QVBoxLayout(source_widget)
                source_layout.setContentsMargins(12, 6, 12, 8)
                source_layout.setSpacing(2)
                source_widget.setStyleSheet(
                    "QWidget#modSourceDetails {"
                    " color: #B8C2BE;"
                    " background: rgba(31, 23, 34, 220);"
                    " border-left: 2px solid rgba(73, 214, 176, 90);"
                    "}"
                )
                for source_index, source_text in enumerate(stat_filter.source_texts):
                    heading = QLabel(
                        stat_filter.source_headings[source_index]
                        if source_index < len(stat_filter.source_headings)
                        else "元Mod"
                    )
                    heading.setStyleSheet(
                        "color: #7F8A86; font-style: italic;"
                    )
                    source_layout.addWidget(heading)
                    source_label = QLabel(source_text)
                    source_label.setWordWrap(True)
                    source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    source_layout.addWidget(source_label)
                source_widget.setSizePolicy(
                    QSizePolicy.Expanding, QSizePolicy.Preferred
                )
                source_item.setSizeHint(
                    0, QSize(0, 12 + 42 * len(stat_filter.source_texts))
                )
                self.mod_filter_tree.setItemWidget(source_item, 0, source_widget)
                row.setExpanded(self.mod_sources_toggle.isChecked())
            row.setHidden(
                bool(stat_filter.hidden_reason) != self.hidden_mods_toggle.isChecked()
                or self._mercenary_support_row_is_hidden(row)
            )
            checkbox = QCheckBox()
            checkbox.setObjectName("modFilterCheckbox")
            checkbox.setToolTip("この条件を価格検索に使用する")
            Styles.apply_checkbox_style(checkbox)
            checkbox.setChecked(stat_filter.enabled)
            checkbox.stateChanged.connect(self._mark_search_dirty)
            checkbox.stateChanged.connect(self._update_all_mod_conditions_button)
            checkbox.stateChanged.connect(
                lambda _state, row=row: self._toggle_hidden_mods(
                    self.hidden_mods_toggle.isChecked()
                )
            )
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(5, 0, 5, 0)
            checkbox_layout.addWidget(checkbox)
            self.mod_filter_tree.setItemWidget(
                row, _MOD_COLUMN_CHECK, checkbox_container
            )
            if tier_tags:
                tier_widget = QWidget()
                tier_layout = QHBoxLayout(tier_widget)
                tier_layout.setContentsMargins(2, 0, 2, 0)
                tier_layout.setSpacing(3)
                for tier in tier_tags:
                    tag = QLabel(f"T{tier}")
                    tag.setAlignment(Qt.AlignCenter)
                    if tier == 1:
                        tag.setStyleSheet(
                            "background: #D8C47A; color: #292416; border-radius: 3px;"
                            " padding: 1px 4px; font-weight: 600;"
                        )
                    else:
                        tag.setStyleSheet(
                            "color: #CDBB78; border: 1px solid #9F9162; border-radius: 3px;"
                            " padding: 0px 3px; font-weight: 600;"
                        )
                    tier_layout.addWidget(tag)
                tier_layout.addStretch(1)
                self.mod_filter_tree.setItemWidget(row, _MOD_COLUMN_TIER, tier_widget)
            editor = QLineEdit(value)
            editor.installEventFilter(self)
            editor.setPlaceholderText("最小")
            self._apply_mod_value_editor_size(editor, leading_gap=True)
            editor.setEnabled(stat_filter.option_value is None)
            editor.textEdited.connect(self._mark_search_dirty)
            self.mod_filter_tree.setItemWidget(row, _MOD_COLUMN_MIN, editor)
            max_editor = QLineEdit(maximum)
            max_editor.installEventFilter(self)
            max_editor.setPlaceholderText("最大")
            self._apply_mod_value_editor_size(max_editor)
            max_editor.setEnabled(stat_filter.option_value is None)
            max_editor.textEdited.connect(self._mark_search_dirty)
            self.mod_filter_tree.setItemWidget(row, _MOD_COLUMN_MAX, max_editor)
            parsed_item = getattr(self, "_parsed_item", None)
            show_unique_slider = (
                parsed_item is not None
                and parsed_item.rarity.casefold() in {"unique", "ユニーク"}
                and stat_filter.roll_min is not None
                and stat_filter.roll_max is not None
                and stat_filter.roll_min < stat_filter.roll_max
                and stat_filter.read_value is not None
                and stat_filter.better in {-1, 1}
                and stat_filter.option_value is None
                and not stat_filter.exact
            )
            if show_unique_slider:
                text_widget = QWidget()
                text_widget.setObjectName("uniqueRollCell")
                # QTreeWidget requires an opaque cell widget; otherwise the native
                # item text is painted through it and appears as a duplicate.
                text_widget.setAutoFillBackground(True)
                text_palette = text_widget.palette()
                text_palette.setColor(QPalette.Window, QColor("#121212"))
                text_widget.setPalette(text_palette)
                text_widget.setStyleSheet(
                    "QWidget#uniqueRollCell { background-color: #121212; }"
                    "QWidget#uniqueRollCell QLabel {"
                    " background-color: #121212; color: #d8ded4;"
                    "}"
                )
                text_layout = QVBoxLayout(text_widget)
                text_layout.setContentsMargins(2, 3, 2, 3)
                text_layout.setSpacing(3)
                text_label = QLabel(stat_filter.text)
                text_label.setToolTip(mod_tooltip)
                text_label.setCursor(Qt.PointingHandCursor)
                text_label._mod_condition_checkbox = checkbox
                text_label.installEventFilter(self)
                text_layout.addWidget(text_label)
                slider = _UniqueRollSlider(
                    (stat_filter.roll_min, stat_filter.roll_max),
                    stat_filter.read_value,
                    stat_filter.better,
                    stat_filter.decimal,
                )
                slider.setObjectName("uniqueRollSlider")
                slider.setSearchValues(stat_filter.min_value, stat_filter.max_value)
                text_layout.addWidget(slider)
                self.mod_filter_tree.setItemWidget(row, _MOD_COLUMN_TEXT, text_widget)
                row.setSizeHint(
                    _MOD_COLUMN_TEXT,
                    QSize(0, self._scaled_display_value(_UNIQUE_ROLL_ROW_HEIGHT))
                )

                def sync_slider(
                    _text="",
                    *,
                    roll_slider=slider,
                    minimum_editor=editor,
                    maximum_editor=max_editor,
                ):
                    def number(text: str) -> float | None:
                        try:
                            return float(text) if text.strip() else None
                        except ValueError:
                            return None
                    roll_slider.setSearchValues(
                        number(minimum_editor.text()),
                        number(maximum_editor.text()),
                    )

                def commit_slider(
                    minimum,
                    maximum,
                    *,
                    minimum_editor=editor,
                    maximum_editor=max_editor,
                    condition_checkbox=checkbox,
                ):
                    minimum_editor.setText("" if minimum is None else f"{minimum:g}")
                    maximum_editor.setText("" if maximum is None else f"{maximum:g}")
                    condition_checkbox.setChecked(True)
                    self._mark_search_dirty()

                editor.textChanged.connect(sync_slider)
                max_editor.textChanged.connect(sync_slider)
                slider.valueCommitted.connect(commit_slider)
        self._update_all_mod_conditions_button()
        self._adjust_window_height_to_mod_rows()

    def _search_completed(self, result: PriceResult, initial_filters, search_generation: int):
        trace = self._search_performance_traces.pop(search_generation, None)
        if search_generation != self._search_generation:
            if trace is not None:
                trace.mark("stale_search_result_discarded")
            return
        if initial_filters:
            self._populate_stat_filters(initial_filters)
        self._show_price_result(result)
        if trace is not None:
            trace.mark(
                "trade_result_displayed",
                listings=len(result.listings),
                candidates=result.total,
                cached=result.cached,
            )

    def _search_partially_completed(self, result: PriceResult, search_generation: int):
        if search_generation != self._search_generation:
            return
        self._show_price_result(result, partial=True)
        trace = self._search_performance_traces.get(search_generation)
        if trace is not None:
            trace.mark(
                "trade_partial_result_displayed", listings=len(result.listings),
            )

    def _show_price_result(self, result: PriceResult, partial: bool = False):
        if not partial:
            self.price_button.setEnabled(True)
            self._last_trade_url = result.web_url
            self.trade_url_button.setEnabled(bool(result.web_url))
        self.price_list.clear()
        cache_note = " / キャッシュ" if result.cached else ""
        if not result.listings:
            self.price_status.setText(
                f"{result.league}: 検索候補{result.total}件{cache_note}。"
                "価格付き出品は取得できませんでした。"
            )
            return
        progress_note = "取得中 / " if partial else ""
        self.price_status.setText(
            f"{result.league}: {progress_note}候補{result.total}件 / "
            f"取得{len(result.listings)}件{cache_note}"
        )
        item = getattr(self, "_parsed_item", None)
        show_stock = any(row.stack_size is not None for row in result.listings)
        # 検索条件が初期OFFでも、参照アイテムと出品のilvl比較には価値がある。
        show_ilvl = (
            item is not None and item.category != "gem"
            and not self.item_level_tag.isHidden()
        )
        show_gem = item is not None and item.category == "gem"
        show_quality = show_gem or (
            item is not None and item.category != "gem" and self._selected_quality() is not None
        )
        columns = ["価格"]
        if show_stock:
            columns.append("在庫")
        if show_ilvl:
            columns.append("ilvl")
        if show_gem:
            columns.append("ジェムLv")
        if show_quality:
            columns.append("品質")
        columns.extend(("出品日時", "取引方式"))
        # QTreeWidget#setHeaderLabels()は既存より列数が少ない場合に、
        # 余った末尾列を削除しない。Gem→武器などで固有列が減る時は
        # 先に列数を確定し、前カテゴリのヘッダーを残さない。
        self.price_list.setColumnCount(len(columns))
        self.price_list.setHeaderLabels(columns)
        header = self.price_list.header()
        for column in range(len(columns)):
            header.setSectionResizeMode(
                column,
                QHeaderView.Stretch
                if column == len(columns) - 1
                else QHeaderView.ResizeToContents,
            )

        for listing in result.listings:
            price_text = (
                "値段なし"
                if listing.pricing_method == "unpriced"
                else f"{listing.amount:g} {listing.currency}"
            )
            if listing.listed_times > 1:
                price_text += f" ×{listing.listed_times}"
            values = [price_text]
            if show_stock:
                values.append(str(listing.stack_size) if listing.stack_size is not None else "-")
            if show_ilvl:
                values.append(str(listing.item_level) if listing.item_level is not None else "-")
            if show_gem:
                values.append(str(listing.gem_level) if listing.gem_level is not None else "-")
            if show_quality:
                values.append(str(listing.quality) if listing.quality is not None else "-")
            values.append(self._relative_listing_time(listing.indexed))
            values.append({
                "instant": "インスタント",
                "unpriced": "値段なし",
            }.get(listing.pricing_method, "対面"))
            QTreeWidgetItem(self.price_list, values)

    @staticmethod
    def _relative_listing_time(indexed: str, now: datetime | None = None) -> str:
        if not indexed:
            return "-"
        try:
            timestamp = datetime.fromisoformat(indexed.replace("Z", "+00:00"))
        except ValueError:
            return "-"
        current = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        seconds = max(0, int((current.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()))
        if seconds < 60:
            return "たった今"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}分前"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}時間前"
        days = hours // 24
        if days < 30:
            return f"{days}日前"
        months = days // 30
        if months < 12:
            return f"{months}か月前"
        return f"{days // 365}年前"

    def _show_price_error(self, message: str, search_generation: int):
        trace = self._search_performance_traces.pop(search_generation, None)
        if search_generation != self._search_generation:
            if trace is not None:
                trace.mark("stale_search_error_discarded")
            return
        self.price_button.setEnabled(True)
        self.price_list.clear()
        self.price_status.setText(message)
        if trace is not None:
            trace.mark("search_error_displayed")

    def _open_trade_url(self):
        if self._last_trade_url:
            QDesktopServices.openUrl(QUrl(self._last_trade_url))


def prepare_poetore_window(owner):
    """Create the reusable poetore window without showing it or making API calls."""
    window = getattr(owner, "_poetore_window", None)
    if window is None:
        # QWidgetの親子関係を持たせると、本体のdisabled/入力透過状態が
        # 別ウィンドウへ波及し得る。寿命はownerの参照で管理し、UIは独立させる。
        from src.utils.config_manager import ConfigManager

        app_config = getattr(owner, "config", None)
        window = PoetoreWindow(
            app_config=app_config,
            save_config=ConfigManager.save_config if isinstance(app_config, dict) else None,
        )
        owner._poetore_window = window
    return window


def show_poetore_window(owner, activate=True):
    """ownerが参照を保持し、二重起動せず独立表示できる公開エントリ。"""
    window = prepare_poetore_window(owner)
    if isinstance(getattr(owner, "config", None), dict):
        window.apply_result_display_size()
        window.refresh_trade_leagues()
    if activate:
        window.show_at_context()
    return window
