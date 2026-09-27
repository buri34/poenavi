"""Management dialog for the main window's custom Currency Exchange rates."""

from __future__ import annotations

from collections.abc import Callable, Collection

from PySide6.QtCore import QMimeData, QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.poetore.exchange_catalog import (
    ExchangeCatalogItem,
    category_labels,
    exchange_catalog_by_id,
    exchange_catalog_items,
)
from src.poetore.exchange_icon_cache import ExchangeIconCache
from src.poetore.exchange_rate_settings import (
    CHAOS_ORB_ID,
    DIVINE_ORB_ID,
    EXALTED_ORB_ID,
    MAX_RATE_PAIRS,
    ExchangeRatePairStore,
    RatePairValidationError,
)
from src.ui.app_theme import POETORE_THEME

BASE_CURRENCY_IDS = (DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID)
RATE_PAIR_DRAG_MIME = "application/x-poenavi-rate-pair-index"
CANDIDATE_ROW_HEIGHT = 18
CANDIDATE_ICON_SIZE = 14


class _IconSignals(QObject):
    ready = Signal(str, str)


class _RegisteredPairRow(QWidget):
    """A rate-pair row that starts an internal reorder drag outside its buttons."""

    def __init__(self, index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.index = index
        self._drag_start: QPoint | None = None
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("ドラッグして表示順を変更")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_start is None
            or not event.buttons() & Qt.LeftButton
            or (event.position().toPoint() - self._drag_start).manhattanLength()
            < QApplication.startDragDistance()
        ):
            super().mouseMoveEvent(event)
            return
        mime = QMimeData()
        mime.setData(RATE_PAIR_DRAG_MIME, str(self.index).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._drag_start)
        drag.exec(Qt.MoveAction)
        self._drag_start = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class _RegisteredPairsWidget(QWidget):
    """Drop surface that maps a visual insertion point to a final pair index."""

    reordered = Signal(int, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[_RegisteredPairRow] = []
        self.setAcceptDrops(True)

    def set_rows(self, rows: list[_RegisteredPairRow]) -> None:
        self._rows = rows

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(RATE_PAIR_DRAG_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasFormat(RATE_PAIR_DRAG_MIME):
            return
        content_y = self._auto_scroll(event.position().toPoint())
        self._show_drop_indicator(self._insertion_index(content_y))
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._clear_drop_indicator()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._clear_drop_indicator()
        if not event.mimeData().hasFormat(RATE_PAIR_DRAG_MIME):
            return
        try:
            source = int(bytes(event.mimeData().data(RATE_PAIR_DRAG_MIME)))
        except ValueError:
            return
        if source < 0 or source >= len(self._rows):
            return
        destination = self._destination_index(
            source, self._insertion_index(event.position().y())
        )
        if destination != source:
            self.reordered.emit(source, destination)
        event.acceptProposedAction()

    def _insertion_index(self, y: float) -> int:
        for index, row in enumerate(self._rows):
            if y < row.geometry().center().y():
                return index
        return len(self._rows)

    def _destination_index(self, source: int, insertion: int) -> int:
        if not self._rows:
            return source
        destination = insertion - 1 if insertion > source else insertion
        return max(0, min(destination, len(self._rows) - 1))

    def _auto_scroll(self, content_position: QPoint) -> int:
        scroll_area = self.parentWidget()
        while scroll_area is not None and not isinstance(scroll_area, QScrollArea):
            scroll_area = scroll_area.parentWidget()
        if scroll_area is None:
            return content_position.y()
        viewport = scroll_area.viewport()
        viewport_position = viewport.mapFrom(self, content_position)
        scroll_bar = scroll_area.verticalScrollBar()
        edge = 24
        step = max(20, scroll_bar.singleStep())
        if viewport_position.y() < edge:
            scroll_bar.setValue(scroll_bar.value() - step)
        elif viewport_position.y() > viewport.height() - edge:
            scroll_bar.setValue(scroll_bar.value() + step)
        return viewport.mapTo(self, viewport_position).y()

    def _show_drop_indicator(self, insertion: int) -> None:
        self._clear_drop_indicator()
        if not self._rows:
            return
        if insertion >= len(self._rows):
            row = self._rows[-1]
            border = "border-bottom"
        else:
            row = self._rows[insertion]
            border = "border-top"
        row.setStyleSheet(
            f"QWidget#{row.objectName()} {{ {border}: 2px solid "
            f"{POETORE_THEME.accent}; }}"
        )

    def _clear_drop_indicator(self) -> None:
        for row in self._rows:
            row.setStyleSheet("")


class ExchangeRateManagementDialog(QDialog):
    """Edit ordered custom-rate pairs and save every operation immediately."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        poe_version: str,
        store: ExchangeRatePairStore,
        available_item_ids: Collection[str],
        icon_cache: ExchangeIconCache,
        on_changed: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.poe_version = poe_version
        self.store = store
        self.icon_cache = icon_cache
        self.on_changed = on_changed or (lambda: None)
        self.catalog = exchange_catalog_by_id(poe_version)
        self._all_items = exchange_catalog_items(poe_version)
        self._available_item_ids = frozenset(available_item_ids)
        self._category_by_label = {
            label: category
            for category, label in self._category_label_pairs()
        }
        self._icon_signals = _IconSignals(self)
        self._icon_signals.ready.connect(self._apply_icon)
        self._icon_requested: set[str] = set()

        self.setWindowTitle("レート表示の管理")
        self.setModal(True)
        self.resize(820, 650)
        self.setMinimumSize(720, 560)
        self._build_ui()
        self._render_registered_pairs()
        self._filter_candidates()

    def _category_label_pairs(self) -> tuple[tuple[str, str], ...]:
        labels = category_labels(self.poe_version)
        categories = tuple(dict.fromkeys(item.category for item in self._all_items))
        return tuple(zip(categories, labels, strict=True))

    def _build_ui(self) -> None:
        theme = POETORE_THEME
        self.setStyleSheet(f"""
            QDialog {{ background: {theme.background}; color: {theme.text}; }}
            QLabel {{ color: {theme.text}; }}
            QLineEdit, QListWidget, QScrollArea {{
                background: {theme.panel}; color: {theme.text};
                border: 1px solid #3A4245; border-radius: 6px;
            }}
            QListWidget::item {{ padding: 7px; }}
            QListWidget::item:selected {{
                background: #276B5A; color: #FFFFFF;
            }}
            QPushButton {{
                background: #1A1F21; color: {theme.text};
                border: 1px solid #3A4245; border-radius: 6px;
                padding: 7px 12px; font-weight: bold;
            }}
            QPushButton:hover, QPushButton:focus {{ border-color: {theme.accent}; }}
            QPushButton:disabled {{ color: #66706C; border-color: #2B3133; }}
            QFrame#ratePairItemCard, QFrame#ratePairCurrencyCard {{
                background: #171C1E; border: 1px solid #3A4245;
                border-radius: 8px;
            }}
            QPushButton[rateCurrencyChoice="true"] {{
                text-align: left; padding: 8px 10px; font-weight: normal;
                background: #1A1F21;
            }}
            QPushButton[rateCurrencyChoice="true"]:checked {{
                color: #FFFFFF; background: #245C50;
                border-color: {theme.accent}; font-weight: bold;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        self.title_label = QLabel()
        self.title_label.setStyleSheet(
            f"color: {theme.accent}; font-size: 18px; font-weight: bold;"
        )
        root.addWidget(self.title_label)

        registered_title = QLabel("登録済み")
        registered_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        root.addWidget(registered_title)
        self.registered_scroll = QScrollArea()
        self.registered_scroll.setObjectName("registeredPairsScroll")
        self.registered_scroll.setWidgetResizable(True)
        self.registered_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.registered_scroll.setFixedHeight(175)
        self.registered_scroll.viewport().setStyleSheet(
            f"background: {theme.panel}; color: {theme.text};"
        )
        self.registered_widget = _RegisteredPairsWidget()
        self.registered_widget.setObjectName("registeredPairsWidget")
        self.registered_widget.setStyleSheet(
            f"QWidget#registeredPairsWidget {{ background: {theme.panel}; "
            f"color: {theme.text}; }}"
        )
        self.registered_layout = QVBoxLayout(self.registered_widget)
        self.registered_layout.setContentsMargins(6, 6, 6, 6)
        self.registered_layout.setSpacing(5)
        self.registered_widget.reordered.connect(self._drag_reorder)
        self.registered_scroll.setWidget(self.registered_widget)
        root.addWidget(self.registered_scroll)

        add_title = QLabel("追加するペア")
        add_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        root.addWidget(add_title)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(10)

        self.item_card = QFrame()
        self.item_card.setObjectName("ratePairItemCard")
        item_card_layout = QVBoxLayout(self.item_card)
        item_card_layout.setContentsMargins(10, 10, 10, 10)
        item_card_layout.setSpacing(8)
        self.item_card_title = QLabel("価格を確認するアイテム")
        self.item_card_title.setObjectName("ratePairItemCardTitle")
        self.item_card_title.setStyleSheet(
            f"color: {theme.accent}; font-weight: bold;"
        )
        item_card_layout.addWidget(self.item_card_title)

        search_row = QHBoxLayout()
        self.search_label = QLabel("検索")
        self.search_label.setObjectName("ratePairSearchLabel")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("日本語名で検索")
        self.search_edit.setAccessibleName("価格を確認するアイテムの日本語名検索")
        self.search_edit.setClearButtonEnabled(True)
        self.search_clear_button = self.search_edit.findChild(QToolButton)
        if self.search_clear_button is not None:
            self.search_clear_button.setObjectName("ratePairSearchClear")
            self.search_clear_button.setToolTip("検索文字列をクリア")
            self.search_clear_button.setAccessibleName("検索文字列をクリア")
        self.search_edit.textChanged.connect(self._filter_candidates)
        search_row.addWidget(self.search_label)
        search_row.addWidget(self.search_edit, 1)
        item_card_layout.addLayout(search_row)

        item_selection_row = QHBoxLayout()
        item_selection_row.setSpacing(10)
        self.category_list = QListWidget()
        self.category_list.setAccessibleName("カテゴリ")
        self.category_list.setFixedWidth(145)
        self.category_list.addItem("すべて")
        self.category_list.addItems(category_labels(self.poe_version))
        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self._category_changed)
        item_selection_row.addWidget(self.category_list)

        self.candidate_list = QListWidget()
        self.candidate_list.setObjectName("ratePairCandidateList")
        self.candidate_list.setAccessibleName("価格を確認するアイテム")
        self.candidate_list.setIconSize(
            QSize(CANDIDATE_ICON_SIZE, CANDIDATE_ICON_SIZE)
        )
        self.candidate_list.setUniformItemSizes(True)
        self.candidate_list.currentItemChanged.connect(self._selection_changed)
        self.candidate_list.verticalScrollBar().valueChanged.connect(
            self._request_visible_icons
        )
        item_selection_row.addWidget(self.candidate_list, 1)
        item_card_layout.addLayout(item_selection_row, 1)
        selection_row.addWidget(self.item_card, 1)

        self.exchange_symbol = QLabel("⇔")
        self.exchange_symbol.setObjectName("ratePairExchangeSymbol")
        self.exchange_symbol.setAlignment(Qt.AlignCenter)
        self.exchange_symbol.setFixedWidth(34)
        self.exchange_symbol.setStyleSheet(
            f"color: {theme.accent}; font-size: 22px; font-weight: bold;"
        )
        selection_row.addWidget(self.exchange_symbol)

        self.currency_card = QFrame()
        self.currency_card.setObjectName("ratePairCurrencyCard")
        self.currency_card.setFixedWidth(165)
        currency_layout = QVBoxLayout(self.currency_card)
        currency_layout.setContentsMargins(10, 10, 10, 10)
        currency_layout.setSpacing(8)
        self.currency_card_title = QLabel("通貨")
        self.currency_card_title.setObjectName("ratePairCurrencyCardTitle")
        self.currency_card_title.setStyleSheet(
            f"color: {theme.accent}; font-weight: bold;"
        )
        currency_layout.addWidget(self.currency_card_title)
        self.currency_group = QButtonGroup(self)
        self.currency_group.setExclusive(True)
        self.currency_buttons: dict[str, QPushButton] = {}
        for item_id in BASE_CURRENCY_IDS:
            name = self.catalog[item_id].japanese_name
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("rateCurrencyChoice", True)
            button.setIconSize(QSize(26, 26))
            button.setMinimumHeight(42)
            button.setAccessibleName(f"通貨 {name}")
            self.currency_group.addButton(button)
            self.currency_buttons[item_id] = button
            currency_layout.addWidget(button)
            button.toggled.connect(self._selection_changed)
        currency_layout.addStretch()
        selection_row.addWidget(self.currency_card)
        root.addLayout(selection_row, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer_copy = QVBoxLayout()
        footer_copy.setSpacing(2)
        self.preview_label = QLabel("アイテムと通貨を選択してください")
        self.preview_label.setObjectName("ratePairPreview")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("font-weight: bold;")
        footer_copy.addWidget(self.preview_label)
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("color: #D4AAA5; font-size: 11px;")
        footer_copy.addWidget(self.validation_label)
        footer.addLayout(footer_copy, 1)
        self.add_button = QPushButton("追加")
        self.add_button.setAccessibleName("選択したレートを追加")
        self.add_button.clicked.connect(self._add_selected_pair)
        footer.addWidget(self.add_button)
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        for item_id in BASE_CURRENCY_IDS:
            self._request_item_icon(item_id)

    def update_available_item_ids(self, item_ids: Collection[str]) -> None:
        self._available_item_ids = frozenset(item_ids)
        self._filter_candidates()

    def _filtered_items(self) -> tuple[ExchangeCatalogItem, ...]:
        query = self.search_edit.text().strip().casefold()
        selected_label = self.category_list.currentItem().text()
        selected_category = self._category_by_label.get(selected_label)
        items = (
            item for item in self._all_items
            if item.item_id in self._available_item_ids
        )
        if query:
            return tuple(item for item in items if query in item.japanese_name.casefold())
        if selected_category is not None:
            return tuple(item for item in items if item.category == selected_category)
        return tuple(items)

    def _filter_candidates(self, *_args) -> None:
        if not hasattr(self, "candidate_list"):
            return
        previous_id = self._selected_item_id()
        query = self.search_edit.text().strip()
        self.candidate_list.clear()
        self._icon_requested.clear()
        category_name = {
            category: label for category, label in self._category_label_pairs()
        }
        for item in self._filtered_items():
            text = item.japanese_name
            if query:
                text = f"{text}  ·  {category_name[item.category]}"
            row = QListWidgetItem(text)
            row.setSizeHint(QSize(0, CANDIDATE_ROW_HEIGHT))
            row.setData(Qt.UserRole, item.item_id)
            row.setToolTip(item.japanese_name)
            self.candidate_list.addItem(row)
            if item.item_id == previous_id:
                self.candidate_list.setCurrentItem(row)
        self._selection_changed()
        self._request_visible_icons()

    def _category_changed(self, _row: int) -> None:
        if self.search_edit.text():
            self.search_edit.clear()
            return
        self._filter_candidates()

    def _request_visible_icons(self, *_args) -> None:
        if self.candidate_list.count() == 0:
            return
        top = self.candidate_list.indexAt(self.candidate_list.viewport().rect().topLeft()).row()
        bottom = self.candidate_list.indexAt(
            self.candidate_list.viewport().rect().bottomLeft()
        ).row()
        top = max(0, top)
        bottom = self.candidate_list.count() - 1 if bottom < 0 else bottom
        for row in range(top, min(bottom + 1, self.candidate_list.count())):
            list_item = self.candidate_list.item(row)
            item_id = list_item.data(Qt.UserRole)
            self._request_item_icon(item_id)

    def _request_item_icon(self, item_id: str) -> None:
        if item_id in self._icon_requested:
            return
        self._icon_requested.add(item_id)
        catalog_item = self.catalog[item_id]
        future = self.icon_cache.request(
            catalog_item.icon_kind, catalog_item.icon_url
        )

        def completed(result_future, *, selected_id=item_id):
            try:
                result = result_future.result()
            except Exception:  # noqa: BLE001  # pragma: no cover
                return
            self._icon_signals.ready.emit(selected_id, str(result.path))

        future.add_done_callback(completed)

    def _apply_icon(self, item_id: str, path: str) -> None:
        icon = QIcon(path)
        if icon.isNull():
            return
        currency_button = self.currency_buttons.get(item_id)
        if currency_button is not None:
            currency_button.setIcon(icon)
        for row in range(self.candidate_list.count()):
            item = self.candidate_list.item(row)
            if item.data(Qt.UserRole) == item_id:
                item.setIcon(icon)
                break

    def _selected_item_id(self) -> str | None:
        selected = self.candidate_list.currentItem() if hasattr(self, "candidate_list") else None
        return selected.data(Qt.UserRole) if selected is not None else None

    def _selected_currency_id(self) -> str | None:
        for item_id, button in self.currency_buttons.items():
            if button.isChecked():
                return item_id
        return None

    def _selection_changed(self, *_args) -> None:
        left_id = self._selected_item_id()
        right_id = self._selected_currency_id()
        pairs = self.store.pairs(self.poe_version)
        reason = ""
        if len(pairs) >= MAX_RATE_PAIRS:
            reason = f"登録上限の{MAX_RATE_PAIRS}件に達しています。"
        elif left_id is None or right_id is None:
            reason = ""
        elif left_id == right_id:
            reason = "同じ通貨同士は登録できません。"
        elif any(
            pair.left_item_id == left_id and pair.right_item_id == right_id
            for pair in pairs
        ):
            reason = "同じ向きのペアはすでに登録されています。"
        self.add_button.setEnabled(
            not reason and left_id is not None and right_id is not None
        )
        self.validation_label.setText(reason)
        if left_id is not None and right_id is not None:
            self.preview_label.setText(
                f"{self.catalog[left_id].japanese_name} ⇔ "
                f"{self.catalog[right_id].japanese_name}"
            )
        else:
            self.preview_label.setText("アイテムと通貨を選択してください")

    def _add_selected_pair(self) -> None:
        left_id = self._selected_item_id()
        right_id = self._selected_currency_id()
        if left_id is None or right_id is None:
            return
        try:
            self.store.add(self.poe_version, left_id, right_id)
        except RatePairValidationError as exc:
            self.validation_label.setText(str(exc))
            return
        self.candidate_list.clearSelection()
        self.candidate_list.setCurrentRow(-1)
        self.currency_group.setExclusive(False)
        for button in self.currency_buttons.values():
            button.setChecked(False)
        self.currency_group.setExclusive(True)
        self._render_registered_pairs()
        self._selection_changed()
        self.on_changed()

    def _render_registered_pairs(self) -> None:
        self.registered_widget.set_rows([])
        self.registered_widget.setMinimumHeight(0)
        while self.registered_layout.count():
            child = self.registered_layout.takeAt(0)
            if child.widget() is not None:
                child.widget().hide()
                child.widget().deleteLater()
        pairs = self.store.pairs(self.poe_version)
        self.title_label.setText(f"レート表示の管理（{len(pairs)} / {MAX_RATE_PAIRS}）")
        if not pairs:
            empty = QLabel("登録済みのレートはありません")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #98A39F; padding: 12px;")
            self.registered_layout.addWidget(empty)
        registered_rows: list[_RegisteredPairRow] = []
        for index, pair in enumerate(pairs):
            row = _RegisteredPairRow(index)
            row.setObjectName(f"registeredPairRow{index}")
            row.setAccessibleName(
                f"{self.catalog[pair.left_item_id].japanese_name}から"
                f"{self.catalog[pair.right_item_id].japanese_name}。"
                "ドラッグして表示順を変更"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(3, 2, 3, 2)
            name = QLabel(
                f"{self.catalog[pair.left_item_id].japanese_name} → "
                f"{self.catalog[pair.right_item_id].japanese_name}"
            )
            name.setObjectName(f"ratePairName{index}")
            name.setToolTip(name.text())
            name.setStyleSheet(f"color: {POETORE_THEME.text};")
            row_layout.addWidget(name, 1)
            up = self._move_button("↑", "上へ移動")
            down = self._move_button("↓", "下へ移動")
            delete = self._icon_button(QStyle.SP_TrashIcon, "削除")
            up.setObjectName(f"ratePairMoveUp{index}")
            down.setObjectName(f"ratePairMoveDown{index}")
            delete.setObjectName(f"ratePairDelete{index}")
            up.setEnabled(index > 0)
            down.setEnabled(index < len(pairs) - 1)
            up.clicked.connect(lambda _checked=False, i=index: self._move_up(i))
            down.clicked.connect(lambda _checked=False, i=index: self._move_down(i))
            delete.clicked.connect(lambda _checked=False, i=index: self._delete(i))
            row_layout.addWidget(up)
            row_layout.addWidget(down)
            row_layout.addWidget(delete)
            self.registered_layout.addWidget(row)
            registered_rows.append(row)
        self.registered_widget.set_rows(registered_rows)
        self.registered_layout.addStretch()
        margins = self.registered_layout.contentsMargins()
        content_height = margins.top() + margins.bottom()
        if registered_rows:
            content_height += sum(row.sizeHint().height() for row in registered_rows)
            content_height += self.registered_layout.spacing() * (len(registered_rows) - 1)
        self.registered_widget.setMinimumHeight(content_height)
        if hasattr(self, "add_button"):
            self._selection_changed()

    def _icon_button(self, icon_type, label: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(self.style().standardIcon(icon_type))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(34, 34)
        button.setToolTip(label)
        button.setAccessibleName(label)
        return button

    def _move_button(self, text: str, label: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(34, 34)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setStyleSheet("""
            QPushButton {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:disabled { color: #000000; }
        """)
        return button

    def _move_up(self, index: int) -> None:
        if self.store.move_up(self.poe_version, index):
            self._render_registered_pairs()
            self.on_changed()

    def _move_down(self, index: int) -> None:
        if self.store.move_down(self.poe_version, index):
            self._render_registered_pairs()
            self.on_changed()

    def _drag_reorder(self, source: int, destination: int) -> None:
        if self.store.move_to(self.poe_version, source, destination):
            self._render_registered_pairs()
            self.on_changed()

    def _delete(self, index: int) -> None:
        self.store.remove(self.poe_version, index)
        self._render_registered_pairs()
        self.on_changed()
