"""Custom Currency Exchange rate rows for the ぽえとれ main window."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from src.poetore.exchange_catalog import exchange_catalog_by_id
from src.poetore.exchange_icon_cache import ExchangeIconCache
from src.poetore.exchange_rate_cache import ExchangeRateValueCache
from src.poetore.exchange_rate_settings import MAX_RATE_PAIRS, ExchangeRatePairStore
from src.poetore.official_exchange import OfficialExchangeShadowService
from src.ui.app_theme import POETORE_THEME

RATE_CHECK_INTERVAL_MSEC = 10 * 60 * 1000
OFFICIAL_DATA_TOOLTIP = (
    "公式Currency Exchange APIは、完了した1時間ごとの取引データを提供する仕様です。"
    "ぽえとれは新しい時間データの公開を自動確認します。"
)


def format_significant_rate(value: float) -> str:
    """Round to four significant digits and strip fractional trailing zeroes."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError("rate must be finite and positive")
    decimal = Decimal(str(value))
    quantum = Decimal(1).scaleb(decimal.adjusted() - 3)
    rounded = decimal.quantize(quantum, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    integer, separator, fraction = text.partition(".")
    grouped = f"{int(integer):,}"
    return grouped + (separator + fraction if separator else "")


class _PanelSignals(QObject):
    table_ready = Signal()
    checked = Signal(object)
    icon_ready = Signal(str, str, str)


class ElidedLabel(QLabel):
    """Keep the full accessible text while painting an elided single line."""

    def paintEvent(self, event):
        painter = QPainter(self)
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(self.alignment()), text)
        painter.end()


