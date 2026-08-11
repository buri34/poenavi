from __future__ import annotations

from functools import partial

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QHeaderView, QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from src.poetore.clipboard import clipboard_change_token, read_item_clipboard
from src.poetore.map_check import (
    DEFAULT_DECISIONS_BY_REF, decision_for, entries_by_stat_id,
    is_map_check_item, load_map_mod_catalog, next_color_decision,
    normalized_map_check_config, set_decision,
)
from src.poetore.parser import ItemParseError, parse_item_text
from src.poetore.window_position import (
    capture_placement_context, position_for_context_at_cursor_y,
)
from src.utils.window_focus import (
    focus_window, get_foreground_window, is_path_of_exile_window,
)


_COLORS = {
    "d": ("☠", "#8b1e25"),
    "w": ("⚠", "#a85a13"),
    "g": ("✓", "#27633a"),
    "-": ("", "#1A1F21"),
    "s": ("", "#1A1F21"),
}

_FONT_SIZES = {"small": 11, "medium": 13, "large": 16}


class MapModManagerDialog(QDialog):
    config_changed = Signal(dict)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = normalized_map_check_config(config)
        self.catalog = load_map_mod_catalog()
        self.setWindowTitle("Map Mod管理")
        self.resize(820, 680)
        self.setStyleSheet(
            "QDialog,QWidget{background:#111416;color:#E6ECEA;}"
            "QLineEdit,QTableWidget{background:#1A1F21;color:#E6ECEA;border:1px solid #3A4245;}"
            "QPushButton{padding:5px;background:#1A1F21;color:#E6ECEA;border:1px solid #3A4245;}"
            "QPushButton:hover{border-color:#65FFCA;}"
            "QPushButton:checked{border:2px solid #65FFCA;}"
        )
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("プロファイル:"))
        self.profile_buttons = []
        for profile in (1, 2, 3):
            button = QPushButton(str(profile))
            button.setCheckable(True)
            button.clicked.connect(partial(self._select_profile, profile))
            controls.addWidget(button)
            self.profile_buttons.append(button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Modを検索…")
        self.search.textChanged.connect(self._refresh)
        controls.addWidget(self.search, 1)
        self.selected_only = QCheckBox("設定済みのみ表示")
        self.selected_only.toggled.connect(self._refresh)
        controls.addWidget(self.selected_only)
        self.show_new = QCheckBox("未確認Modを表示")
        self.show_new.setChecked(self.config["show_new_stats"])
        self.show_new.toggled.connect(self._set_show_new)
        controls.addWidget(self.show_new)
        root.addLayout(controls)
        self.count_label = QLabel()
        root.addWidget(self.count_label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Map Mod", "危険", "警告", "有利", "解除"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch,
        )
        root.addWidget(self.table, 1)
        close = QPushButton("閉じる")
        close.clicked.connect(self.accept)
        root.addWidget(close)
        self._select_profile(self.config["profile"])

    def _set_show_new(self, checked):
        self.config["show_new_stats"] = bool(checked)
        self._save()

    def _select_profile(self, profile, _checked=False):
        self.config["profile"] = profile
        for index, button in enumerate(self.profile_buttons, 1):
            button.setChecked(index == profile)
        self._refresh()
        self._save()

    def _rows(self):
        rows = list(self.catalog)
        known_refs = {entry.ref for entry in rows}
        for ref in DEFAULT_DECISIONS_BY_REF:
            if ref not in known_refs:
                rows.append(type("Outdated", (), {
                    "key": f"legacy:{ref}", "ref": ref, "japanese": ref,
                    "scope": "outdated", "stat_ids": (),
                })())
        query = self.search.text().strip().casefold()
        result = []
        for entry in rows:
            decision = decision_for(self.config, entry.key)
            if self.selected_only.isChecked() and decision in {"-", "s"}:
                continue
            tag = {"heist_exclusive": "Heist限定", "ubermap_exclusive": "Uber Map限定",
                   "outdated": "更新確認が必要"}.get(entry.scope, "")
            searchable = f"{entry.japanese} {entry.ref} {tag}".casefold()
            if query and query not in searchable:
                continue
            result.append((entry, tag))
        scope_order = {
            "normal": 0,
            "ubermap_exclusive": 1,
            "heist_exclusive": 2,
            "outdated": 3,
        }
        result.sort(key=lambda row: scope_order.get(row[0].scope, 3))
        return result

    def _refresh(self):
        rows = self._rows()
        self.table.setRowCount(len(rows))
        for row, (entry, tag) in enumerate(rows):
            text = f"[{tag}] {entry.japanese}" if tag else entry.japanese
            self.table.setItem(row, 0, QTableWidgetItem(text))
            current = decision_for(self.config, entry.key)
            for column, (label, value, color) in enumerate((
                ("☠", "d", "#8b1e25"), ("⚠", "w", "#a85a13"),
                ("✓", "g", "#27633a"), ("×", "-", "#1A1F21"),
            ), 1):
                button = QPushButton(label)
                button.setCheckable(True)
                button.setChecked(current == value)
                button.setStyleSheet(f"QPushButton{{background:{color};}}")
                button.clicked.connect(partial(self._choose, entry.key, value))
                self.table.setCellWidget(row, column, button)
        self.count_label.setText(f"{len(rows)}件（全{len(self.catalog)}件）")

    def _choose(self, key, value, _checked=False):
        set_decision(self.config, key, value)
        self._save()
        self._refresh()

    def _save(self):
        self.config_changed.emit(dict(self.config))


class MapCheckWindow(QDialog):
    config_changed = Signal(dict)

    DEFAULT_WIDTH = 560
    DEFAULT_HEIGHT = 360
    MIN_HEIGHT = 180
    SCREEN_EDGE_MARGIN = 16

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = normalized_map_check_config(config)
        self._font_size_name = str(config.get("_font_size", "medium")).casefold()
        self._capture_generation = 0
        self._copy_started = False
        self._keyboard = None
        self._placement_context = None
        self.setWindowTitle("Map Check")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setStyleSheet(
            "QDialog,QWidget{background:#111416;color:#E6ECEA;}"
            "QPushButton{padding:7px;background:#1A1F21;color:#E6ECEA;border:1px solid #3A4245;}"
            "QPushButton:hover{border-color:#65FFCA;}"
            "QPushButton:checked{border:2px solid #65FFCA;}"
        )
        self._apply_font_size()
        self.root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel("Map Check")
        self.title.setStyleSheet("font-size:15px;font-weight:bold;")
        header.addWidget(self.title, 1)
        header.addWidget(QLabel("プロファイル:"))
        self.profile_buttons = []
        for profile in (1, 2, 3):
            button = QPushButton(str(profile))
            button.setFixedWidth(32)
            button.setCheckable(True)
            button.clicked.connect(partial(self._select_profile, profile))
            header.addWidget(button)
            self.profile_buttons.append(button)
        close = QPushButton("×")
        close.setFixedWidth(32)
        close.clicked.connect(self.close)
        header.addWidget(close)
        self.root.addLayout(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.scroll.setWidget(self.body)
        self.root.addWidget(self.scroll, 1)
        self._select_profile(self.config["profile"], save=False)

    def reload_config(self, config):
        self.config = normalized_map_check_config(config)
        self._font_size_name = str(config.get("_font_size", "medium")).casefold()
        self._apply_font_size()
        self._select_profile(self.config["profile"], save=False)

    def _apply_font_size(self):
        size = _FONT_SIZES.get(self._font_size_name, _FONT_SIZES["medium"])
        self.setStyleSheet(
            self.styleSheet() + f"QLabel,QPushButton{{font-size:{size}px;}}"
        )

    def capture_from_poe(self):
        from pynput.keyboard import Controller, Key
        self._placement_context = capture_placement_context()
        foreground = get_foreground_window()
        self._poe_window_hwnd = (
            foreground if is_path_of_exile_window(foreground) else None
        )
        self._keyboard = Controller()
        self._capture_generation += 1
        generation = self._capture_generation
        self._copy_started = False
        self._copy_keys = (Key.ctrl, "c")
        QTimer.singleShot(250, lambda: self._start_copy(generation))

    def capture_hotkey_released(self):
        self._start_copy(self._capture_generation)

    def _start_copy(self, generation):
        from src.utils.internal_key_input import internal_key_input

        if generation != self._capture_generation or self._copy_started:
            return
        self._copy_started = True
        before = clipboard_change_token(QApplication.clipboard())
        with internal_key_input():
            for key in self._copy_keys:
                self._keyboard.press(key)
            for key in reversed(self._copy_keys):
                self._keyboard.release(key)
        self._wait_clipboard(before, generation, 0)

    def _wait_clipboard(self, before, generation, elapsed):
        if generation != self._capture_generation:
            return
        if clipboard_change_token(QApplication.clipboard()) != before or elapsed >= 300:
            self._consume_clipboard()
            return
        QTimer.singleShot(10, lambda: self._wait_clipboard(before, generation, elapsed + 10))

    def _consume_clipboard(self):
        try:
            item = parse_item_text(read_item_clipboard(QApplication.clipboard()))
        except ItemParseError:
            QMessageBox.warning(self.parentWidget(), "Map Check", "アイテムを取得できませんでした。")
            return
        if not is_map_check_item(item):
            QMessageBox.information(self.parentWidget(), "Map Check", "Map系アイテムではありません。")
            return
        self._item = item
        self._render(item)
        context = self._placement_context or capture_placement_context()
        self._resize_to_content(context)
        self.move(position_for_context_at_cursor_y(context, self.size()))
        self.show()
        self.raise_()
        self.activateWindow()

    def _clear_body(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render(self, item):
        self.title.setText(item.name or item.base_type or "Map Check")
        self._clear_body()
        lookup = entries_by_stat_id()
        for modifier in item.modifiers:
            entry = lookup.get(modifier.stat_id or "")
            if entry is None:
                row = QLabel(f"未認識Mod — {modifier.text}")
                row.setStyleSheet("padding:7px;color:#efb366;")
                self.body_layout.addWidget(row)
                continue
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            button = QPushButton()
            button.setProperty("map_mod_key", entry.key)
            button.setProperty("map_mod_text", modifier.text)
            button.clicked.connect(partial(self._cycle_entry, entry.key))
            row_layout.addWidget(button, 1)
            if self.config.get("show_new_stats"):
                seen = QPushButton()
                seen.setFixedWidth(72)
                seen.setProperty("map_seen_key", entry.key)
                seen.clicked.connect(partial(self._toggle_seen, entry.key))
                row_layout.addWidget(seen)
                self._style_seen_button(seen, entry.key)
            self.body_layout.addWidget(row_widget)
            self._style_mod_button(button, entry.key, modifier.text)
        if not item.modifiers:
            self.body_layout.addWidget(QLabel("認識できるMap Modがありません。"))
        self.body_layout.addStretch()

    def _content_height(self):
        """Return the body height required by every rendered Map Mod row."""
        margins = self.body_layout.contentsMargins()
        height = margins.top() + margins.bottom()
        visible_items = []
        for index in range(self.body_layout.count()):
            layout_item = self.body_layout.itemAt(index)
            widget = layout_item.widget()
            if widget is not None and not widget.isHidden():
                visible_items.append(widget)
                height += widget.sizeHint().height()
        if visible_items:
            height += self.body_layout.spacing() * (len(visible_items) - 1)
        return height

    def _resize_to_content(self, context):
        """Grow to show all rows, retaining scrolling only at the screen limit."""
        self.body_layout.activate()
        root_margins = self.root.contentsMargins()
        header = self.root.itemAt(0).layout()
        chrome_height = (
            root_margins.top()
            + root_margins.bottom()
            + header.sizeHint().height()
            + self.root.spacing()
            + self.scroll.frameWidth() * 2
        )
        desired_height = max(self.MIN_HEIGHT, chrome_height + self._content_height())
        available_height = max(
            self.MIN_HEIGHT,
            context.target_rect.height() - self.SCREEN_EDGE_MARGIN * 2,
        )
        self.resize(self.DEFAULT_WIDTH, min(desired_height, available_height))

    def _style_mod_button(self, button, key, text):
        decision = decision_for(self.config, key)
        icon, color = _COLORS[decision]
        button.setText(f"{icon}  {text}".strip())
        button.setStyleSheet(f"QPushButton{{background:{color};text-align:left;padding:9px;}}")

    def _cycle_entry(self, key, _checked=False):
        set_decision(self.config, key, next_color_decision(decision_for(self.config, key)))
        self.config_changed.emit(dict(self.config))
        for button in self.body.findChildren(QPushButton):
            if button.property("map_mod_key") == key:
                self._style_mod_button(button, key, button.property("map_mod_text"))
        self._refresh_seen_buttons(key)

    def _toggle_seen(self, key, _checked=False):
        if not self.config.get("show_new_stats"):
            return
        current = decision_for(self.config, key)
        if current not in {"-", "s"}:
            return
        set_decision(self.config, key, "s" if current == "-" else "-")
        self.config_changed.emit(dict(self.config))
        self._refresh_seen_buttons(key)

    def _refresh_seen_buttons(self, key):
        for button in self.body.findChildren(QPushButton):
            if button.property("map_seen_key") == key:
                self._style_seen_button(button, key)

    def _style_seen_button(self, button, key):
        decision = decision_for(self.config, key)
        if decision == "-":
            button.setText("未確認")
            button.setToolTip("クリックして、このModを確認済みにします")
            button.setEnabled(True)
        elif decision == "s":
            button.setText("確認済")
            button.setToolTip("クリックして、未確認の状態に戻します")
            button.setEnabled(True)
        else:
            button.setText("設定済")
            button.setToolTip("警告・危険・有利のいずれかに設定済みです")
            button.setEnabled(False)

    def _select_profile(self, profile, _checked=False, save=True):
        self.config["profile"] = profile
        for index, button in enumerate(self.profile_buttons, 1):
            button.setChecked(index == profile)
        if save:
            self.config_changed.emit(dict(self.config))
        if hasattr(self, "_item"):
            self._render(self._item)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            target = getattr(self, "_poe_window_hwnd", None)
            self.close()
            if target is not None:
                QTimer.singleShot(0, lambda: focus_window(target))
            return
        super().keyPressEvent(event)

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate and self.isVisible():
            QTimer.singleShot(0, self.close)
        return super().event(event)
