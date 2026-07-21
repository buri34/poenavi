from __future__ import annotations

import threading
from dataclasses import replace

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
    QSizeGrip, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit, QHeaderView,
)

from .parser import ItemParseError, parse_item_text
from .clipboard import read_item_clipboard
from .merge import merge_normal_and_detailed_copy
from .window_position import PlacementContext, capture_placement_context, position_for_context
from .trade import (
    PRESET_BASE, PRESET_FINISHED, PriceResult, TradeApiError, TradeStatFilter,
    available_trade_presets, default_trade_currency, resolve_trade_stat_filters, search_prices,
    unique_candidates,
    unique_variants, unresolved_modifier_warnings,
)


class _TradeSignals(QObject):
    completed = Signal(object, object)
    failed = Signal(str)
    unique_candidates_ready = Signal(object)
    unique_variants_ready = Signal(object)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # PoENavi本体には入力透過（クリックスルー）機能があるため、
        # ぽえとれ側では常にマウス入力を受け取れる状態を明示する。
        self.setWindowFlag(Qt.WindowTransparentForInput, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setEnabled(True)
        self.setWindowTitle("ぽえとれ（ローカル試作・価格検索版）")
        self.resize(860, 720)
        self._placement_context: PlacementContext | None = None
        self._focus_signal_connected = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.addWidget(_PoetoreTitleBar(self))
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
        self.trade_url_button = QPushButton("日本語公式Tradeで開く")
        self.trade_url_button.setEnabled(False)
        self.trade_url_button.clicked.connect(self._open_trade_url)
        buttons.addWidget(self.trade_url_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        search_options = QHBoxLayout()
        search_options.addWidget(QLabel("検索用途:"))
        self.trade_preset_combo = QComboBox()
        self.trade_preset_combo.addItem("完成品", PRESET_FINISHED)
        self.trade_preset_combo.currentIndexChanged.connect(self._trade_preset_changed)
        search_options.addWidget(self.trade_preset_combo)
        search_options.addWidget(QLabel("取引方式:"))
        self.trade_status_combo = QComboBox()
        self.trade_status_combo.addItem("インスタントバイアウトのみ", "instant")
        self.trade_status_combo.addItem("インスタント＋対面", "available")
        self.trade_status_combo.addItem("対面トレードのみ", "online")
        self.trade_status_combo.addItem("オフライン出品も含む", "offline")
        search_options.addWidget(self.trade_status_combo)
        search_options.addWidget(QLabel("価格通貨:"))
        self.trade_currency_combo = QComboBox()
        self.trade_currency_combo.addItem("すべての通貨", "any")
        self.trade_currency_combo.addItem("カオスオーブのみ", "chaos")
        self.trade_currency_combo.addItem("ディヴァインオーブのみ", "divine")
        self.trade_currency_combo.addItem("カオス＋ディヴァイン", "chaos_divine")
        search_options.addWidget(self.trade_currency_combo)
        self.unique_name_label = QLabel("未鑑定ユニーク候補:")
        self.unique_name_combo = QComboBox()
        self.unique_name_label.hide()
        self.unique_name_combo.hide()
        search_options.addWidget(self.unique_name_label)
        search_options.addWidget(self.unique_name_combo)
        self.unique_variant_label = QLabel("ユニークVariant:")
        self.unique_variant_combo = QComboBox()
        self.unique_variant_label.hide()
        self.unique_variant_combo.hide()
        search_options.addWidget(self.unique_variant_label)
        search_options.addWidget(self.unique_variant_combo)
        search_options.addStretch()
        layout.addLayout(search_options)

        item_state_options = QHBoxLayout()
        item_state_options.addWidget(QLabel("コラプト条件:"))
        self.corrupted_combo = QComboBox()
        self.corrupted_combo.addItem("未コラプトのみ", False)
        self.corrupted_combo.addItem("コラプト品含む", True)
        item_state_options.addWidget(self.corrupted_combo)
        item_state_options.addWidget(QLabel("スプリット条件:"))
        self.split_combo = QComboBox()
        self.split_combo.addItem("非スプリットのみ", False)
        self.split_combo.addItem("スプリット品含む", True)
        item_state_options.addWidget(self.split_combo)
        item_state_options.addWidget(QLabel("出品期間:"))
        self.listed_within_combo = QComboBox()
        for label, value in (
            ("指定なし", "any"), ("24時間以内", "1day"), ("3日以内", "3days"),
            ("1週間以内", "1week"), ("2週間以内", "2weeks"),
            ("1か月以内", "1month"), ("2か月以内", "2months"),
        ):
            self.listed_within_combo.addItem(label, value)
        item_state_options.addWidget(self.listed_within_combo)
        item_state_options.addStretch()
        layout.addLayout(item_state_options)

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
        self.mod_filter_tree.setHeaderLabels(["使用", "種別", "Mod", "最小値", "最大値", "判断・詳細", "論理"])
        self.mod_filter_tree.setRootIsDecorated(False)
        self.mod_filter_tree.setAlternatingRowColors(True)
        self.mod_filter_tree.setMinimumHeight(145)
        mod_header = self.mod_filter_tree.header()
        mod_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(2, QHeaderView.Stretch)
        mod_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        mod_header.setSectionResizeMode(5, QHeaderView.Stretch)
        mod_header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        layout.addWidget(self.mod_filter_tree)
        self.mod_warning = QLabel("")
        self.mod_warning.setWordWrap(True)
        self.mod_warning.setStyleSheet("color: #d6a84b;")
        self.mod_warning.hide()
        layout.addWidget(self.mod_warning)
        self.price_status = QLabel("価格検索はPoE公式Trade APIを使います。初期設定はインスタントバイアウトのみです。")
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
        resize_row = QHBoxLayout()
        resize_row.addStretch()
        resize_row.addWidget(QSizeGrip(self))
        layout.addLayout(resize_row)
        self._trade_signals = _TradeSignals(self)
        self._trade_signals.completed.connect(self._search_completed)
        self._trade_signals.failed.connect(self._show_price_error)
        self._trade_signals.unique_candidates_ready.connect(self._show_unique_candidates)
        self._trade_signals.unique_variants_ready.connect(self._show_unique_variants)
        self._trade_base_type = None
        self._trade_item_name = None
        self._preset_item_key = None
        self._currency_item_key = None
        self._state_item_key = None
        self._unique_selector_item_key = None
        self._last_trade_url = ""
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

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
        old_belongs = old is self or (
            isinstance(old, QWidget) and self.isAncestorOf(old)
        )
        new_belongs = new is self or (
            isinstance(new, QWidget) and self.isAncestorOf(new)
        )
        if self.isVisible() and old_belongs and not new_belongs:
            self.close()

    def showEvent(self, event):
        if not self._focus_signal_connected:
            QApplication.instance().focusChanged.connect(self._close_when_focus_leaves_panel)
            self._focus_signal_connected = True
        super().showEvent(event)

    def closeEvent(self, event):
        if self._focus_signal_connected:
            QApplication.instance().focusChanged.disconnect(self._close_when_focus_leaves_panel)
            self._focus_signal_connected = False
        super().closeEvent(event)

    def paste_from_clipboard(self):
        self._trade_base_type = None
        self._trade_item_name = None
        self._preset_item_key = None
        self._reset_unique_candidates()
        self.mod_filter_tree.clear()
        self.input_edit.setPlainText(read_item_clipboard(QApplication.clipboard()))
        self.parse_current_text()

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
        include_corrupted = bool(self.corrupted_combo.currentData())
        include_split = bool(self.split_combo.currentData())
        self.price_status.setText(
            f"現在のPCリーグで「{preset_label} / {trade_status_label} / "
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
                    item, self._trade_base_type, stat_filters=effective_filters,
                    trade_status=trade_status, trade_name=resolved_trade_name,
                    preset=preset,
                    trade_currency=trade_currency,
                    include_corrupted=include_corrupted,
                    include_split=include_split,
                    trade_discriminator=str(selected_discriminator) if selected_discriminator else None,
                    listed_within=listed_within,
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
        self.trade_preset_combo.blockSignals(True)
        self.trade_preset_combo.clear()
        self.trade_preset_combo.addItem("完成品", PRESET_FINISHED)
        if PRESET_BASE in presets:
            self.trade_preset_combo.addItem("クラフトベース", PRESET_BASE)
        self.trade_preset_combo.setCurrentIndex(0)
        self.trade_preset_combo.setEnabled(len(presets) > 1)
        self.trade_preset_combo.setToolTip(
            "未完成でクラフト価値がある装備は、完成品とクラフトベースを切り替えて検索できます。"
        )
        self.trade_preset_combo.blockSignals(False)
        self.mod_filter_tree.clear()

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
        self.corrupted_combo.setCurrentIndex(1 if "corrupted" in item.flags else 0)
        self.split_combo.setCurrentIndex(1 if "split" in item.flags else 0)
        is_equipment = item.category in {
            "weapon", "armour", "accessory", "cluster_jewel", "jewel", "abyss_jewel",
        }
        self.corrupted_combo.setEnabled(is_equipment)
        self.split_combo.setEnabled(is_equipment)

    def _trade_preset_changed(self):
        if not hasattr(self, "mod_filter_tree"):
            return
        self.mod_filter_tree.clear()
        self.price_list.clear()
        preset = str(self.trade_preset_combo.currentData() or PRESET_FINISHED)
        if preset == PRESET_BASE:
            self.price_status.setText(
                "クラフトベースとして、ベースタイプとアイテムレベルを中心に検索します。"
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
        window = PoetoreWindow()
        owner._poetore_window = window
    if activate:
        window.show_at_context()
    return window
