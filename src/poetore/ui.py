from __future__ import annotations

import threading
import re
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QIcon, QIntValidator, QPainter, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QLayout,
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSizeGrip, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit, QHeaderView,
)

from .parser import ItemParseError, parse_item_text
from .clipboard import read_item_clipboard
from .merge import merge_normal_and_detailed_copy
from .window_position import PlacementContext, capture_placement_context, position_for_context
from .trade import (
    PRESET_BASE, PRESET_FINISHED, PriceResult, TradeApiError, TradeStatFilter,
    available_pc_leagues, available_trade_presets, default_pc_league, default_trade_currency,
    gem_metadata,
    resolve_trade_stat_filters, search_prices, unique_candidates,
    unique_variants, unresolved_modifier_warnings, uses_dedicated_exact_preset,
)
from .poe_ninja import PoeNinjaPrice, default_poe_ninja_service


class _TradeSignals(QObject):
    completed = Signal(object, object)
    failed = Signal(str)
    unique_candidates_ready = Signal(object)
    unique_variants_ready = Signal(object)
    leagues_ready = Signal(object)
    poe_ninja_ready = Signal(object, object)
    poe_ninja_failed = Signal(object)


_INFLUENCE_CHIPS = {
    "shaper": ("Shaper", "pseudo.pseudo_has_shaper_influence"),
    "elder": ("Elder", "pseudo.pseudo_has_elder_influence"),
    "crusader": ("Crusader", "pseudo.pseudo_has_crusader_influence"),
    "hunter": ("Hunter", "pseudo.pseudo_has_hunter_influence"),
    "redeemer": ("Redeemer", "pseudo.pseudo_has_redeemer_influence"),
    "warlord": ("Warlord", "pseudo.pseudo_has_warlord_influence"),
}


def _influence_chip_icon(label: str, active: bool) -> QIcon:
    """チェック、Influence画像の順で1つのボタンアイコンへ合成する。"""
    result = QPixmap(38, 20)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#f4ffed" if active else "#687064"))
    painter.drawText(QRect(0, 0, 16, 20), Qt.AlignCenter, "☑" if active else "☐")
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "icons" / f"{label}.png"
    influence = QPixmap(str(icon_path))
    if not influence.isNull():
        painter.drawPixmap(18, 0, 20, 20, influence)
    painter.end()
    return QIcon(result)


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
            button.clicked.connect(lambda checked=False, value=index: self.setCurrentIndex(value))
            layout.addWidget(button)
            self._buttons.append(button)
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


class _NumericFilterChip(QFrame):
    """ON/OFFと最小値（必要なら最大値）を持つ共通検索チップ。"""

    def __init__(self, label: str, minimum: int, maximum: int, parent=None):
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
        painter.setPen(QPen(QColor("#53604f"), 1, Qt.DashLine))
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
        color = "#79d65b" if self._points[-1] >= self._points[0] else "#ff6b6b"
        painter.setPen(QPen(QColor(color), 1.5))
        painter.drawPolyline(polygon)


