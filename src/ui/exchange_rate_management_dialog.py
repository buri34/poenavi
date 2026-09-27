"""Management dialog for the main window's custom Currency Exchange rates."""

from __future__ import annotations

from collections.abc import Callable, Collection

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStyle,
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


class _IconSignals(QObject):
    ready = Signal(str, str)


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
            QRadioButton {{ color: {theme.text}; spacing: 8px; padding: 5px; }}
            QRadioButton::indicator {{
                width: 15px; height: 15px; border: 2px solid #77827E;
                border-radius: 8px; background: transparent;
            }}
            QRadioButton::indicator:checked {{
                background: {theme.accent}; border-color: {theme.accent};
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
        self.registered_scroll.setWidgetResizable(True)
        self.registered_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.registered_scroll.setFixedHeight(175)
        self.registered_widget = QWidget()
        self.registered_layout = QVBoxLayout(self.registered_widget)
        self.registered_layout.setContentsMargins(6, 6, 6, 6)
        self.registered_layout.setSpacing(5)
        self.registered_scroll.setWidget(self.registered_widget)
        root.addWidget(self.registered_scroll)

        search_row = QHBoxLayout()
        search_label = QLabel("検索")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("日本語名で検索")
        self.search_edit.setAccessibleName("交換対象の日本語名検索")
        self.search_edit.textChanged.connect(self._filter_candidates)
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit, 1)
        root.addLayout(search_row)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(10)
        self.category_list = QListWidget()
        self.category_list.setAccessibleName("カテゴリ")
        self.category_list.setFixedWidth(160)
        self.category_list.addItem("すべて")
        self.category_list.addItems(category_labels(self.poe_version))
        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self._filter_candidates)
        selection_row.addWidget(self.category_list)

        self.candidate_list = QListWidget()
        self.candidate_list.setAccessibleName("交換対象")
        self.candidate_list.setIconSize(QSize(28, 28))
        self.candidate_list.currentItemChanged.connect(self._selection_changed)
        self.candidate_list.verticalScrollBar().valueChanged.connect(
            self._request_visible_icons
        )
        selection_row.addWidget(self.candidate_list, 1)

        currency_panel = QFrame()
        currency_layout = QVBoxLayout(currency_panel)
        currency_layout.setContentsMargins(8, 0, 0, 0)
        currency_title = QLabel("基準通貨")
        currency_title.setStyleSheet("font-weight: bold;")
        currency_layout.addWidget(currency_title)
        self.currency_group = QButtonGroup(self)
        self.currency_buttons: dict[str, QRadioButton] = {}
        for item_id in BASE_CURRENCY_IDS:
            name = self.catalog[item_id].japanese_name
            radio = QRadioButton(name)
            radio.setAccessibleName(f"基準通貨 {name}")
            self.currency_group.addButton(radio)
            self.currency_buttons[item_id] = radio
            currency_layout.addWidget(radio)
            radio.toggled.connect(self._selection_changed)
        currency_layout.addStretch()
        selection_row.addWidget(currency_panel)
        root.addLayout(selection_row, 1)

        self.preview_label = QLabel("追加するペアを選択してください")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("font-weight: bold;")
        root.addWidget(self.preview_label)
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("color: #D4AAA5; font-size: 11px;")
        root.addWidget(self.validation_label)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.add_button = QPushButton("追加")
        self.add_button.setAccessibleName("選択したレートを追加")
        self.add_button.clicked.connect(self._add_selected_pair)
        action_row.addWidget(self.add_button)
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        action_row.addWidget(self.close_button)
        root.addLayout(action_row)

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
            row.setData(Qt.UserRole, item.item_id)
            row.setToolTip(item.japanese_name)
            self.candidate_list.addItem(row)
            if item.item_id == previous_id:
                self.candidate_list.setCurrentItem(row)
        self._selection_changed()
        self._request_visible_icons()

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
            if item_id in self._icon_requested:
                continue
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
            reason = "登録上限の5件に達しています。"
        elif left_id is None or right_id is None:
            reason = "交換対象と基準通貨を選択してください。"
        elif left_id == right_id:
            reason = "同じ通貨同士は登録できません。"
        elif any(
            pair.left_item_id == left_id and pair.right_item_id == right_id
            for pair in pairs
        ):
            reason = "同じ向きのペアはすでに登録されています。"
        self.add_button.setEnabled(not reason)
        self.validation_label.setText(reason)
        if left_id is not None and right_id is not None:
            self.preview_label.setText(
                f"{self.catalog[left_id].japanese_name} → "
                f"{self.catalog[right_id].japanese_name}"
            )
        else:
            self.preview_label.setText("追加するペアを選択してください")

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
        while self.registered_layout.count():
            child = self.registered_layout.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()
        pairs = self.store.pairs(self.poe_version)
        self.title_label.setText(f"レート表示の管理（{len(pairs)} / {MAX_RATE_PAIRS}）")
        if not pairs:
            empty = QLabel("登録済みのレートはありません")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #98A39F; padding: 12px;")
            self.registered_layout.addWidget(empty)
        for index, pair in enumerate(pairs):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(3, 2, 3, 2)
            name = QLabel(
                f"{self.catalog[pair.left_item_id].japanese_name} → "
                f"{self.catalog[pair.right_item_id].japanese_name}"
            )
            name.setToolTip(name.text())
            row_layout.addWidget(name, 1)
            up = self._icon_button(QStyle.SP_ArrowUp, "上へ移動")
            down = self._icon_button(QStyle.SP_ArrowDown, "下へ移動")
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
        self.registered_layout.addStretch()
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

    def _move_up(self, index: int) -> None:
        if self.store.move_up(self.poe_version, index):
            self._render_registered_pairs()
            self.on_changed()

    def _move_down(self, index: int) -> None:
        if self.store.move_down(self.poe_version, index):
            self._render_registered_pairs()
            self.on_changed()

    def _delete(self, index: int) -> None:
        self.store.remove(self.poe_version, index)
        self._render_registered_pairs()
        self.on_changed()
