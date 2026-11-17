"""Shared, restart-only appearance editor for both application modes."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFontComboBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from src.ui.appearance import (
    MAX_FONT_SIZE, MIN_FONT_SIZE, PRESETS, normalize_appearance, resolve_tokens,
)


class AppearanceSettingsWidget(QScrollArea):
    COLOR_FIELDS = (
        ("accent", "アクセント"), ("text", "文字"),
        ("muted_text", "補助文字"), ("background", "背景"),
        ("surface", "パネル・入力欄"), ("border", "枠線"),
        ("overlay_bg", "オーバーレイの背景"),
        ("overlay_text", "オーバーレイの文字"),
    )

    def __init__(self, appearance=None, parent=None, *, mode="poenavi"):
        super().__init__(parent)
        self.setObjectName("appearanceSettings")
        self.setWidgetResizable(True)
        self._draft = normalize_appearance(appearance)
        self._mode = mode
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        note = QLabel(
            "両モードで共通の外観です。保存後、再起動すると反映されます。\n"
            "ゲーム内容を表す色は変更しません。透過率は各画面の既存設定を使います。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(8)
        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("appearancePreset")
        for value, label in PRESETS.items():
            self.preset_combo.addItem(label, value)
        form.addRow("プリセット", self.preset_combo)
        self.font_combo = QFontComboBox()
        self.font_combo.setObjectName("appearanceFontFamily")
        form.addRow("フォント", self.font_combo)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setObjectName("appearanceFontSize")
        self.font_size_spin.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setToolTip("既存の文字サイズの比率を保ちながら、全体を拡大・縮小します。")
        form.addRow("基準文字サイズ", self.font_size_spin)
        self.color_buttons = {}
        for role, label in self.COLOR_FIELDS:
            button = QPushButton()
            button.setObjectName(f"appearanceColor_{role}")
            button.setAccessibleName(f"{label}の色を選択")
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda checked=False, key=role: self._choose_color(key))
            form.addRow(label, button)
            self.color_buttons[role] = button
        layout.addLayout(form)
        hint = QLabel("色ボタンで自由に選択できます。＊はプリセットからの上書きです。")
        hint.setWordWrap(True)
        hint.setProperty("uiRole", "muted")
        layout.addWidget(hint)

        self.preview = QFrame()
        self.preview.setObjectName("appearancePreview")
        preview_layout = QVBoxLayout(self.preview)
        self.preview_title = QLabel("外観プレビュー")
        self.preview_title.setObjectName("appearancePreviewTitle")
        self.preview_text = QLabel("文字とパネルの見本  Aa 123\n保存した外観は次回起動時に反映されます。")
        self.preview_text.setWordWrap(True)
        self.preview_caption = QLabel("補助文字と枠線")
        self.preview_caption.setObjectName("appearancePreviewCaption")
        self.preview_overlay = QLabel("オーバーレイの見本")
        self.preview_overlay.setObjectName("appearancePreviewOverlay")
        self.preview_overlay.setWordWrap(True)
        for widget in (self.preview_title, self.preview_text, self.preview_caption, self.preview_overlay):
            preview_layout.addWidget(widget)
        layout.addWidget(self.preview)
        actions = QHBoxLayout()
        self.reset_button = QPushButton("外観を既定に戻す")
        self.reset_button.setObjectName("appearanceReset")
        self.reset_button.clicked.connect(self._reset)
        actions.addWidget(self.reset_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        self.setWidget(content)
        self._load_controls()
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        self.font_combo.currentFontChanged.connect(self._font_changed)
        self.font_size_spin.valueChanged.connect(self._size_changed)

    def settings(self):
        return normalize_appearance(self._draft)

    def _load_controls(self):
        tokens = resolve_tokens(self._draft, self._mode)
        for control in (self.preset_combo, self.font_combo, self.font_size_spin):
            control.blockSignals(True)
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(self._draft["preset"]))
        self.font_combo.setCurrentFont(QFont(tokens.font_family))
        self.font_size_spin.setValue(tokens.base_font_size)
        for control in (self.preset_combo, self.font_combo, self.font_size_spin):
            control.blockSignals(False)
        self._update_preview()

    def _preset_changed(self):
        self._draft["preset"] = self.preset_combo.currentData()
        self._update_preview()

    def _font_changed(self, font):
        self._draft["overrides"]["font_family"] = font.family()
        self._update_preview()

    def _size_changed(self, size):
        self._draft["overrides"]["base_font_size"] = size
        self._update_preview()

    def _choose_color(self, role):
        tokens = resolve_tokens(self._draft, self._mode)
        color = QColorDialog.getColor(QColor(getattr(tokens, role)), self, "色を選択")
        if color.isValid():
            self._draft["overrides"][role] = color.name().upper()
            self._update_preview()

    def _reset(self):
        self._draft = normalize_appearance(None)
        self._load_controls()

    def _update_preview(self):
        tokens = resolve_tokens(self._draft, self._mode)
        for role, _label in self.COLOR_FIELDS:
            color = getattr(tokens, role)
            swatch = QPixmap(20, 20)
            swatch.fill(QColor(color))
            button = self.color_buttons[role]
            button.setIcon(QIcon(swatch))
            marker = " ＊" if role in self._draft["overrides"] else ""
            button.setText(f"{color}{marker}")
        self.preview.setStyleSheet(f"""
            QFrame#appearancePreview {{ background: {tokens.surface}; border: 1px solid {tokens.border}; border-radius: 6px; }}
            QFrame#appearancePreview QLabel {{ color: {tokens.text}; background: transparent;
                border: none; font-family: '{tokens.font_family}'; font-size: {tokens.base_font_size}px; }}
            QFrame#appearancePreview QLabel#appearancePreviewTitle {{ color: {tokens.accent}; font-weight: bold; }}
            QFrame#appearancePreview QLabel#appearancePreviewCaption {{ color: {tokens.muted_text}; }}
            QFrame#appearancePreview QLabel#appearancePreviewOverlay {{ color: {tokens.overlay_text}; background: {tokens.overlay_bg};
                border: 1px solid {tokens.overlay_border}; padding: 6px; }}
        """)