class _PoetoreTitleBar(QWidget):
    """Small draggable title bar for the frameless price-check panel."""

    def __init__(self, window: "PoetoreWindow"):
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        title = QLabel("ぽえとれ")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        layout.addStretch()
        close_button = QPushButton("×")
        close_button.setToolTip("閉じる")
        close_button.setFixedSize(28, 24)
        close_button.clicked.connect(window.close)
        layout.addWidget(close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
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
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class PoetoreWindow(QWidget):
    """貼り付け解析だけを行う、Trade API未接続のローカル試作画面。"""

    def __init__(self, parent=None, app_config=None, save_config=None):
        super().__init__(parent)
        self._app_config = app_config if isinstance(app_config, dict) else {}
        self._save_app_config = save_config
        self._league_refresh_started = False
        self._auto_league: str | None = None
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # PoENavi本体には入力透過（クリックスルー）機能があるため、
        # ぽえとれ側では常にマウス入力を受け取れる状態を明示する。
        self.setWindowFlag(Qt.WindowTransparentForInput, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setEnabled(True)
        self.setWindowTitle("ぽえとれ")
        self.resize(720, 860)
        self.setMinimumSize(680, 620)
        self._placement_context: PlacementContext | None = None
        self._focus_signal_connected = False
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
        self.poe_ninja_trend_label = QLabel("")
        self.poe_ninja_trend_label.setObjectName("poeNinjaTrendLabel")
        self.poe_ninja_trend_chart = _SparklineWidget()
        # 旧テスト・後続実装から差し込み口を参照できる別名。
        self.poe_ninja_trend_placeholder = self.poe_ninja_trend_chart
        self.poe_ninja_open_button = QPushButton("poe.ninja  ↗")
        self.poe_ninja_open_button.setObjectName("poeNinjaOpenButton")
        self.poe_ninja_open_button.clicked.connect(self._open_poe_ninja_url)
        ninja_layout.addWidget(self.poe_ninja_price_label)
        ninja_layout.addWidget(self.poe_ninja_price_value)
        ninja_layout.addStretch()
        ninja_layout.addWidget(self.poe_ninja_trend_label)
        ninja_layout.addWidget(self.poe_ninja_trend_chart)
        ninja_layout.addWidget(self.poe_ninja_open_button)
        self.poe_ninja_price_panel.hide()
        panel_layout.addWidget(self.poe_ninja_price_panel)

        top_options = QHBoxLayout()
        top_options.setSpacing(6)
        self.trade_league_combo = QComboBox()
        self.trade_league_combo.setEditable(True)
        self.trade_league_combo.setMinimumContentsLength(12)
        self.trade_league_combo.setToolTip("一覧から選択、またはPrivate League IDを直接入力")
        self.trade_league_combo.addItem("自動（現行SCを取得中）", "auto")
        saved_league = str(self._app_config.get("poetore", {}).get("league", "auto"))
        if saved_league != "auto":
            self.trade_league_combo.addItem(saved_league, saved_league)
            self.trade_league_combo.setCurrentIndex(1)
        self.trade_league_combo.currentIndexChanged.connect(self._persist_trade_league)
        self.trade_league_combo.lineEdit().editingFinished.connect(self._persist_trade_league)
        top_options.addWidget(self.trade_league_combo, stretch=2)
        self.trade_preset_combo = _BinaryToggle(
            ("完成品", PRESET_FINISHED), ("クラフトベース", PRESET_BASE),
        )
        self.trade_preset_combo.currentIndexChanged.connect(self._trade_preset_changed)
        top_options.addWidget(self.trade_preset_combo, stretch=1)
        self.magic_rarity_toggle = _BinaryToggle(
            ("ユニーク以外", False), ("マジック完全一致", True),
        )
        self.magic_rarity_toggle.setToolTip(
            "マジックのクラフトベースだけに絞る場合は「マジック完全一致」を選択"
        )
        self.magic_rarity_toggle.hide()

        self.trade_status_combo = QComboBox()
        self.trade_status_combo.addItem("インスタントバイアウトのみ", "instant")
        self.trade_status_combo.addItem("インスタント＋対面", "available")
        self.trade_status_combo.addItem("対面トレードのみ", "online")
        self.trade_status_combo.addItem("オフライン出品も含む", "offline")
        self.trade_currency_combo = QComboBox()
        self.trade_currency_combo.addItem("すべての通貨", "any")
        self.trade_currency_combo.addItem("カオスオーブのみ", "chaos")
        self.trade_currency_combo.addItem("ディヴァインオーブのみ", "divine")
        self.trade_currency_combo.addItem("カオス＋ディヴァイン", "chaos_divine")
        self.listed_within_combo = QComboBox()
        for label, value in (
            ("期間指定なし", "any"), ("24時間以内", "1day"), ("3日以内", "3days"),
            ("1週間以内", "1week"), ("2週間以内", "2weeks"),
            ("1か月以内", "1month"), ("2か月以内", "2months"),
        ):
            self.listed_within_combo.addItem(label, value)

        unique_options = QHBoxLayout()
        self.unique_name_label = QLabel("未鑑定ユニーク候補:")
        self.unique_name_combo = QComboBox()
        self.unique_name_label.hide()
        self.unique_name_combo.hide()
        unique_options.addWidget(self.unique_name_label)
        unique_options.addWidget(self.unique_name_combo)
        self.unique_variant_label = QLabel("ユニークVariant:")
        self.unique_variant_combo = QComboBox()
        self.unique_variant_label.hide()
        self.unique_variant_combo.hide()
        unique_options.addWidget(self.unique_variant_label)
        unique_options.addWidget(self.unique_variant_combo)
        unique_options.addStretch()
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
        for influence, (label, _stat_id) in _INFLUENCE_CHIPS.items():
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
        self.area_level_chip = _NumericFilterChip("Area Lv", 1, 100)
        self.heist_wings_chip = _NumericFilterChip("公開Wing", 1, 4)
        for chip in (self.map_tier_chip, self.area_level_chip, self.heist_wings_chip):
            chip.hide()
        self.blighted_chip = QPushButton()
        self.blighted_chip.setObjectName("readonlyFilterChip")
        self.blighted_chip.hide()
        self.completion_reward_chip = QPushButton()
        self.completion_reward_chip.setObjectName("readonlyFilterChip")
        self.completion_reward_chip.hide()
        self.split_combo = _CycleButton(
            (("スプリット", True, False), ("非スプリット", False, False)),
        )
        self.split_combo.hide()
        self.mirrored_combo = _CycleButton(
            (("ミラー化", True, False), ("非ミラー化", False, False)),
        )
        self.mirrored_combo.hide()
        self._filter_chips = (
            ("links", self.links_tag),
            ("map_tier", self.map_tier_chip),
            ("completion_reward", self.completion_reward_chip),
            ("area_level", self.area_level_chip),
            ("heist_wings", self.heist_wings_chip),
            ("blighted", self.blighted_chip),
            ("item_level", self.item_level_tag),
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

        self.weapon_property_label = QLabel("武器性能・検索Mod")
        self.weapon_property_label.setObjectName("sectionTitle")
        panel_layout.addWidget(self.weapon_property_label)

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
        self.mod_filter_tree.setHeaderLabels(["", "種別", "検索条件", "最小", "最大", "詳細", "論理"])
        self.mod_filter_tree.setRootIsDecorated(False)
        self.mod_filter_tree.setAlternatingRowColors(True)
        self.mod_filter_tree.setMinimumHeight(230)
        mod_header = self.mod_filter_tree.header()
        mod_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(2, QHeaderView.Stretch)
        mod_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(5, QHeaderView.Stretch)
        mod_header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        panel_layout.addWidget(self.mod_filter_tree, stretch=3)
        self.mod_warning = QLabel("")
        self.mod_warning.setWordWrap(True)
        self.mod_warning.setStyleSheet("color: #d6a84b;")
        self.mod_warning.hide()
        panel_layout.addWidget(self.mod_warning)

        action_row = QHBoxLayout()
        self.price_button = QPushButton("検索")
        self.price_button.setObjectName("primaryButton")
        self.price_button.clicked.connect(self.search_current_item)
        action_row.addWidget(self.price_button)
        action_row.addWidget(self.trade_status_combo, stretch=2)
        action_row.addWidget(self.trade_currency_combo, stretch=2)
        action_row.addWidget(self.listed_within_combo, stretch=1)
        self.trade_url_button = QPushButton("公式トレード  ↗")
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
        self.price_list.setHeaderLabels(["#", "価格", "アイテム", "出品者"])
        self.price_list.setRootIsDecorated(False)
        self.price_list.setAlternatingRowColors(True)
        self.price_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.price_list.setMinimumHeight(150)
        price_header = self.price_list.header()
        price_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        price_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        price_header.setSectionResizeMode(2, QHeaderView.Stretch)
        price_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        panel_layout.addWidget(self.price_list, stretch=2)
        resize_row = QHBoxLayout()
        resize_row.addStretch()
        resize_row.addWidget(QSizeGrip(self))
        panel_layout.addLayout(resize_row)
        self._apply_poetore_style()
        self._trade_signals = _TradeSignals(self)
        self._trade_signals.completed.connect(self._search_completed)
        self._trade_signals.failed.connect(self._show_price_error)
        self._trade_signals.unique_candidates_ready.connect(self._show_unique_candidates)
        self._trade_signals.unique_variants_ready.connect(self._show_unique_variants)
        self._trade_signals.leagues_ready.connect(self._show_trade_leagues)
        self._trade_signals.poe_ninja_ready.connect(self._show_poe_ninja_price)
        self._trade_signals.poe_ninja_failed.connect(self._hide_poe_ninja_price)
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
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def _apply_poetore_style(self):
        """Awakenedの情報密度を、ぽえなびの黒＋黄緑テーマで表現する。"""
        self.setStyleSheet("""
            QWidget {
                color: #b0ff7b;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
            }
            QFrame#poetorePanel {
                background: rgba(14, 14, 14, 246);
                border: 1px solid rgba(176, 255, 123, 120);
                border-radius: 5px;
            }
            QFrame#itemHeader {
                background: rgba(5, 5, 5, 205);
                border: 1px solid rgba(176, 255, 123, 80);
                border-radius: 4px;
            }
            QFrame#poeNinjaPricePanel {
                background: rgba(22, 28, 20, 205);
                border: 1px solid rgba(176, 255, 123, 65);
                border-radius: 4px;
            }
            QLabel#poeNinjaPriceLabel { color: #91b87a; font-weight: 700; }
            QLabel#poeNinjaPriceValue { color: #f4ffed; font-size: 14px; font-weight: 700; }
            QLabel#poeNinjaTrendLabel { color: #91b87a; font-size: 10px; }
            QPushButton#poeNinjaOpenButton { padding: 3px 7px; }
            QLabel#itemName {
                color: #d8ffbd;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#itemBase { color: #91b87a; font-size: 11px; }
            QLabel#sectionTitle {
                color: #b0ff7b;
                font-weight: 700;
                border-bottom: 1px solid rgba(176, 255, 123, 70);
                padding: 4px 2px;
            }
            QLabel#priceStatus { color: #aab2a5; padding: 1px 2px; }
            QPushButton {
                background: rgba(26, 26, 26, 225);
                color: #b0ff7b;
                border: 1px solid rgba(176, 255, 123, 150);
                border-radius: 3px;
                padding: 5px 9px;
            }
            QPushButton:hover { background: rgba(55, 72, 46, 230); border-color: #d8ffbd; }
            QPushButton:pressed { background: #111; }
            QPushButton:disabled { color: #52604c; border-color: #394136; }
            QPushButton#binaryToggle {
                border-radius: 0;
                padding: 4px 7px;
            }
            QPushButton#binaryToggle:first-child { border-radius: 3px 0 0 3px; }
            QPushButton#binaryToggle:last-child { border-radius: 0 3px 3px 0; }
            QPushButton#binaryToggle:checked {
                background: rgba(93, 145, 66, 225);
                color: #f4ffed;
                border-color: #d8ffbd;
                font-weight: 700;
            }
            QPushButton#cycleToggle {
                background: rgba(26, 26, 26, 225);
                color: #f4ffed;
                min-width: 112px;
                font-weight: 700;
            }
            QPushButton#cycleToggle[alert="true"] { color: #ff5757; }
            QPushButton#influenceChip {
                background: rgba(20, 20, 20, 180);
                color: #687064;
                border: 1px dashed rgba(145, 155, 140, 150);
                padding: 3px 7px;
                font-weight: 700;
            }
            QPushButton#influenceChip[active="true"] {
                background: rgba(70, 105, 52, 210);
                color: #f4ffed;
                border: 1px solid #b0ff7b;
            }
            QFrame#numericFilterTag {
                background: rgba(70, 105, 52, 210);
                border: 1px solid #b0ff7b;
                border-radius: 3px;
            }
            QFrame#numericFilterTag[active="false"] {
                background: rgba(20, 20, 20, 180);
                border: 1px dashed rgba(145, 155, 140, 150);
            }
            QPushButton#numericFilterToggle, QLineEdit#numericFilterEdit {
                background: transparent;
                color: #f4ffed;
                border: none;
                padding: 0;
                font-weight: 700;
            }
            QFrame#numericFilterTag[active="false"] QPushButton,
            QFrame#numericFilterTag[active="false"] QLineEdit,
            QFrame#numericFilterTag[active="false"] QLabel { color: #687064; }
            QPushButton#readonlyFilterChip {
                background: rgba(70, 105, 52, 210);
                color: #f4ffed;
                border: 1px solid #b0ff7b;
                padding: 3px 7px;
                font-weight: 700;
            }
            QFrame#itemLevelTag {
                background: rgba(70, 105, 52, 210);
                border: 1px solid #b0ff7b;
                border-radius: 3px;
            }
            QFrame#gemLevelTag {
                background: rgba(70, 105, 52, 210);
                border: 1px solid #b0ff7b;
                border-radius: 3px;
            }
            QFrame#gemQualityTag {
                background: rgba(70, 105, 52, 210);
                border: 1px solid #b0ff7b;
                border-radius: 3px;
            }
            QFrame#linksTag {
                background: rgba(70, 105, 52, 210);
                border: 1px solid #b0ff7b;
                border-radius: 3px;
            }
            QFrame#itemLevelTag QLabel {
                color: #f4ffed;
                font-weight: 700;
            }
            QPushButton#itemLevelToggle, QPushButton#gemLevelToggle, QPushButton#gemQualityToggle, QPushButton#linksToggle {
                background: transparent;
                color: #f4ffed;
                border: none;
                padding: 0;
                font-weight: 700;
            }
            QLineEdit#itemLevelEdit, QLineEdit#itemLevelMaxEdit, QLineEdit#gemLevelEdit, QLineEdit#gemQualityEdit, QLineEdit#linksEdit {
                background: transparent;
                color: #f4ffed;
                border: none;
                padding: 0;
                min-height: 20px;
                font-weight: 700;
            }
            QLineEdit#itemLevelEdit:focus, QLineEdit#itemLevelMaxEdit:focus, QLineEdit#gemLevelEdit:focus, QLineEdit#gemQualityEdit:focus, QLineEdit#linksEdit:focus {
                border: none;
                color: #d8ffbd;
            }
            QFrame#itemLevelTag[active="false"] {
                border: 1px dashed rgba(145, 155, 140, 150);
                background: rgba(20, 20, 20, 180);
            }
            QFrame#gemLevelTag[active="false"] {
                border: 1px dashed rgba(145, 155, 140, 150);
                background: rgba(20, 20, 20, 180);
            }
            QFrame#gemQualityTag[active="false"] {
                border: 1px dashed rgba(145, 155, 140, 150);
                background: rgba(20, 20, 20, 180);
            }
            QFrame#linksTag[active="false"] {
                border: 1px dashed rgba(145, 155, 140, 150);
                background: rgba(20, 20, 20, 180);
            }
            QFrame#itemLevelTag[active="false"] QPushButton,
            QFrame#itemLevelTag[active="false"] QLineEdit,
            QFrame#itemLevelTag[active="false"] QLabel {
                color: #687064;
            }
            QFrame#gemLevelTag[active="false"] QPushButton,
            QFrame#gemLevelTag[active="false"] QLineEdit {
                color: #687064;
            }
            QFrame#gemQualityTag[active="false"] QPushButton,
            QFrame#gemQualityTag[active="false"] QLineEdit {
                color: #687064;
            }
            QFrame#linksTag[active="false"] QPushButton,
            QFrame#linksTag[active="false"] QLineEdit {
                color: #687064;
            }
            QPushButton#primaryButton {
                background: rgba(93, 145, 66, 225);
                color: #f4ffed;
                font-weight: 700;
                min-width: 76px;
            }
            QComboBox, QLineEdit {
                background: rgba(25, 25, 25, 235);
                color: #d8ffbd;
                border: 1px solid rgba(176, 255, 123, 105);
                border-radius: 3px;
                padding: 4px 6px;
                min-height: 20px;
                selection-background-color: rgba(112, 164, 79, 220);
            }
            QComboBox:hover, QLineEdit:focus { border-color: #b0ff7b; }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #1b1b1b;
                color: #d8ffbd;
                border: 1px solid #6f9b55;
                selection-background-color: #557d3e;
            }
            QTreeWidget {
                background: rgba(18, 18, 18, 222);
                alternate-background-color: rgba(29, 36, 26, 205);
                color: #d8ded4;
                border: 1px solid rgba(176, 255, 123, 65);
                border-radius: 3px;
                gridline-color: rgba(176, 255, 123, 35);
                outline: none;
            }
            QTreeWidget::item { padding: 4px 2px; border-bottom: 1px solid rgba(176, 255, 123, 24); }
            QTreeWidget::item:selected { background: rgba(112, 164, 79, 125); color: white; }
            QHeaderView::section {
                background: rgba(34, 38, 32, 245);
                color: #b0ff7b;
                border: none;
                border-right: 1px solid rgba(176, 255, 123, 45);
                border-bottom: 1px solid rgba(176, 255, 123, 70);
                padding: 5px 4px;
                font-weight: 600;
            }
            QScrollBar:vertical { background: #181818; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: rgba(176, 255, 123, 125); min-height: 26px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QSizeGrip { background: transparent; }
        """)
        # Awakenedでは詳細ソースは任意表示。初期画面は検索条件そのものに集中する。
        self.mod_filter_tree.setColumnHidden(5, True)

    def _update_item_header(self, item):
        is_nonunique_equipment = (
            item.category in {"weapon", "armour", "accessory"}
            and item.rarity.casefold() not in {"unique", "ユニーク"}
        )
        display_name = (
            self._display_base_type(item)
            if is_nonunique_equipment
            else item.name or item.base_type or "名称不明"
        )
        self.item_name_label.setText(display_name)
        self.item_name_label.setVisible(not is_nonunique_equipment)
        self.base_scope_toggle.setVisible(is_nonunique_equipment)
        if is_nonunique_equipment:
            key = item.raw_text
            self.base_scope_toggle.setItemText(0, display_name)
            self.base_scope_toggle.setItemText(1, f"すべての{self._item_class_label(item.item_class)}")
            if key != self._base_scope_item_key:
                self._base_scope_item_key = key
                self.base_scope_toggle.setCurrentIndex(0)
        self.weapon_property_label.setText(
            "武器性能・検索Mod" if item.category == "weapon" else "検索条件"
        )

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
        if event.type() == QEvent.KeyPress and self.isVisible():
            is_escape = event.key() == Qt.Key_Escape
            is_alt_w = event.key() == Qt.Key_W and event.modifiers() == Qt.AltModifier
            if is_escape or is_alt_w:
                event.accept()
                self.close()
                return True
        return super().eventFilter(watched, event)

    def _close_when_focus_leaves_panel(self, old, new):
        old_belongs = self._widget_belongs_to_panel(old)
        new_belongs = self._widget_belongs_to_panel(new)
        if new is None and self._widget_is_panel_popup(old):
            return
        if self.isVisible() and old_belongs and not new_belongs:
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
            self._poe_ninja_item_key = None
            self._queue_poe_ninja_price(item)

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
        self._hide_poe_ninja_price(key)
        if not league:
            return

        def run():
            try:
                result = default_poe_ninja_service.lookup(
                    item, league,
                    trade_name=self._trade_item_name,
                    trade_base_type=self._trade_base_type,
                )
            except Exception:
                self._trade_signals.poe_ninja_failed.emit(key)
            else:
                if result is None:
                    self._trade_signals.poe_ninja_failed.emit(key)
                else:
                    self._trade_signals.poe_ninja_ready.emit(key, result)

        threading.Thread(target=run, daemon=True).start()

    def _show_poe_ninja_price(self, key, price: PoeNinjaPrice):
        if key != self._poe_ninja_item_key:
            return
        self.poe_ninja_price_value.setText(price.display_price())
        trend = price.trend_summary()
        self.poe_ninja_trend_label.setText(
            f"{trend[0]} {trend[1]}\n7日推移" if trend else "7日データなし"
        )
        self.poe_ninja_trend_chart.setPoints(price.graph_points())
        self._last_poe_ninja_url = price.url
        self.poe_ninja_price_panel.show()

    def _hide_poe_ninja_price(self, key=None):
        if key is not None and key != self._poe_ninja_item_key:
            return
        self.poe_ninja_price_panel.hide()
        self.poe_ninja_price_value.setText("—")
        self.poe_ninja_trend_label.clear()
        self.poe_ninja_trend_chart.setPoints(())
        self._last_poe_ninja_url = ""

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
        if self._focus_signal_connected:
            QApplication.instance().focusChanged.disconnect(self._close_when_focus_leaves_panel)
            self._focus_signal_connected = False
        super().closeEvent(event)

    def capture_from_poe(self):
        """通常コピーと詳細コピーを順番に取得し、日本語名を保って解析する。"""
        from pynput.keyboard import Controller, Key

        # この時点ではPoEが前面。コピー後にぽえとれがフォーカスを取る前に保存する。
        self._placement_context = capture_placement_context()
        self._capture_keyboard = Controller()
        QTimer.singleShot(250, lambda: self._send_copy((Key.ctrl, "c"), self._capture_normal_copy))

    def _send_copy(self, keys, callback):
        for key in keys:
            self._capture_keyboard.press(key)
        for key in reversed(keys):
            self._capture_keyboard.release(key)
        QTimer.singleShot(300, callback)

    def _capture_normal_copy(self):
        self._normal_copy_text = read_item_clipboard(QApplication.clipboard())
        from pynput.keyboard import Key
        self._send_copy((Key.ctrl, Key.alt, "c"), self._capture_detailed_copy)

    def _capture_detailed_copy(self):
        detailed_text = read_item_clipboard(QApplication.clipboard())
        try:
            detailed_item = parse_item_text(detailed_text)
            merged_text = merge_normal_and_detailed_copy(self._normal_copy_text, detailed_text)
        except ItemParseError as exc:
            QMessageBox.warning(self, "取り込めませんでした", f"PoEのアイテムコピーを取得できませんでした。\n{exc}")
            return
        self._trade_base_type = detailed_item.base_type
        self._trade_item_name = detailed_item.name if detailed_item.rarity.casefold() in {"unique", "ユニーク"} else None
        self._preset_item_key = None
        self._reset_unique_candidates()
        self.mod_filter_tree.clear()
        self.input_edit.setPlainText(merged_text)
        self.parse_current_text()
        self.show_at_context(self._placement_context)
        self.search_current_item()

    def show_at_context(self, context: PlacementContext | None = None, activate: bool = True):
        context = context or capture_placement_context()
        self._placement_context = context
        self.move(position_for_context(context, self.size()))
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()

    def parse_current_text(self):
        self._parsed_item = None
        try:
            item = parse_item_text(self.input_edit.toPlainText())
        except ItemParseError as exc:
            QMessageBox.warning(self, "解析できませんでした", str(exc))
            return
        if item.raw_text != self._unique_selector_item_key:
            self._reset_unique_candidates()
            self._unique_selector_item_key = item.raw_text
        self._configure_trade_presets(item)
        self._configure_trade_currency(item)
        self._configure_item_state_filters(item)
        self._configure_item_level(item)
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
            self._populate_stat_filters(resolve_trade_stat_filters(
                item, preset, self._trade_base_type,
            ))
        warnings = unresolved_modifier_warnings(item)
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
        if self.isVisible():
            self._queue_poe_ninja_price(item)

    def search_current_item(self):
        self.parse_current_text()
        item = getattr(self, "_parsed_item", None)
        if item is None:
            return
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
        selected_unique_name = self.unique_name_combo.currentData() if self.unique_name_combo.isVisible() else None
        trade_name = str(selected_unique_name or self._trade_item_name or "").strip() or None
        selected_discriminator = (
            self.unique_variant_combo.currentData() if self.unique_variant_combo.isVisible() else None
        )

        def run():
            try:
                initial_filters = resolve_trade_stat_filters(
                    item, preset, self._trade_base_type,
                ) if needs_initial_filters else ()
                effective_filters = initial_filters if needs_initial_filters else filters
                if item.category in {"gem", "weapon", "armour", "flask", "tincture"}:
                    effective_filters = tuple(
                        row for row in effective_filters
                        if row.stat_id not in {"property.gem_level", "property.quality"}
                    )
                if links_chip_visible:
                    effective_filters = tuple(
                        row for row in effective_filters if row.stat_id != "property.links"
                    )
                effective_filters = tuple(
                    row for row in effective_filters if row.kind != "influence"
                )
                special_ids = {
                    "property.map_tier", "property.area_level", "property.heist_wings",
                    "property.map_blighted", "property.map_uberblighted",
                    "property.map_completion_reward",
                }
                effective_filters = tuple(
                    row for row in effective_filters if row.stat_id not in special_ids
                ) + influence_filters + special_filters
                if item.rarity.casefold() in {"unique", "ユニーク"} and "unidentified" in item.flags and not trade_name:
                    candidates = unique_candidates(self._trade_base_type or item.base_type)
                    if len(candidates) > 1:
                        self._trade_signals.unique_candidates_ready.emit(candidates)
                        return
                    if not candidates:
                        raise TradeApiError("未鑑定ユニークの候補を公式データから特定できませんでした。")
                    resolved_trade_name = candidates[0]
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
                )
            except (TradeApiError, ValueError) as exc:
                self._trade_signals.failed.emit(str(exc))
            else:
                self._trade_signals.completed.emit(result, initial_filters)

        threading.Thread(target=run, daemon=True).start()

    def _configure_trade_presets(self, item):
        key = item.raw_text
        if key == self._preset_item_key:
            return
        self._preset_item_key = key
        presets = available_trade_presets(item)
        dedicated_exact = uses_dedicated_exact_preset(item)
        self.trade_preset_combo.blockSignals(True)
        self.trade_preset_combo.setItemText(0, "専用検索" if dedicated_exact else "完成品")
        self.trade_preset_combo.setSecondAvailable(PRESET_BASE in presets)
        self.trade_preset_combo.setCurrentIndex(0)
        self.trade_preset_combo.setEnabled(len(presets) > 1)
        if dedicated_exact:
            self.trade_preset_combo.setToolTip(
                "このアイテム種別に必要な条件だけを使う専用検索です。"
            )
        else:
            self.trade_preset_combo.setToolTip(
                "未完成でクラフト価値がある装備は、完成品とクラフトベースを切り替えて検索できます。"
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
            and item.category in {"weapon", "armour", "accessory", "cluster_jewel"}
        )
        self.magic_rarity_toggle.setVisible(show)
        if show:
            self.magic_rarity_toggle.setCurrentIndex(0)

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
        self._hidden_include_split = not (craftable and not has_special_state)
        is_mirrored = "mirrored" in item.flags
        self.mirrored_combo.setCurrentIndex(0)
        self.mirrored_combo.setVisible(is_mirrored)
        self._hidden_include_mirrored = not (craftable and "corrupted" not in item.flags)

    def _configure_item_level(self, item):
        """新しいアイテムを読み取った時だけ、共通ilvl条件を実値へ戻す。"""
        key = item.raw_text
        if key == getattr(self, "_item_level_item_key", None):
            return
        self._item_level_item_key = key
        has_item_level = item.item_level is not None
        self.item_level_tag.setVisible(has_item_level)
        self._set_item_level_filter_enabled(has_item_level)
        is_cluster = has_item_level and item.category == "cluster_jewel"
        self.item_level_range_separator.setVisible(is_cluster)
        self.item_level_max_edit.setVisible(is_cluster)
        self.item_level_tag.setFixedWidth(157 if is_cluster else 104)
        if is_cluster:
            minimum = max(value for value in (1, 50, 68, 75, 84) if value <= item.item_level)
            maximum = next((value for value in (49, 67, 74) if value >= item.item_level), None)
            self.item_level_edit.setText(str(minimum))
            self.item_level_max_edit.setText(str(maximum) if maximum is not None else "")
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
        elif item.category in {"weapon", "armour"}:
            visible = preset == PRESET_BASE and quality is not None and quality >= 20
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
        six_link_classes = {
            "鎧", "Body Armours", "弓", "Bows", "両手剣", "Two Hand Swords",
            "両手斧", "Two Hand Axes", "両手メイス", "Two Hand Maces",
            "スタッフ", "Staves", "ウォースタッフ", "Warstaves",
        }
        exceptional_base = item.base_type.casefold() in {"gnarled branch", "fishing rod"}
        visible = linked == 6 and item.item_class in six_link_classes and not exceptional_base
        self.links_tag.setVisible(visible)
        self.links_edit.setText("6" if visible else "")
        self._set_links_filter_enabled(visible)

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
            flag.split(":", 1)[1] for flag in item.flags
            if flag.startswith("influence:") and flag.split(":", 1)[1] in _INFLUENCE_CHIPS
        ]
        visible = set(influences) if 1 <= len(influences) <= 2 else set()
        exact = preset == PRESET_BASE or uses_dedicated_exact_preset(item)
        for influence, button in self.influence_chips.items():
            button.setVisible(influence in visible)
            self._set_influence_filter_enabled(influence, influence in visible and exact)

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
            label, stat_id = _INFLUENCE_CHIPS[influence]
            rows.append(TradeStatFilter(stat_id, f"{label}影響", None, "influence", True))
        return tuple(rows)

    def _configure_special_filter_chips(self, item):
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        key = (item.raw_text, preset)
        if key == getattr(self, "_special_chip_item_key", None):
            return
        self._special_chip_item_key = key
        rows = resolve_trade_stat_filters(item, preset, self._trade_base_type)
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

        numeric = (
            (self.map_tier_chip, "property.map_tier", True),
            (self.area_level_chip, "property.area_level", False),
            (self.heist_wings_chip, "property.heist_wings", False),
        )
        for chip, stat_id, exact in numeric:
            row = by_id.get(stat_id)
            chip.setVisible(row is not None)
            if row is not None:
                # Map Tierは完全一致だが、同じ値を2欄へ重複表示しない。
                # 選択条件へ戻す段階でmin=maxに復元する。
                maximum = None if exact else row.max_value
                chip.setValues(row.min_value, maximum)
                chip.setActive(row.enabled)

        blight = by_id.get("property.map_uberblighted") or by_id.get("property.map_blighted")
        self.blighted_chip.setVisible(blight is not None)
        self.blighted_chip.setText(blight.text if blight else "")
        reward = by_id.get("property.map_completion_reward")
        self.completion_reward_chip.setVisible(reward is not None)
        self.completion_reward_chip.setText(reward.text if reward else "")

    def _selected_special_chip_filters(self) -> tuple[TradeStatFilter, ...]:
        rows = getattr(self, "_special_chip_rows", {})
        selected = []
        for chip, stat_id in (
            (self.map_tier_chip, "property.map_tier"),
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
        for stat_id in (
            "property.map_blighted", "property.map_uberblighted",
            "property.map_completion_reward",
        ):
            row = rows.get(stat_id)
            if row is not None:
                selected.append(replace(row, enabled=True))
        return tuple(selected)

    def _trade_preset_changed(self):
        if not hasattr(self, "mod_filter_tree"):
            return
        self.mod_filter_tree.clear()
        self.price_list.clear()
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        item = getattr(self, "_parsed_item", None)
        self._configure_magic_rarity_toggle(item)
        if item is not None:
            self._configure_quality(item)
            self._configure_influence_chips(item)
            self._configure_special_filter_chips(item)
            self._populate_stat_filters(resolve_trade_stat_filters(
                item, preset, self._trade_base_type,
            ))
        if preset == PRESET_BASE:
            self.price_status.setText(
                "クラフトベースとして、ベースタイプとアイテムレベルを中心に検索します。"
            )
        elif item is not None and uses_dedicated_exact_preset(item):
            self.price_status.setText(
                "アイテム種別に合わせた専用条件で検索します。"
            )
        else:
            self.price_status.setText("完成品として、実際の性能を中心に検索します。")

    def _reset_unique_candidates(self):
        self.unique_name_combo.clear()
        self.unique_name_combo.hide()
        self.unique_name_label.hide()
        self.unique_variant_combo.clear()
        self.unique_variant_combo.hide()
        self.unique_variant_label.hide()

    def _show_unique_candidates(self, candidates):
        self.price_button.setEnabled(True)
        self.unique_name_combo.clear()
        for name in candidates:
            self.unique_name_combo.addItem(str(name), str(name))
        self.unique_name_label.show()
        self.unique_name_combo.show()
        self.price_status.setText(
            f"同じベースの未鑑定ユニークが{len(candidates)}種類あります。候補を選んで「価格を検索」を押してください。"
        )

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
            editor = self.mod_filter_tree.itemWidget(row, 3)
            max_editor = self.mod_filter_tree.itemWidget(row, 4)
            logic_editor = self.mod_filter_tree.itemWidget(row, 6)
            value_text = editor.text().strip() if isinstance(editor, QLineEdit) else row.text(3).strip()
            max_text = max_editor.text().strip() if isinstance(max_editor, QLineEdit) else row.text(4).strip()
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
                    enabled=row.checkState(0) == Qt.Checked,
                    group_type=(logic_editor.currentData()
                                if isinstance(logic_editor, QComboBox) else original.group_type),
                ))
            else:
                filters.append(TradeStatFilter(
                    row.data(0, Qt.UserRole), row.text(2), value, row.text(1),
                    row.checkState(0) == Qt.Checked,
                    maximum, row.data(0, Qt.UserRole + 1), row.data(0, Qt.UserRole + 2) or 0.0,
                    bool(row.data(0, Qt.UserRole + 3)),
                ))
        return tuple(filters)

    def _populate_stat_filters(self, filters: tuple[TradeStatFilter, ...]):
        self.mod_filter_tree.clear()
        for stat_filter in filters:
            if stat_filter.stat_id in {"property.item_level", "property.gem_level"}:
                continue
            if (stat_filter.stat_id == "property.quality"
                    and getattr(self, "_parsed_item", None) is not None
                    and self._parsed_item.category in {"gem", "weapon", "armour", "flask", "tincture"}):
                continue
            if stat_filter.stat_id == "property.links" and not self.links_tag.isHidden():
                continue
            if stat_filter.kind == "influence":
                continue
            if stat_filter.stat_id in {
                "property.map_tier", "property.area_level", "property.heist_wings",
                "property.map_blighted", "property.map_uberblighted",
                "property.map_completion_reward",
            }:
                continue
            value = "" if stat_filter.min_value is None else f"{stat_filter.min_value:g}"
            maximum = "" if stat_filter.max_value is None else f"{stat_filter.max_value:g}"
            details = []
            if stat_filter.read_value is not None:
                details.append(f"読取 {stat_filter.read_value:g}")
            if stat_filter.tier is not None:
                details.append(f"T{stat_filter.tier}")
            if stat_filter.roll_min is not None and stat_filter.roll_max is not None:
                details.append(f"範囲 {stat_filter.roll_min:g}–{stat_filter.roll_max:g}")
            if stat_filter.affix:
                details.append(stat_filter.affix.capitalize())
            if stat_filter.generation and stat_filter.generation != stat_filter.kind:
                details.append(stat_filter.generation)
            if stat_filter.exact:
                details.append("完全一致")
            elif stat_filter.better == -1:
                details.append("低いほど良い")
            if stat_filter.inverted:
                details.append("API符号反転")
            if stat_filter.option_text:
                details.append(f"選択肢 {stat_filter.option_text}")
            if stat_filter.oils:
                oil_names = (
                    "プリズマチック", "澄んだ", "セピア色", "琥珀色", "新緑色", "青緑色",
                    "淡青色", "藍色", "スミレ色", "深紅色", "黒色", "乳白色", "銀色", "金色",
                )
                details.append("Oil " + " + ".join(oil_names[index] for index in stat_filter.oils))
            if stat_filter.group_type != "and":
                details.append(stat_filter.group_type.upper())
            is_mod = stat_filter.kind in {
                "explicit", "prefix", "suffix", "crafted", "fractured", "implicit", "enchant", "veiled"
            }
            if is_mod and stat_filter.confidence:
                confidence = f"一致 {stat_filter.confidence:.0%}"
                if stat_filter.confidence < 1:
                    confidence = f"⚠ {confidence}"
            elif is_mod:
                confidence = "⚠ 一致未確認"
            else:
                confidence = ""
            summary = " / ".join(filter(None, [stat_filter.selection_reason, *details, confidence]))
            row = QTreeWidgetItem(["", stat_filter.kind, stat_filter.text, "", "", summary, ""])
            row.setData(0, Qt.UserRole, stat_filter.stat_id)
            row.setData(0, Qt.UserRole + 1, stat_filter.ref)
            row.setData(0, Qt.UserRole + 2, stat_filter.confidence)
            row.setData(0, Qt.UserRole + 3, stat_filter.inverted)
            row.setData(0, Qt.UserRole + 4, stat_filter)
            row.setToolTip(2, summary)
            row.setToolTip(5, summary)
            row.setCheckState(0, Qt.Checked if stat_filter.enabled else Qt.Unchecked)
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
            self.mod_filter_tree.addTopLevelItem(row)
            editor = QLineEdit(value)
            editor.installEventFilter(self)
            editor.setPlaceholderText("最小")
            editor.setFixedWidth(80)
            editor.setEnabled(stat_filter.option_value is None)
            self.mod_filter_tree.setItemWidget(row, 3, editor)
            max_editor = QLineEdit(maximum)
            max_editor.installEventFilter(self)
            max_editor.setPlaceholderText("最大")
            max_editor.setFixedWidth(80)
            max_editor.setEnabled(stat_filter.option_value is None)
            self.mod_filter_tree.setItemWidget(row, 4, max_editor)
            logic = QComboBox()
            logic.installEventFilter(self)
            for label, value_name in (("AND", "and"), ("NOT", "not"), ("COUNT", "count")):
                logic.addItem(label, value_name)
            logic.setCurrentIndex(max(0, logic.findData(stat_filter.group_type)))
            self.mod_filter_tree.setItemWidget(row, 6, logic)

    def _search_completed(self, result: PriceResult, initial_filters):
        if initial_filters:
            self._populate_stat_filters(initial_filters)
        self._show_price_result(result)

    def _show_price_result(self, result: PriceResult):
        self.price_button.setEnabled(True)
        self._last_trade_url = result.web_url
        self.trade_url_button.setEnabled(bool(result.web_url))
        cache_note = " / キャッシュ" if result.cached else ""
        if not result.listings:
            self.price_status.setText(
                f"{result.league}: 検索候補{result.total}件{cache_note}。"
                "価格付き出品は取得できませんでした。"
            )
            return
        medians = " / ".join(
            f"{value:g} {currency}" for currency, value in result.median_by_currency().items()
        )
        samples = ", ".join(f"{row.amount:g} {row.currency}" for row in result.listings[:5])
        self.price_status.setText(
            f"{result.league}: 候補{result.total}件 / 取得{len(result.listings)}件{cache_note} | "
            f"中央値 {medians} | 安値例 {samples}"
        )
        for index, listing in enumerate(result.listings, start=1):
            item_label = listing.item_name or listing.base_type or "（名前なし）"
            if listing.item_name and listing.base_type:
                item_label = f"{listing.item_name} / {listing.base_type}"
            QTreeWidgetItem(self.price_list, [
                str(index), f"{listing.amount:g} {listing.currency}", item_label,
                listing.account or "-",
            ])

    def _show_price_error(self, message: str):
        self.price_button.setEnabled(True)
        self.price_list.clear()
        self.price_status.setText(message)

    def _open_trade_url(self):
        if self._last_trade_url:
            QDesktopServices.openUrl(QUrl(self._last_trade_url))


def show_poetore_window(owner, activate=True):
    """ownerが参照を保持し、二重起動せず独立表示できる公開エントリ。"""
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
    if isinstance(getattr(owner, "config", None), dict):
        window.refresh_trade_leagues()
    if activate:
        window.show_at_context()
    return window
