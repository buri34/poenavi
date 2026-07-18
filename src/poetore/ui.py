from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit, QHeaderView,
)

from .parser import ItemParseError, parse_item_text
from .clipboard import read_item_clipboard
from .merge import merge_normal_and_detailed_copy


class PoetoreWindow(QWidget):
    """貼り付け解析だけを行う、Trade API未接続のローカル試作画面。"""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        # PoENavi本体には入力透過（クリックスルー）機能があるため、
        # ぽえとれ側では常にマウス入力を受け取れる状態を明示する。
        self.setWindowFlag(Qt.WindowTransparentForInput, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setEnabled(True)
        self.setWindowTitle("ぽえとれ（ローカル試作・Alt+D対応版）")
        self.resize(860, 620)
        layout = QVBoxLayout(self)
        note = QLabel("PoEでアイテムにカーソルを合わせて Alt+D。日本語名と詳細Modを自動で合成します。価格検索APIは未接続です。")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        paste_button = QPushButton("クリップボードから貼り付け")
        paste_button.clicked.connect(self.paste_from_clipboard)
        buttons.addWidget(paste_button)
        parse_button = QPushButton("解析")
        parse_button.clicked.connect(self.parse_current_text)
        buttons.addWidget(parse_button)
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

    def paste_from_clipboard(self):
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
            merged_text = merge_normal_and_detailed_copy(self._normal_copy_text, detailed_text)
        except ItemParseError as exc:
            QMessageBox.warning(self, "取り込めませんでした", f"PoEのアイテムコピーを取得できませんでした。\n{exc}")
            return
        self.input_edit.setPlainText(merged_text)
        self.parse_current_text()
        self.show()
        self.raise_()
        self.activateWindow()

    def parse_current_text(self):
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