class CustomExchangeRatePanel(QWidget):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        poe_version: str,
        store: ExchangeRatePairStore,
        league_getter: Callable[[], str],
        service: OfficialExchangeShadowService,
        value_cache: ExchangeRateValueCache,
        icon_cache: ExchangeIconCache,
        on_manage: Callable[[], None],
        on_rows_changed: Callable[[], None] | None = None,
        refresh_callback: Callable[..., None] | None = None,
    ):
        super().__init__(parent)
        self.poe_version = poe_version
        self.store = store
        self.league_getter = league_getter
        self.service = service
        self.value_cache = value_cache
        self.icon_cache = icon_cache
        self.on_manage = on_manage
        self.on_rows_changed = on_rows_changed or (lambda: None)
        self.refresh_callback = refresh_callback or self.refresh
        self.catalog = exchange_catalog_by_id(poe_version)
        self.row_widgets: list[QWidget] = []
        self._signals = _PanelSignals(self)
        self._signals.table_ready.connect(self._table_ready)
        self._signals.checked.connect(self._sync_checked)
        # A disk-cache hit can complete before the row has been attached to this
        # panel. Queue delivery so the label is discoverable when the icon is
        # applied, regardless of whether the Future completed synchronously.
        self._signals.icon_ready.connect(self._apply_icon, Qt.QueuedConnection)
        self._manual_check = False
        self._sync_in_progress = False
        self._build_ui()
        self.render_rows()
        self.check_timer = QTimer(self)
        self.check_timer.setInterval(RATE_CHECK_INTERVAL_MSEC)
        self.check_timer.timeout.connect(self.refresh_callback)
        self.check_timer.start()

    def _build_ui(self) -> None:
        self.setStyleSheet(f"""
            QToolTip {{
                color: {POETORE_THEME.text};
                background-color: {POETORE_THEME.background};
                border: 1px solid #66706C;
                padding: 5px;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        title_row = QHBoxLayout()
        self.title_label = QLabel("カレンシー交換レート")
        self.title_label.setStyleSheet(
            f"color: {POETORE_THEME.accent}; font-size: 15px; font-weight: bold;"
        )
        self.title_label.setToolTip(OFFICIAL_DATA_TOOLTIP)
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        self.manage_button = QPushButton("管理")
        self.manage_button.setAccessibleName("レート表示の管理を開く")
        self.manage_button.setToolTip("登録、削除、並べ替え")
        self.manage_button.clicked.connect(self.on_manage)
        title_row.addWidget(self.manage_button)
        root.addLayout(title_row)

        self.card = QFrame()
        self.card.setObjectName("customExchangeRateCard")
        self.card.setStyleSheet(f"""
            QFrame#customExchangeRateCard {{
                background: {POETORE_THEME.panel}; border: 1px solid #343B3E;
                border-radius: 10px;
            }}
        """)
        self.rows_layout = QVBoxLayout(self.card)
        self.rows_layout.setContentsMargins(10, 8, 10, 8)
        self.rows_layout.setSpacing(4)
        root.addWidget(self.card)

        footer = QHBoxLayout()
        self.status_label = QLabel("最新データを確認中…")
        self.status_label.setStyleSheet("color: #98A39F; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setToolTip(OFFICIAL_DATA_TOOLTIP)
        footer.addWidget(self.status_label, 1)
        self.refresh_button = QPushButton("最新データ確認")
        self.refresh_button.setFocusPolicy(Qt.NoFocus)
        self.refresh_button.setToolTip(OFFICIAL_DATA_TOOLTIP)
        self.refresh_button.clicked.connect(
            lambda: self.refresh_callback(manual=True)
        )
        footer.addWidget(self.refresh_button)
        root.addLayout(footer)

    def render_rows(self) -> None:
        while self.rows_layout.count():
            child = self.rows_layout.takeAt(0)
            if child.widget() is not None:
                child.widget().hide()
                child.widget().deleteLater()
        self.row_widgets.clear()
        league = self.league_getter()
        pairs = self.store.pairs(self.poe_version)
        latest_cached_at = None
        for index, pair in enumerate(pairs):
            display_is_rate = False
            result = self.service.direct_pair(
                self.poe_version, league, pair.left_item_id, pair.right_item_id
            )
            if result.status == "available" and result.price is not None:
                display = format_significant_rate(result.price)
                display_is_rate = True
                self.value_cache.put(
                    self.poe_version,
                    league,
                    pair.left_item_id,
                    pair.right_item_id,
                    result.price,
                    result.end_hour or 0,
                )
            elif result.status == "no_trades":
                display = "取引データなし"
            elif result.status == "unconfirmed":
                display = "価格未確定"
            else:
                cached = self.value_cache.get(
                    self.poe_version, league, pair.left_item_id, pair.right_item_id
                )
                if cached is not None:
                    display = format_significant_rate(cached.price)
                    display_is_rate = True
                    latest_cached_at = max(latest_cached_at or 0, cached.confirmed_at)
                else:
                    display = (
                        "最新データ取得中…"
                        if self._sync_in_progress
                        else "最新データを取得できません"
                    )
            row = self._make_row(
                index,
                pair.left_item_id,
                pair.right_item_id,
                display,
                display_is_rate=display_is_rate,
            )
            self.rows_layout.addWidget(row)
            self.row_widgets.append(row)

        if len(pairs) < MAX_RATE_PAIRS:
            self.add_button = QPushButton("＋")
            self.add_button.setObjectName("customRateAddButton")
            self.add_button.setAccessibleName("表示する交換レートを追加")
            self.add_button.setToolTip("レート表示の管理を開く")
            self.add_button.setFixedHeight(30 if pairs else 54)
            self.add_button.setStyleSheet(
                "QPushButton { color: #68716E; background: transparent; "
                "border: 1px dashed #3A4245; font-size: 21px; }"
                f"QPushButton:hover, QPushButton:focus {{ color: {POETORE_THEME.accent}; "
                f"border-color: {POETORE_THEME.accent}; }}"
            )
            self.add_button.clicked.connect(self.on_manage)
            self.rows_layout.addWidget(self.add_button)
        else:
            self.add_button = None

        state = self.service.sync_state(self.poe_version, league)
        if self._sync_in_progress:
            self.status_label.setText("最新データを確認中…")
        elif state.available:
            self.status_label.setText(
                f"{league} ・ 公式取引データ（1時間単位・自動取得）"
            )
        elif latest_cached_at is not None:
            age_hours = max(0, int((time.time() - latest_cached_at) // 3600))
            self.status_label.setText(f"最終確認 {age_hours}時間前")
        self.on_rows_changed()

    def _make_row(
        self,
        index: int,
        left_id: str,
        right_id: str,
        display: str,
        *,
        display_is_rate: bool,
    ) -> QWidget:
        row = QWidget()
        row.setObjectName(f"customRateRow{index}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(7)
        left_icon = self._icon_label(left_id, "left")
        layout.addWidget(left_icon)
        left_name = ElidedLabel(self.catalog[left_id].japanese_name)
        left_name.setObjectName(f"customRateLeftName{index}")
        left_name.setToolTip(left_name.text())
        left_name.setAccessibleName(left_name.text())
        left_name.setFixedWidth(125)
        left_name.setStyleSheet(
            f"color: {POETORE_THEME.accent}; font-size: 13px;"
        )
        layout.addWidget(left_name)
        value_text = f"1 ＝ {display}" if display_is_rate else display
        value = QLabel(value_text)
        value.setObjectName(f"customRateValue{index}")
        value.setAlignment(Qt.AlignCenter)
        value.setToolTip(value_text)
        value_font_size = 15 if display_is_rate else 12
        value.setStyleSheet(
            f"color: {POETORE_THEME.text}; font-size: {value_font_size}px; "
            "font-weight: bold;"
        )
        layout.addWidget(value, 1)
        right_icon = self._icon_label(right_id, "right")
        layout.addWidget(right_icon)
        right_name = ElidedLabel(self.catalog[right_id].japanese_name)
        right_name.setObjectName(f"customRateRightName{index}")
        right_name.setToolTip(right_name.text())
        right_name.setAccessibleName(right_name.text())
        right_name.setFixedWidth(88)
        right_name.setStyleSheet(
            f"color: {POETORE_THEME.accent}; font-size: 13px;"
        )
        layout.addWidget(right_name)
        delete = QPushButton()
        delete.setObjectName(f"customRateDelete{index}")
        delete.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        delete.setIconSize(QSize(17, 17))
        delete.setFixedSize(32, 32)
        delete.setToolTip("このレートを削除")
        delete.setAccessibleName("このレートを削除")
        delete.clicked.connect(lambda _checked=False, i=index: self._remove(i))
        layout.addWidget(delete)
        return row

    def _icon_label(self, item_id: str, side: str) -> QLabel:
        label = QLabel()
        label.setObjectName(f"customRateIcon-{side}-{item_id}")
        label.setFixedSize(28, 28)
        label.setToolTip(self.catalog[item_id].japanese_name)
        item = self.catalog[item_id]
        future = self.icon_cache.request(item.icon_kind, item.icon_url)

        def completed(result_future, selected=item_id, selected_side=side):
            try:
                result = result_future.result()
            except Exception:  # noqa: BLE001  # cache worker contains failures
                return
            self._signals.icon_ready.emit(selected, selected_side, str(result.path))

        future.add_done_callback(completed)
        return label

    def _apply_icon(self, item_id: str, side: str, path: str) -> None:
        icon = QIcon(path)
        pixmap = icon.pixmap(QSize(28, 28))
        for label in self.findChildren(QLabel, f"customRateIcon-{side}-{item_id}"):
            label.setPixmap(pixmap)

    def _remove(self, index: int) -> None:
        self.store.remove(self.poe_version, index)
        self.render_rows()

    def refresh(self, *, manual: bool = False) -> None:
        self._manual_check = self._manual_check or manual
        self._sync_in_progress = True
        self.status_label.setText("最新データを確認中…")
        self.refresh_button.setEnabled(False)
        self.render_rows()
        league = self.league_getter()
        self.service.queue_sync(
            self.poe_version,
            league,
            on_complete=lambda _result: self._signals.table_ready.emit(),
            on_checked=lambda result: self._signals.checked.emit(result),
        )

    def _table_ready(self) -> None:
        self.render_rows()

    def _sync_checked(self, result) -> None:
        self._sync_in_progress = False
        self.refresh_button.setEnabled(True)
        manual = self._manual_check
        self._manual_check = False
        self.render_rows()
        if result.status == "updated":
            self.status_label.setText("最新の公式データへ更新しました")
        elif result.status == "no_new_data" and manual:
            self.status_label.setText("新しい公式データはまだありません")
        elif result.status == "failed":
            has_cached = any(
                self.value_cache.get(
                    self.poe_version,
                    self.league_getter(),
                    pair.left_item_id,
                    pair.right_item_id,
                ) is not None
                for pair in self.store.pairs(self.poe_version)
            )
            if not has_cached:
                self.status_label.setText("公式データを取得できませんでした")

    def available_item_ids(self) -> frozenset[str]:
        return self.service.exchange_item_ids(
            self.poe_version, self.league_getter()
        )

    def league_changed(self) -> None:
        self.render_rows()

    def stop(self) -> None:
        self.check_timer.stop()
