"""Settings UI for the PoE2 Abyss Desecration tier overlay."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.poetore.window_position import path_of_exile_client_rect
from src.ui.app_theme import SETTINGS_THEME
from src.ui.expedition_settings_dialog import (
    ClickableImageLabel,
    ExpeditionRegionSelector,
    RegionPreview,
    valid_normalized_region,
)
from src.ui.settings_dialog import AutoHideHotkeyWidget
from src.ui.styles import Styles

DEFAULT_EXAMPLE_IMAGE_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "images"
    / "desecration_region_example.png"
)
EXAMPLE_POPUP_SIZE = QSize(1350, 700)
EXAMPLE_POPUP_IMAGE_SIZE = QSize(1290, 945)


class DesecrationRegionSelector(ExpeditionRegionSelector):
    def __init__(self, client_rect, parent=None):
        super().__init__(client_rect, parent)
        self.setWindowTitle("アビス冒涜Modの読取範囲を指定")


class DesecrationSettingsDialog(QDialog):
    def __init__(
        self, parent=None, desecration_config=None, hotkey="alt+r",
        screen_reading_enabled=False, example_image_path=None,
        client_rect_getter=path_of_exile_client_rect,
        selector_class=DesecrationRegionSelector,
    ):
        super().__init__(parent)
        self._config = dict(desecration_config or {})
        self._regions = {
            "inventory_open_region": valid_normalized_region(
                self._config.get("inventory_open_region")
            ),
            "inventory_closed_region": valid_normalized_region(
                self._config.get("inventory_closed_region")
            ),
        }
        self._client_rect_getter = client_rect_getter
        self._selector_class = selector_class
        self._example_image_path = Path(example_image_path or DEFAULT_EXAMPLE_IMAGE_PATH)
        self._section_widgets = {}
        self.setWindowTitle("アビス冒涜Modティアチェック設定")
        self.setMinimumSize(620, 820)
        self.setStyleSheet(self._style_sheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("desecrationSettingsScroll")
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
        basic.addLayout(reading_toggle_row)
        shared_hint = QLabel(
            "エクスペ報酬価格チェックとアビス冒涜Modティアチェックで共通の設定です。"
        )
        shared_hint.setWordWrap(True)
        shared_hint.setStyleSheet(f"color: {SETTINGS_THEME.muted_text};")
        basic.addWidget(shared_hint)

        form = QFormLayout()
        form.setContentsMargins(0, 2, 0, 0)
        self.hotkey_widget = AutoHideHotkeyWidget(
            hotkey, theme=SETTINGS_THEME, allow_no_modifier=True
        )
        self.hotkey_widget.key_button.setStyleSheet("")
        form.addRow("読取ショートカット:", self.hotkey_widget)
        basic.addLayout(form)
        content.addWidget(basic_group)

        range_group, ranges = self._section_group("2. 読取範囲", "readRegionsGroup")
        instruction = QLabel(
            "タイトル・装備画像・確認ボタンを含めず、3つのMod選択肢部分だけを囲んでください。\n"
            "読取時は「インベントリを開いた状態」を先に確認し、読取に失敗した場合は"
            "「閉じた状態」を確認します。"
        )
        instruction.setWordWrap(True)
        instruction.setObjectName("desecrationRegionInstruction")
        ranges.addWidget(instruction)
        size_warning = QLabel(
            "PoE2のウィンドウサイズを変更した場合、位置が変わるため再設定が必要です。"
        )
        size_warning.setWordWrap(True)
        size_warning.setObjectName("screenSizeRegionWarning")
        ranges.addWidget(size_warning)
        self._add_region_section(
            ranges, "inventory_open_region", "インベントリを開いた状態", required=True,
        )
        self._add_region_section(
            ranges, "inventory_closed_region", "インベントリを閉じた状態（任意）",
            note="※インベントリを閉じると位置がずれて読取に失敗するため",
        )
        heading = QHBoxLayout()
        example_heading = QLabel("指定例")
        example_heading.setObjectName("desecrationExampleHeading")
        heading.addWidget(example_heading)
        hint = QLabel("※以下の画像をクリックするとポップアップで拡大表示します")
        hint.setStyleSheet(f"color: {SETTINGS_THEME.muted_text};")
        heading.addWidget(hint)
        heading.addStretch()
        ranges.addLayout(heading)
        self.example_thumbnail = ClickableImageLabel()
        self.example_thumbnail.setObjectName("desecrationExampleThumbnail")
        self.example_thumbnail.setAlignment(Qt.AlignCenter)
        self.example_thumbnail.setFixedHeight(130)
        self.example_thumbnail.setCursor(Qt.PointingHandCursor)
        self.example_thumbnail.clicked.connect(self._show_example_popup)
        ranges.addWidget(self.example_thumbnail)
        self._load_example_thumbnail()
        content.addWidget(range_group)

        display_group, display = self._section_group(
            "3. 表示設定", "displaySettingsGroup"
        )
        self.show_ranges_checkbox = QCheckBox(
            "Tierの数値範囲を表示する（例：15–25%）"
        )
        self.show_ranges_checkbox.setChecked(
            bool(self._config.get("show_tier_ranges", True))
        )
        Styles.apply_checkbox_style(self.show_ranges_checkbox)
        display.addWidget(self.show_ranges_checkbox)
        content.addWidget(display_group)
        content.addStretch()

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
        self._refresh_all()

    @staticmethod
    def _section_group(title: str, object_name: str):
        group = QGroupBox(title)
        group.setObjectName(object_name)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)
        return group, layout

    def _add_region_section(self, root, key, title, *, required=False, note=""):
        heading = QHBoxLayout()
        heading.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName(f"{key}Title")
        heading.addWidget(title_label)
        if required:
            required_label = QLabel("（必須）")
            required_label.setObjectName("desecrationRequiredLabel")
            heading.addWidget(required_label)
        if note:
            note_label = QLabel(note)
            note_label.setObjectName("desecrationClosedRegionNote")
            heading.addWidget(note_label)
        heading.addStretch()
        root.addLayout(heading)
        status = QLabel()
        preview = RegionPreview()
        preview.setMinimumHeight(82)
        preview.set_region(self._regions[key])
        root.addWidget(status)
        root.addWidget(preview)
        row = QHBoxLayout()
        choose = QPushButton()
        choose.clicked.connect(lambda _checked=False, item=key: self._choose_region(item))
        reset = QPushButton("読取範囲をリセット")
        reset.clicked.connect(lambda _checked=False, item=key: self._reset_region(item))
        row.addWidget(choose)
        row.addWidget(reset)
        root.addLayout(row)
        self._section_widgets[key] = (status, preview, choose, reset)

    def settings(self) -> tuple[dict, str, bool]:
        config = dict(self._config)
        config["show_tier_ranges"] = self.show_ranges_checkbox.isChecked()
        for key, region in self._regions.items():
            if region is None:
                config.pop(key, None)
            else:
                config[key] = dict(region)
        return config, self.hotkey_widget.key_text, self.enabled_checkbox.isChecked()

    def _choose_region(self, key):
        client_rect = self._client_rect_getter()
        if client_rect is None:
            QMessageBox.warning(
                self, "PoE2が見つかりません",
                "PoE2を起動して冒涜Modの3択画面を表示してから、もう一度お試しください。",
            )
            return
        windows = [self]
        owner = self.parentWidget()
        if owner is not None and owner.isWindow():
            windows.append(owner)
        opacities = [window.windowOpacity() for window in windows]
        for window in windows:
            window.setWindowOpacity(0.0)
        QApplication.processEvents()
        try:
            selector = self._selector_class(QRect(client_rect), self)
            result = selector.exec()
        finally:
            for window, opacity in reversed(list(zip(windows, opacities))):
                window.setWindowOpacity(opacity)
            self.raise_()
            self.activateWindow()
        if result != QDialog.Accepted:
            return
        region = valid_normalized_region(selector.selected_region)
        if region is None:
            QMessageBox.warning(self, "範囲を確認してください", "選択した範囲を保存できませんでした。")
            return
        self._regions[key] = region
        self._refresh_all()

    def _reset_region(self, key):
        self._regions[key] = None
        self._refresh_all()

    def _refresh_all(self):
        for key, (status, preview, choose, reset) in self._section_widgets.items():
            configured = self._regions[key] is not None
            required = key == "inventory_open_region"
            if configured:
                text, color = "設定済み", "#B0FF7B"
            elif required:
                text, color = "未設定（読取ショートカットは無効）", "#FFCC80"
            else:
                text, color = "未設定", "#98A39F"
            status.setText(text)
            status.setStyleSheet(f"color: {color}; font-weight: bold;")
            preview.set_region(self._regions[key])
            choose.setText("読取範囲を再設定" if configured else "読取範囲を設定")
            reset.setEnabled(configured)

    def _load_example_thumbnail(self):
        pixmap = QPixmap(str(self._example_image_path))
        if pixmap.isNull():
            self.example_thumbnail.setText(
                "指定例画像は準備中です\n（画像追加後、ここをクリックすると拡大表示します）"
            )
            return
        self.example_thumbnail.setPixmap(pixmap.scaled(
            QSize(540, 120), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def _show_example_popup(self):
        popup = QDialog(self)
        popup.setWindowTitle("読取範囲の指定例")
        popup.resize(EXAMPLE_POPUP_SIZE)
        layout = QVBoxLayout(popup)
        image = QLabel()
        image.setObjectName("desecrationExamplePopupImage")
        image.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(self._example_image_path))
        image.setText("指定例画像は準備中です。") if pixmap.isNull() else image.setPixmap(
            pixmap.scaled(
                EXAMPLE_POPUP_IMAGE_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
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
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: {theme.background}; }}
            QLabel, QCheckBox, QGroupBox {{ color: {theme.text}; }}
            QGroupBox {{
                background: {theme.panel}; border: 1px solid #465046;
                border-radius: 7px; margin-top: 10px; padding-top: 7px;
            }}
            QGroupBox::title {{
                color: {theme.accent}; font-size: 14px; font-weight: bold;
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 10px; padding: 0 6px;
            }}
            QLabel#desecrationExampleHeading {{ font-weight: bold; }}
            QPushButton {{ background: {theme.panel}; color: {theme.text}; border: 1px solid #596359;
                border-radius: 5px; padding: 7px 12px; font-weight: bold; }}
            QPushButton:hover {{ background: #293229; border-color: {theme.accent}; }}
            QLabel#desecrationRegionInstruction {{ color: {theme.muted_text}; }}
            QLabel#desecrationRequiredLabel, QLabel#screenSizeRegionWarning,
            QLabel#screenReadingEnableRequiredHint {{
                color: #FFD54F; font-weight: bold;
            }}
            QLabel#screenReadingEnableRequiredHint {{ font-size: 12px; }}
            QLabel#desecrationClosedRegionNote {{
                color: {theme.muted_text}; font-size: 11px;
            }}
            QLabel#desecrationExampleThumbnail {{ background: #151A15; color: {theme.muted_text};
                border: 1px solid #596359; border-radius: 6px; }}
            QCheckBox::indicator:checked {{ background: {theme.accent}; }}
        """
