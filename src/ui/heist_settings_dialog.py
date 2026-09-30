"""PoE1 Grand Heist reward OCR settings dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.dialog_theme import POETORE_DIALOG_THEME, apply_dialog_theme
from src.ui.expedition_settings_dialog import ClickableImageLabel
from src.ui.high_accuracy_ocr_pack_group import HighAccuracyOcrPackGroup
from src.ui.settings_dialog import AutoHideHotkeyWidget

DEFAULT_EXAMPLE_IMAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "images"
    / "heist_curio_manual_selection_example.png"
)


class HeistSettingsDialog(QDialog):
    """Configure the opt-in manual-selection Heist reward reader."""

    def __init__(
        self,
        parent=None,
        *,
        enabled: bool = False,
        hotkey: str = "alt+e",
        example_image_path=None,
        ocr_pack_controller=None,
    ):
        super().__init__(parent)
        self._example_image_path = Path(
            example_image_path or DEFAULT_EXAMPLE_IMAGE_PATH
        )
        self._ocr_pack_controller = ocr_pack_controller
        self.theme = POETORE_DIALOG_THEME
        self.setWindowTitle("ハイスト報酬OCR設定")
        self.setMinimumSize(620, 700)
        apply_dialog_theme(self, self.theme)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)
        self.title_label = QLabel("ハイスト報酬OCR設定")
        self.title_label.setProperty("uiRole", "title")
        root.addWidget(self.title_label)

        scroll = QScrollArea()
        scroll.setObjectName("heistSettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content_widget = QWidget()
        content = QVBoxLayout(content_widget)
        content.setContentsMargins(4, 4, 4, 4)
        content.setSpacing(10)
        scroll.setWidget(content_widget)
        root.addWidget(scroll, 1)

        basic_group, basic = self._section_group("1. 基本設定", "basicSettingsGroup")
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)
        self.enabled_checkbox = QCheckBox("ハイスト報酬OCRを有効化")
        self.enabled_checkbox.setChecked(bool(enabled))
        toggle_row.addWidget(self.enabled_checkbox)
        self.enable_required_hint = QLabel("※有効時だけOCRとホットキーを起動します")
        self.enable_required_hint.setObjectName("heistEnableRequiredHint")
        self.enable_required_hint.setProperty("uiRole", "muted")
        toggle_row.addWidget(self.enable_required_hint)
        toggle_row.addStretch()
        basic.addLayout(toggle_row)

        form = QFormLayout()
        form.setContentsMargins(0, 2, 0, 0)
        self.hotkey_widget = AutoHideHotkeyWidget(
            hotkey,
            theme=self.theme,
            allow_no_modifier=True,
            allow_multiple_modifiers=True,
            allow_shift=True,
        )
        self.hotkey_widget.key_button.setStyleSheet("")
        form.addRow("読取ショートカット:", self.hotkey_widget)
        basic.addLayout(form)
        content.addWidget(basic_group)

        pack_group = HighAccuracyOcrPackGroup(self._ocr_pack_controller, self)
        self.ocr_pack_status = pack_group.status_label
        self.ocr_pack_progress = pack_group.progress_bar
        self.ocr_pack_retry = pack_group.retry_button
        content.addWidget(pack_group)

        usage_group, usage = self._section_group("3. 読み取り方法", "readMethodGroup")
        instruction = QLabel(
            "ショートカットを押したら、展示パネルの報酬名とベースタイプが見える部分を"
            "左上から右下へドラッグしてください。\n"
            "ドラッグを終えると自動で確定します。Escでキャンセルできます。"
        )
        instruction.setObjectName("heistSelectionInstruction")
        instruction.setProperty("uiRole", "muted")
        instruction.setWordWrap(True)
        usage.addWidget(instruction)

        warning = QLabel(
            "アイテムの説明文や背景を広く含めず、下の例のように名前部分だけを囲むと"
            "安定して読み取れます。"
        )
        warning.setObjectName("heistSelectionWarning")
        warning.setProperty("state", "warning")
        warning.setWordWrap(True)
        usage.addWidget(warning)

        example_heading = QHBoxLayout()
        example_title = QLabel("範囲指定例")
        example_title.setObjectName("heistExampleHeading")
        example_title.setProperty("uiRole", "section")
        example_heading.addWidget(example_title)
        hint = QLabel("※画像をクリックすると拡大表示します")
        hint.setObjectName("heistExampleHint")
        hint.setProperty("uiRole", "muted")
        example_heading.addWidget(hint)
        example_heading.addStretch()
        usage.addLayout(example_heading)

        self.example_thumbnail = ClickableImageLabel()
        self.example_thumbnail.setObjectName("heistExampleThumbnail")
        self.example_thumbnail.setProperty("uiRole", "surface")
        self.example_thumbnail.setAlignment(Qt.AlignCenter)
        self.example_thumbnail.setFixedHeight(150)
        self.example_thumbnail.setCursor(Qt.PointingHandCursor)
        self.example_thumbnail.clicked.connect(self._show_example_popup)
        usage.addWidget(self.example_thumbnail)
        self._load_example_thumbnail()
        content.addWidget(usage_group)
        content.addStretch()

        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setProperty("buttonRole", "secondary")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("保存")
        self.save_button.setProperty("buttonRole", "primary")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        root.addLayout(footer)

        for widget_type in (QCheckBox, QGroupBox, QPushButton, QScrollArea):
            for widget in self.findChildren(widget_type):
                widget.setStyleSheet("")

    @staticmethod
    def _section_group(title: str, object_name: str):
        group = QGroupBox(title)
        group.setObjectName(object_name)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)
        return group, layout

    def settings(self) -> tuple[str, bool]:
        return self.hotkey_widget.key_text, self.enabled_checkbox.isChecked()

    def _load_example_thumbnail(self) -> None:
        pixmap = QPixmap(str(self._example_image_path))
        if pixmap.isNull():
            self.example_thumbnail.setText("範囲指定例画像を読み込めませんでした。")
            return
        self.example_thumbnail.setPixmap(
            pixmap.scaled(QSize(550, 138), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.example_thumbnail.setToolTip("クリックして拡大")

    def _show_example_popup(self) -> None:
        popup = QDialog(self)
        popup.setWindowTitle("ハイスト報酬の範囲指定例")
        popup.resize(1100, 360)
        apply_dialog_theme(popup, self.theme)
        layout = QVBoxLayout(popup)
        guide = QLabel("このように、報酬名とベースタイプが表示された横長部分を囲みます。")
        guide.setProperty("uiRole", "muted")
        guide.setWordWrap(True)
        layout.addWidget(guide)
        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(self._example_image_path))
        if pixmap.isNull():
            image.setText("範囲指定例画像を読み込めませんでした。")
        else:
            image.setPixmap(
                pixmap.scaled(
                    QSize(1060, 240), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        layout.addWidget(image)
        close = QPushButton("閉じる")
        close.setProperty("buttonRole", "secondary")
        close.clicked.connect(popup.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        popup.exec()
