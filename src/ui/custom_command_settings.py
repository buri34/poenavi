from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from src.ui.app_theme import POENAVI_THEME
from src.ui.settings_dialog import HotkeyButton


def normalized_custom_commands(value) -> list[dict]:
    result = []
    if not isinstance(value, list):
        return result
    for row in value:
        if not isinstance(row, dict):
            continue
        result.append({
            "enabled": bool(row.get("enabled", True)),
            "name": str(row.get("name", "")).strip(),
            "hotkey": str(row.get("hotkey", "")).strip() or "none",
            "command": str(row.get("command", "")).strip(),
        })
    return result


def custom_command_hotkeys(commands) -> dict[str, str]:
    return {
        f"custom_command:{index}": row["hotkey"]
        for index, row in enumerate(normalized_custom_commands(commands))
        if row["enabled"] and row["command"].startswith("/")
    }


class CustomCommandSettingsWidget(QWidget):
    ROW_HEIGHT = 38

    def __init__(self, commands=None, parent=None, theme=None):
        super().__init__(parent)
        self.theme = theme or POENAVI_THEME
        layout = QVBoxLayout(self)
        note = QLabel(
            "PoEチャットへ送るコマンドを登録します。ホットキーは Ctrl+H のように入力してください。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["有効", "名前", "ホットキー", "コマンド"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(f"""
            QTableWidget {{ background: {self.theme.background}; color: {self.theme.text};
                gridline-color: {self.theme.accent}; border: 1px solid {self.theme.accent}; }}
            QTableWidget::item {{ background: {self.theme.panel}; color: {self.theme.text}; padding: 4px; }}
            QTableWidget::item:selected {{ background: {self.theme.accent}; color: {self.theme.background}; }}
            QHeaderView::section {{ background: {self.theme.panel}; color: {self.theme.text};
                border: 1px solid {self.theme.accent}; padding: 5px; }}
        """)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        add = QPushButton("追加")
        remove = QPushButton("選択行を削除")
        add.clicked.connect(self.add_row)
        remove.clicked.connect(self.remove_selected_rows)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        layout.addLayout(buttons)
        for command in normalized_custom_commands(commands):
            self.add_row(command)

    def add_row(self, command=None):
        command = command or {"enabled": True, "name": "", "hotkey": "none", "command": "/"}
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, self.ROW_HEIGHT)
        enabled = QCheckBox()
        enabled.setChecked(bool(command.get("enabled", True)))
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(enabled)
        holder_layout.setAlignment(enabled, Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 0, holder)
        self.table.setItem(row, 1, QTableWidgetItem(str(command.get("name", ""))))
        hotkey = HotkeyButton(str(command.get("hotkey", "none")))
        hotkey.setStyleSheet(
            f"QPushButton{{background:{self.theme.panel};color:{self.theme.text};"
            f"border:1px solid {self.theme.accent};padding:5px;}}"
            f"QPushButton:checked{{background:{self.theme.accent};color:{self.theme.background};}}"
        )
        self.table.setCellWidget(row, 2, hotkey)
        self.table.setItem(row, 3, QTableWidgetItem(str(command.get("command", "/"))))

    def remove_selected_rows(self):
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def commands(self):
        rows = []
        for row in range(self.table.rowCount()):
            holder = self.table.cellWidget(row, 0)
            enabled = holder.findChild(QCheckBox).isChecked()
            text = lambda column: (self.table.item(row, column).text().strip() if self.table.item(row, column) else "")
            hotkey = self.table.cellWidget(row, 2).key_text
            rows.append({"enabled": enabled, "name": text(1), "hotkey": hotkey or "none", "command": text(3)})
        return rows

    def validate(self, existing_hotkeys: dict[str, str]) -> bool:
        from src.utils.global_hotkeys import find_duplicate_hotkeys
        commands = self.commands()
        for index, row in enumerate(commands, 1):
            if not row["enabled"]:
                continue
            if not row["name"] or not row["hotkey"] or row["hotkey"].casefold() == "none" or not row["command"].startswith("/"):
                QMessageBox.warning(self, "任意コマンド設定", f"{index}行目は名前・ホットキーを入力し、コマンドを / から始めてください。")
                return False
        combined = dict(existing_hotkeys)
        combined.update(custom_command_hotkeys(commands))
        duplicates = find_duplicate_hotkeys(combined)
        if duplicates:
            keys = "、".join(duplicates)
            QMessageBox.warning(self, "ホットキー重複", f"既存機能または任意コマンドと重複しています: {keys}")
            return False
        return True
