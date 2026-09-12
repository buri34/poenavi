"""エクスペディション報酬チェック専用設定画面。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.poetore.window_position import path_of_exile_client_rect
from src.ui.app_theme import SETTINGS_THEME
from src.ui.settings_dialog import AutoHideHotkeyWidget
from src.ui.styles import Styles

MIN_SELECTION_WIDTH_RATIO = 0.05
MIN_SELECTION_HEIGHT_RATIO = 0.05
DEFAULT_EXAMPLE_IMAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "images"
    / "expedition_region_example.png"
)


def normalized_region(selection: QRect, client_rect: QRect) -> dict[str, float] | None:
    """Return a validated selection as client-relative coordinates."""
    if (
        client_rect.width() <= 0
        or client_rect.height() <= 0
        or selection.width() <= 0
        or selection.height() <= 0
        or not client_rect.contains(selection)
    ):
        return None
    if (
        selection.width() / client_rect.width() < MIN_SELECTION_WIDTH_RATIO
        or selection.height() / client_rect.height() < MIN_SELECTION_HEIGHT_RATIO
    ):
        return None
    return {
        "left": (selection.left() - client_rect.left()) / client_rect.width(),
        "top": (selection.top() - client_rect.top()) / client_rect.height(),
        "right": (selection.left() + selection.width() - client_rect.left())
        / client_rect.width(),
        "bottom": (selection.top() + selection.height() - client_rect.top())
        / client_rect.height(),
    }


def valid_normalized_region(value) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        region = {
            key: float(value[key])
            for key in ("left", "top", "right", "bottom")
        }
    except (KeyError, TypeError, ValueError):
        return None
    if not (
        0.0 <= region["left"] < region["right"] <= 1.0
        and 0.0 <= region["top"] < region["bottom"] <= 1.0
        and region["right"] - region["left"] >= MIN_SELECTION_WIDTH_RATIO
        and region["bottom"] - region["top"] >= MIN_SELECTION_HEIGHT_RATIO
    ):
        return None
    return region


class ExpeditionRegionSelector(QDialog):
    """Transparent drag selector constrained to the PoE client rectangle."""

    def __init__(self, client_rect: QRect, parent=None):
        super().__init__(parent)
        self.client_rect = QRect(client_rect)
        self._origin: QPoint | None = None
        self._selection = QRect()
        guide_font = self.font()
        guide_font.setPixelSize(36)
        guide_font.setBold(True)
        self.setFont(guide_font)
        self.setStyleSheet("font-size: 36px; font-weight: bold;")
        self.setWindowTitle("エクスペ報酬の読取範囲を指定")
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setGeometry(client_rect)
        self.setFocusPolicy(Qt.StrongFocus)

    @property
    def selected_region(self) -> dict[str, float] | None:
        global_selection = QRect(self._selection)
        global_selection.translate(self.client_rect.topLeft())
        return normalized_region(global_selection, self.client_rect)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        self._origin = event.position().toPoint()
        self._selection = QRect(self._origin, QSize())
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._origin is None:
            return
        point = event.position().toPoint()
        point.setX(max(0, min(self.width() - 1, point.x())))
        point.setY(max(0, min(self.height() - 1, point.y())))
        self._selection = QRect(self._origin, point).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.mouseMoveEvent(event)
            self._origin = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.selected_region is None:
                QMessageBox.warning(
                    self,
                    "範囲を確認してください",
                    "範囲が小さすぎるか、ゲーム画面の外を含んでいます。",
                )
                return
            self.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.fillRect(self.rect(), QColor(0, 0, 0, 92))
        if not self._selection.isNull():
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self._selection, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#B0FF7B"), 3))
            painter.drawRect(self._selection)
        painter.setPen(QColor("white"))
        painter.drawText(
            self.rect().adjusted(20, 20, -20, -20),
            Qt.AlignTop | Qt.AlignHCenter,
            "左上から右下へドラッグ\n"
            "Enter: 確定\n"
            "Esc: キャンセル",
        )


class RegionPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._region = None
        self.setObjectName("expeditionRegionPreview")
        self.setMinimumHeight(120)

    def set_region(self, region):
        self._region = valid_normalized_region(region)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        panel = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(panel, QColor("#151A15"))
        painter.setPen(QPen(QColor("#596359"), 1))
        painter.drawRect(panel)
        if self._region is None:
            painter.setPen(QColor(SETTINGS_THEME.muted_text))
            painter.drawText(panel, Qt.AlignCenter, "読取範囲は未設定です")
            return
        left = panel.left() + round(panel.width() * self._region["left"])
        top = panel.top() + round(panel.height() * self._region["top"])
        right = panel.left() + round(panel.width() * self._region["right"])
        bottom = panel.top() + round(panel.height() * self._region["bottom"])
        painter.setPen(QPen(QColor("#B0FF7B"), 3))
        painter.drawRect(QRect(QPoint(left, top), QPoint(right, bottom)))


class ClickableImageLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ExpeditionSettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        expedition_config=None,
        screen_reading_enabled=False,
        hotkey="alt+e",
        example_image_path=None,
        client_rect_getter=path_of_exile_client_rect,
        selector_class=ExpeditionRegionSelector,
    ):
        super().__init__(parent)
        self._config = dict(expedition_config or {})
        self._region = valid_normalized_region(self._config.get("region"))
        self._client_rect_getter = client_rect_getter
        self._selector_class = selector_class
        self._example_image_path = Path(
            example_image_path or DEFAULT_EXAMPLE_IMAGE_PATH
        )
        self.setWindowTitle("エクスペ報酬チェック設定")
        self.setMinimumSize(560, 650)
        self.setStyleSheet(self._style_sheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        reading_toggle_row = QHBoxLayout()
        reading_toggle_row.setSpacing(8)
        self.enabled_checkbox = QCheckBox("ゲーム画面の読み取り機能を有効にする")
        self.enabled_checkbox.setChecked(bool(screen_reading_enabled))
        Styles.apply_checkbox_style(self.enabled_checkbox)
        reading_toggle_row.addWidget(self.enabled_checkbox)
        self.enable_required_hint = QLabel(
            "※使用するにはチェックをONにしてください"
        )
        self.enable_required_hint.setObjectName("screenReadingEnableRequiredHint")
        reading_toggle_row.addWidget(self.enable_required_hint)
        reading_toggle_row.addStretch()
        root.addLayout(reading_toggle_row)
        shared_hint = QLabel(
            "エクスペ報酬価格チェックとアビス冒涜Modティアチェックで共通の設定です。"
        )
        shared_hint.setWordWrap(True)
        shared_hint.setStyleSheet(f"color: {SETTINGS_THEME.muted_text};")
        root.addWidget(shared_hint)

        hotkey_form = QFormLayout()
        self.hotkey_widget = AutoHideHotkeyWidget(
            hotkey, theme=SETTINGS_THEME, allow_no_modifier=True
        )
        self.hotkey_widget.key_button.setStyleSheet("")
        hotkey_form.addRow("読取ショートカット:", self.hotkey_widget)
        root.addLayout(hotkey_form)

        root.addWidget(QLabel("現在の読取範囲"))
        self.status_label = QLabel()
        self.status_label.setObjectName("expeditionRegionStatus")
        root.addWidget(self.status_label)
        self.preview = RegionPreview()
        self.preview.set_region(self._region)
        root.addWidget(self.preview)

        range_buttons = QHBoxLayout()
        self.set_region_button = QPushButton()
        self.set_region_button.setObjectName("setExpeditionRegionButton")
        self.set_region_button.clicked.connect(self._choose_region)
        self.reset_region_button = QPushButton("読取範囲をリセット")
        self.reset_region_button.setObjectName("resetExpeditionRegionButton")
        self.reset_region_button.clicked.connect(self._reset_region)
        range_buttons.addWidget(self.set_region_button)
        range_buttons.addWidget(self.reset_region_button)
        root.addLayout(range_buttons)

        instruction = QLabel(
            "報酬カードの左端・右端、先頭カードの上端、報酬パネル内側の最下部を囲んでください。\n"
            "タイトルや外枠は含めず、報酬が少ない時の空白部分は含めます。"
        )
        instruction.setWordWrap(True)
        instruction.setObjectName("expeditionRegionInstruction")
        root.addWidget(instruction)
        size_warning = QLabel(
            "PoE2のウィンドウサイズを変更した場合、位置が変わるため再設定が必要です。"
        )
        size_warning.setWordWrap(True)
        size_warning.setObjectName("screenSizeRegionWarning")
        root.addWidget(size_warning)

        example_heading = QHBoxLayout()
        example_heading.addWidget(QLabel("指定例"))
        self.example_hint_label = QLabel(
            "※以下の画像をクリックするとポップアップで拡大表示します"
        )
        self.example_hint_label.setObjectName("expeditionExampleHint")
        example_heading.addWidget(self.example_hint_label)
        example_heading.addStretch()
        root.addLayout(example_heading)
        self.example_thumbnail = ClickableImageLabel()
        self.example_thumbnail.setObjectName("expeditionExampleThumbnail")
        self.example_thumbnail.setAlignment(Qt.AlignCenter)
        self.example_thumbnail.setFixedHeight(150)
        self.example_thumbnail.setCursor(Qt.PointingHandCursor)
        self.example_thumbnail.clicked.connect(self._show_example_popup)
        root.addWidget(self.example_thumbnail)
        self._load_example_thumbnail()

        root.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("キャンセル")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)
        self._refresh_region_state()

    def settings(self) -> tuple[dict, str, bool]:
        config = dict(self._config)
        config.pop("enabled", None)
        if self._region is None:
            config.pop("region", None)
        else:
            config["region"] = dict(self._region)
        return config, self.hotkey_widget.key_text, self.enabled_checkbox.isChecked()

    def _choose_region(self):
        client_rect = self._client_rect_getter()
        if client_rect is None:
            QMessageBox.warning(
                self,
                "PoE2が見つかりません",
                "PoE2を起動して報酬画面を表示してから、もう一度お試しください。",
            )
            return
        windows = [self]
        owner = self.parentWidget()
        if owner is not None and owner.isWindow():
            windows.append(owner)
        previous_opacities = [window.windowOpacity() for window in windows]
        for window in windows:
            window.setWindowOpacity(0.0)
        QApplication.processEvents()
        try:
            selector = self._selector_class(QRect(client_rect), self)
            result = selector.exec()
        finally:
            for window, opacity in reversed(
                list(zip(windows, previous_opacities))
            ):
                window.setWindowOpacity(opacity)
            self.raise_()
            self.activateWindow()
        if result != QDialog.Accepted:
            return
        region = valid_normalized_region(selector.selected_region)
        if region is None:
            QMessageBox.warning(
                self,
                "範囲を確認してください",
                "選択した範囲を保存できませんでした。",
            )
            return
        self._region = region
        self.preview.set_region(region)
        self._refresh_region_state()

    def _reset_region(self):
        self._region = None
        self.preview.set_region(None)
        self._refresh_region_state()

    def _refresh_region_state(self):
        configured = self._region is not None
        self.status_label.setText("設定済み" if configured else "未設定")
        self.status_label.setStyleSheet(
            "color: #B0FF7B; font-weight: bold;"
            if configured
            else "color: #FFCC80; font-weight: bold;"
        )
        self.set_region_button.setText(
            "読取範囲を再設定" if configured else "読取範囲を設定"
        )
        self.reset_region_button.setEnabled(configured)

    def _load_example_thumbnail(self):
        pixmap = QPixmap(str(self._example_image_path))
        if pixmap.isNull():
            self.example_thumbnail.setText(
                "指定例画像は準備中です\n（画像追加後、ここをクリックすると拡大表示します）"
            )
            return
        self.example_thumbnail.setPixmap(
            pixmap.scaled(
                QSize(500, 140), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        self.example_thumbnail.setToolTip("クリックして拡大")

    def _show_example_popup(self):
        popup = QDialog(self)
        popup.setWindowTitle("読取範囲の指定例")
        popup.resize(900, 700)
        layout = QVBoxLayout(popup)
        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(self._example_image_path))
        if pixmap.isNull():
            image.setText("指定例画像は準備中です。")
        else:
            image.setPixmap(
                pixmap.scaled(
                    QSize(860, 630), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        layout.addWidget(image)
        close = QPushButton("閉じる")
        close.clicked.connect(popup.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        popup.exec()

    @staticmethod
    def _style_sheet():
        theme = SETTINGS_THEME
        return f"""
            QDialog {{ background: {theme.background}; color: {theme.text}; font-size: 13px; }}
            QLabel, QCheckBox {{ color: {theme.text}; }}
            QPushButton {{
                background: {theme.panel}; color: {theme.text};
                border: 1px solid #596359; border-radius: 5px;
                padding: 7px 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #293229; border-color: {theme.accent}; }}
            QPushButton:focus {{ border-color: {theme.accent}; }}
            QLabel#expeditionRegionInstruction {{ color: {theme.muted_text}; }}
            QLabel#screenSizeRegionWarning, QLabel#screenReadingEnableRequiredHint {{
                color: #FFD54F; font-weight: bold;
            }}
            QLabel#screenReadingEnableRequiredHint {{ font-size: 12px; }}
            QLabel#expeditionExampleThumbnail {{
                background: #151A15; color: {theme.muted_text};
                border: 1px solid #596359; border-radius: 6px;
            }}
            QCheckBox::indicator:checked {{ background: {theme.accent}; }}
        """
