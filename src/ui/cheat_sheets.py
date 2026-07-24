"""ユーザー登録画像をゲーム上へ表示するCheat sheet機能。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QPoint, QRect, Signal
from PySide6.QtGui import QCursor, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSlider,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import Styles
from src.poetore.window_position import path_of_exile_client_rect
from src.utils.config_manager import ConfigManager
from src.utils.i18n import tr_ui


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
DEFAULT_CHEAT_SHEET_CONFIG = {
    "images": [],
    "selected_id": "",
    "opacity": 100,
    "position": {"x": 120, "y": 120},
    "position_initialized": False,
    "width": 900,
    "height": 650,
}


def cheat_sheet_directory() -> Path:
    path = ConfigManager.get_user_data_dir() / "cheat_sheets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def import_cheat_sheet_image(source: str | Path) -> dict:
    """画像をユーザーデータへコピーし、保存用レコードを返す。"""
    source_path = Path(source)
    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(tr_ui("対応していない画像形式です"))
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    image_id = uuid.uuid4().hex
    filename = f"{image_id}{suffix}"
    destination = cheat_sheet_directory() / filename
    shutil.copy2(source_path, destination)
    return {
        "id": image_id,
        "name": source_path.stem,
        "filename": filename,
    }


def registered_image_path(record: dict) -> Path:
    """設定値から登録画像の安全な絶対パスを返す。"""
    filename = Path(str(record.get("filename", ""))).name
    return cheat_sheet_directory() / filename


def remove_registered_image(record: dict) -> None:
    path = registered_image_path(record)
    if path.is_file():
        path.unlink()


def normalized_cheat_sheet_config(config: dict | None) -> dict:
    merged = {
        **DEFAULT_CHEAT_SHEET_CONFIG,
        **(config if isinstance(config, dict) else {}),
    }
    merged["images"] = [
        dict(item)
        for item in merged.get("images", [])
        if isinstance(item, dict) and item.get("id") and item.get("filename")
    ]
    if not any(item["id"] == merged.get("selected_id") for item in merged["images"]):
        merged["selected_id"] = merged["images"][0]["id"] if merged["images"] else ""
    return merged


class CheatSheetManagerDialog(QDialog):
    """画像の登録・名称変更・順序変更を行う管理画面。"""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("Cheat sheet画像の管理"))
        self.resize(620, 430)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.value = normalized_cheat_sheet_config(config)
        self._original_records = {
            item["id"]: dict(item) for item in self.value["images"]
        }
        self._new_records: list[dict] = []
        self._pending_deletions: list[dict] = []

        layout = QVBoxLayout(self)
        hint = QLabel(tr_ui(
            "画像はPoENaviのユーザーデータへコピーされます。"
            " Shift+Spaceは登録ではなく表示／非表示に使います。"
        ))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        body = QHBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._load_current)
        body.addWidget(self.list_widget, 2)

        editor = QVBoxLayout()
        editor.addWidget(QLabel(tr_ui("表示名")))
        self.name_edit = QLineEdit()
        self.name_edit.textEdited.connect(self._rename_current)
        editor.addWidget(self.name_edit)

        self.add_button = QPushButton(tr_ui("画像を追加"))
        self.add_button.clicked.connect(self._add_image)
        editor.addWidget(self.add_button)
        self.remove_button = QPushButton(tr_ui("削除"))
        self.remove_button.clicked.connect(self._remove_image)
        editor.addWidget(self.remove_button)

        order = QHBoxLayout()
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        self.up_button.clicked.connect(lambda: self._move_current(-1))
        self.down_button.clicked.connect(lambda: self._move_current(1))
        order.addWidget(self.up_button)
        order.addWidget(self.down_button)
        editor.addLayout(order)

        editor.addWidget(QLabel(tr_ui("表示の不透明度")))
        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.value.get("opacity", 100)))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_label.setText(f"{value}%")
        )
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        editor.addLayout(opacity_row)
        editor.addStretch()
        body.addLayout(editor, 1)
        layout.addLayout(body)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr_ui("キャンセル"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr_ui("保存"))
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self._refresh_list()

    def _refresh_list(self, row: int | None = None):
        current = self.list_widget.currentRow() if row is None else row
        self.list_widget.clear()
        for image in self.value["images"]:
            name = image.get("name")
            self.list_widget.addItem(
                tr_ui("名称未設定") if not name or name == "名称未設定" else name
            )
        if self.value["images"]:
            self.list_widget.setCurrentRow(max(0, min(current, len(self.value["images"]) - 1)))
        else:
            self._load_current(-1)

    def _load_current(self, row: int):
        valid = 0 <= row < len(self.value["images"])
        self.name_edit.setEnabled(valid)
        self.remove_button.setEnabled(valid)
        self.up_button.setEnabled(valid and row > 0)
        self.down_button.setEnabled(valid and row < len(self.value["images"]) - 1)
        self.name_edit.setText(self.value["images"][row].get("name", "") if valid else "")

    def _rename_current(self, text: str):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.value["images"]):
            self.value["images"][row]["name"] = text.strip()
            self.list_widget.item(row).setText(
                self.value["images"][row]["name"] or tr_ui("名称未設定")
            )

    def _add_image(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr_ui("Cheat sheet画像を選択"),
            "",
            tr_ui("画像 (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"),
        )
        for path in paths:
            try:
                record = import_cheat_sheet_image(path)
                self.value["images"].append(record)
                self._new_records.append(record)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    tr_ui("画像を追加できません"),
                    str(exc),
                )
        if paths:
            self._refresh_list(len(self.value["images"]) - 1)

    def _remove_image(self):
        row = self.list_widget.currentRow()
        if not 0 <= row < len(self.value["images"]):
            return
        record = self.value["images"].pop(row)
        if record["id"] in self._original_records:
            self._pending_deletions.append(record)
        else:
            remove_registered_image(record)
            self._new_records = [
                item for item in self._new_records if item["id"] != record["id"]
            ]
        self._refresh_list(min(row, len(self.value["images"]) - 1))

    def _move_current(self, delta: int):
        row = self.list_widget.currentRow()
        target = row + delta
        if not (0 <= row < len(self.value["images"]) and 0 <= target < len(self.value["images"])):
            return
        self.value["images"].insert(target, self.value["images"].pop(row))
        self._refresh_list(target)

    def result_config(self) -> dict:
        self.value["opacity"] = self.opacity_slider.value()
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.value["images"]):
            self.value["selected_id"] = self.value["images"][row]["id"]
        return normalized_cheat_sheet_config(self.value)

    def accept(self):
        for record in self._pending_deletions:
            remove_registered_image(record)
        super().accept()

    def reject(self):
        for record in self._new_records:
            remove_registered_image(record)
        super().reject()


class CheatSheetOverlay(QWidget):
    """PoEのフォーカスを奪わずに登録画像を表示するオーバーレイ。"""

    config_changed = Signal(dict)
    manage_requested = Signal()

    def __init__(self, config: dict, parent=None):
        super().__init__(None)
        self.owner = parent
        self.config = normalized_cheat_sheet_config(config)
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "WindowDoesNotAcceptFocus"):
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(320, 220)
        self._drag_offset: QPoint | None = None
        self._pixmap = QPixmap()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        self.setStyleSheet(
            "QWidget { background: rgba(12, 12, 12, 235); color: white; "
            "border: 1px solid rgba(176,255,123,150); border-radius: 6px; }"
            "QLabel { border: none; background: transparent; }"
            "QPushButton { background:#292929; color:white; border:1px solid #666; "
            "border-radius:4px; padding:4px 8px; }"
            "QPushButton:hover { border-color:#b0ff7b; }"
        )

        title_row = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("font-weight:bold; font-size:14px;")
        self.title_label.setCursor(QCursor(Qt.SizeAllCursor))
        self.title_label.installEventFilter(self)
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        manage = QPushButton(tr_ui("管理"))
        manage.clicked.connect(self.manage_requested.emit)
        title_row.addWidget(manage)
        close = QPushButton("×")
        close.setFixedWidth(34)
        close.clicked.connect(self.hide_and_save)
        title_row.addWidget(close)
        layout.addLayout(title_row)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(200, 120)
        self.image_label.setWordWrap(True)
        layout.addWidget(self.image_label, 1)

        nav = QHBoxLayout()
        previous = QPushButton(tr_ui("◀ 前"))
        previous.clicked.connect(lambda: self.step_image(-1))
        next_button = QPushButton(tr_ui("次 ▶"))
        next_button.clicked.connect(lambda: self.step_image(1))
        nav.addWidget(previous)
        nav.addStretch()
        self.counter_label = QLabel("")
        nav.addWidget(self.counter_label)
        nav.addStretch()
        nav.addWidget(next_button)
        nav.addWidget(QSizeGrip(self))
        layout.addLayout(nav)
        self._apply_saved_geometry()
        self.reload(self.config)

    def _apply_saved_geometry(self):
        position = self.config.get("position", {})
        width = max(320, int(self.config.get("width", 900)))
        height = max(220, int(self.config.get("height", 650)))
        geometry = QRect(int(position.get("x", 120)), int(position.get("y", 120)), width, height)
        screens = QApplication.screens()
        if screens and not self.config.get("position_initialized", False):
            poe_rect = path_of_exile_client_rect()
            target_point = poe_rect.center() if poe_rect is not None else QCursor.pos()
            screen = QApplication.screenAt(target_point) or QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                geometry.moveLeft(available.center().x() - (width - 1) // 2)
                geometry.moveTop(available.top() + round(available.height() * 0.10))
        if screens and not any(screen.availableGeometry().intersects(geometry) for screen in screens):
            available = screens[0].availableGeometry()
            geometry.moveCenter(available.center())
        self.setGeometry(geometry)

    def reload(self, config: dict):
        self.config = normalized_cheat_sheet_config(config)
        self.setWindowOpacity(max(0.2, min(1.0, int(self.config["opacity"]) / 100)))
        self._show_selected_image()

    def _selected_index(self) -> int:
        images = self.config["images"]
        for index, image in enumerate(images):
            if image["id"] == self.config.get("selected_id"):
                return index
        return 0

    def _show_selected_image(self):
        images = self.config["images"]
        if not images:
            self.title_label.setText(
                tr_ui("Cheat sheets（画像タイトルをドラッグで移動）")
            )
            self.image_label.setStyleSheet(
                "QLabel {"
                " background: rgba(0, 0, 0, 205);"
                " color: white;"
                " border: 1px solid rgba(255, 255, 255, 110);"
                " border-radius: 10px;"
                " padding: 28px;"
                " font-size: 20px;"
                " font-weight: bold;"
                "}"
            )
            self.image_label.setText(tr_ui(
                "画像が登録されていません\n\n"
                "ぽえなび本体の「🖼」ボタンから画像を登録してください"
            ))
            self.counter_label.clear()
            self._pixmap = QPixmap()
            return
        index = self._selected_index()
        record = images[index]
        self.config["selected_id"] = record["id"]
        title = record.get("name")
        if not title or title == "名称未設定":
            title = tr_ui("名称未設定")
        self.title_label.setText(
            tr_ui(f"{title}（画像タイトルをドラッグで移動）")
        )
        self.counter_label.setText(f"{index + 1} / {len(images)}")
        self._pixmap = QPixmap(str(registered_image_path(record)))
        if self._pixmap.isNull():
            self.image_label.setStyleSheet(
                "QLabel {"
                " background: rgba(0, 0, 0, 205);"
                " color: white;"
                " border: 1px solid rgba(255, 255, 255, 110);"
                " border-radius: 10px;"
                " padding: 28px;"
                " font-size: 20px;"
                " font-weight: bold;"
                "}"
            )
            self.image_label.setText(tr_ui("画像ファイルが見つかりません"))
        else:
            self.image_label.setStyleSheet(
                "QLabel { background: transparent; border: none; padding: 0; }"
            )
            self.image_label.clear()
            self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if not self._pixmap.isNull():
            self.image_label.setPixmap(
                self._pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def step_image(self, delta: int):
        images = self.config["images"]
        if not images:
            return
        index = (self._selected_index() + delta) % len(images)
        self.config["selected_id"] = images[index]["id"]
        self._show_selected_image()
        self.config_changed.emit(dict(self.config))

    def toggle(self):
        if self.isVisible():
            self.hide_and_save()
        else:
            self.reload(self.config)
            self.show()
            self.raise_()

    def hide_and_save(self):
        geometry = self.geometry()
        self.config["position"] = {"x": geometry.x(), "y": geometry.y()}
        self.config["position_initialized"] = True
        self.config["width"] = geometry.width()
        self.config["height"] = geometry.height()
        self.config_changed.emit(dict(self.config))
        self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 50:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.title_label:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if (
                event.type() == QEvent.MouseMove
                and self._drag_offset is not None
                and event.buttons() & Qt.LeftButton
            ):
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide_and_save()
            event.accept()
            return
        super().keyPressEvent(event)
