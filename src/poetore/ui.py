from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit, QHeaderView,
)

from .parser import ItemParseError, parse_item_text
from .clipboard import read_item_clipboard
from .merge import merge_normal_and_detailed_copy
from .trade import PriceResult, TradeApiError, TradeStatFilter, resolve_trade_stat_filters, search_prices


class _TradeSignals(QObject):
    completed = Signal(object, object)
    failed = Signal(str)


class PoetoreWindow(QWidget):
    """貼り付け解析だけを行う、Trade API未接続のローカル試作画面。"""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        # PoENavi本体には入力透過（クリックスルー）機能があるため、
        # ぽえとれ側では常にマウス入力を受け取れる状態を明示する。
        self.setWindowFlag(Qt.WindowTransparentForInput, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setEnabled(True)
        self.setWindowTitle("ぽえとれ（ローカル試作・価格検索版）")
        self.resize(860, 720)
        layout = QVBoxLayout(self)
        note = QLabel("PoEでアイテムにカーソルを合わせて Alt+D。日本語名と詳細Modを合成し、現在のPCリーグの相場を自動検索します。")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        paste_button = QPushButton("クリップボードから貼り付け")
        paste_button.clicked.connect(self.paste_from_clipboard)
        buttons.addWidget(paste_button)
        parse_button = QPushButton("解析")
        parse_button.clicked.connect(self.parse_current_text)
        buttons.addWidget(parse_button)
        self.price_button = QPushButton("価格を検索")
        self.price_button.clicked.connect(self.search_current_item)
        buttons.addWidget(self.price_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        splitter = QSplitter(Qt.Horizontal)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("ここにアイテムの詳細コピー文を貼り付けます")
        splitter.addWidget(self.input_edit)
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["項目", "解析結果"])
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.setRootIsDecorated(True)
        self.result_tree.setUniformRowHeights(True)
        self.result_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.result_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        splitter.addWidget(self.result_tree)
        splitter.setSizes([430, 430])
        layout.addWidget(splitter, stretch=1)
        mod_label = QLabel("検索に使うMod（チェックした条件だけ再検索に使用）")
        layout.addWidget(mod_label)
        self.mod_filter_tree = QTreeWidget()
        self.mod_filter_tree.setHeaderLabels(["使用", "種別", "Mod", "最小値"])
        self.mod_filter_tree.setRootIsDecorated(False)
        self.mod_filter_tree.setAlternatingRowColors(True)
        self.mod_filter_tree.setMinimumHeight(145)
        mod_header = self.mod_filter_tree.header()
        mod_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(2, QHeaderView.Stretch)
        mod_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.mod_filter_tree)
        self.price_status = QLabel("価格検索はPoE公式Trade APIのオンライン出品を使います。")
        self.price_status.setWordWrap(True)
        layout.addWidget(self.price_status)
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
        layout.addWidget(self.price_list)
        self._trade_signals = _TradeSignals(self)
        self._trade_signals.completed.connect(self._search_completed)
        self._trade_signals.failed.connect(self._show_price_error)
        self._trade_base_type = None

    def paste_from_clipboard(self):
        self._trade_base_type = None
        self.mod_filter_tree.clear()
        self.input_edit.setPlainText(read_item_clipboard(QApplication.clipboard()))
        self.parse_current_text()

    def capture_from_poe(self):
        """通常コピーと詳細コピーを順番に取得し、日本語名を保って解析する。"""
        from pynput.keyboard import Controller, Key

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
        self.mod_filter_tree.clear()
        self.input_edit.setPlainText(merged_text)
        self.parse_current_text()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_current_item()

    def parse_current_text(self):
        self._parsed_item = None
        try:
            item = parse_item_text(self.input_edit.toPlainText())
        except ItemParseError as exc:
            QMessageBox.warning(self, "解析できませんでした", str(exc))
            return
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

    def search_current_item(self):
        self.parse_current_text()
        item = getattr(self, "_parsed_item", None)
        if item is None:
            return
        self.price_button.setEnabled(False)
        self.price_list.clear()
        self.price_status.setText("現在のPCリーグでオンライン出品を検索中…")
        filters = self._selected_stat_filters()
        needs_initial_filters = self.mod_filter_tree.topLevelItemCount() == 0

        def run():
            try:
                initial_filters = resolve_trade_stat_filters(item) if needs_initial_filters else ()
                effective_filters = initial_filters if needs_initial_filters else filters
                result = search_prices(item, self._trade_base_type, stat_filters=effective_filters)
            except TradeApiError as exc:
                self._trade_signals.failed.emit(str(exc))
            else:
                self._trade_signals.completed.emit(result, initial_filters)

        threading.Thread(target=run, daemon=True).start()

    def _selected_stat_filters(self) -> tuple[TradeStatFilter, ...]:
        filters = []
        for index in range(self.mod_filter_tree.topLevelItemCount()):
            row = self.mod_filter_tree.topLevelItem(index)
            editor = self.mod_filter_tree.itemWidget(row, 3)
            value_text = editor.text().strip() if isinstance(editor, QLineEdit) else row.text(3).strip()
            try:
                value = float(value_text) if value_text else None
            except ValueError:
                value = None
            filters.append(TradeStatFilter(
                row.data(0, Qt.UserRole), row.text(2), value, row.text(1),
                row.checkState(0) == Qt.Checked,
            ))
        return tuple(filters)

    def _populate_stat_filters(self, filters: tuple[TradeStatFilter, ...]):
        self.mod_filter_tree.clear()
        for stat_filter in filters:
            value = "" if stat_filter.min_value is None else f"{stat_filter.min_value:g}"
            row = QTreeWidgetItem(["", stat_filter.kind, stat_filter.text, ""])
            row.setData(0, Qt.UserRole, stat_filter.stat_id)
            row.setCheckState(0, Qt.Checked if stat_filter.enabled else Qt.Unchecked)
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
            self.mod_filter_tree.addTopLevelItem(row)
            editor = QLineEdit(value)
            editor.setPlaceholderText("最小")
            editor.setFixedWidth(80)
            self.mod_filter_tree.setItemWidget(row, 3, editor)

    def _search_completed(self, result: PriceResult, initial_filters):
        if initial_filters:
            self._populate_stat_filters(initial_filters)
        self._show_price_result(result)

    def _show_price_result(self, result: PriceResult):
        self.price_button.setEnabled(True)
        if not result.listings:
            self.price_status.setText(f"{result.league}: 検索候補{result.total}件。価格付き出品は取得できませんでした。")
            return
        medians = " / ".join(
            f"{value:g} {currency}" for currency, value in result.median_by_currency().items()
        )
        samples = ", ".join(f"{row.amount:g} {row.currency}" for row in result.listings[:5])
        self.price_status.setText(
            f"{result.league}: 候補{result.total}件 / 取得{len(result.listings)}件 | "
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


def show_poetore_window(owner, activate=True):
    """ownerが参照を保持し、二重起動せず独立表示できる公開エントリ。"""
    window = getattr(owner, "_poetore_window", None)
    if window is None:
        # QWidgetの親子関係を持たせると、本体のdisabled/入力透過状態が
        # 別ウィンドウへ波及し得る。寿命はownerの参照で管理し、UIは独立させる。
        window = PoetoreWindow()
        owner._poetore_window = window
    if activate:
        window.show()
        window.raise_()
        window.activateWindow()
    return window
