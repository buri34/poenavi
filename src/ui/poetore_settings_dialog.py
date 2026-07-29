"""ぽえとれモード専用の軽量設定画面。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode
from src.ui.app_theme import POETORE_THEME


class PoetoreSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.current_config = current_config or {}
        self.setWindowTitle("ぽえとれ設定")
        self.setMinimumWidth(480)
        self.setStyleSheet(self._style_sheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        startup = self.current_config.get("startup")
        startup = startup if isinstance(startup, dict) else {}
        startup_group = QGroupBox("起動モード")
        startup_layout = QVBoxLayout(startup_group)
        self.show_mode_selector_cb = QCheckBox(
            "起動時に「ぽえなび／ぽえとれ」を毎回選択する"
        )
        self.show_mode_selector_cb.setChecked(
            bool(startup.get("show_mode_selector", True))
        )
        startup_layout.addWidget(self.show_mode_selector_cb)
        startup_row = QFormLayout()
        self.preferred_mode_combo = QComboBox()
        self.preferred_mode_combo.addItem("ぽえなび", POENAVI_MODE)
        self.preferred_mode_combo.addItem("ぽえとれ", POETORE_MODE)
        preferred = normalize_app_mode(
            startup.get("preferred_mode", POETORE_MODE)
        )
        self.preferred_mode_combo.setCurrentIndex(
            self.preferred_mode_combo.findData(preferred)
        )
        startup_row.addRow("次回起動するモード:", self.preferred_mode_combo)
        startup_layout.addLayout(startup_row)
        root.addWidget(startup_group)

        hotkeys = self.current_config.get("hotkeys")
        hotkeys = hotkeys if isinstance(hotkeys, dict) else {}
        hotkey_group = QGroupBox("共通・ぽえとれホットキー")
        hotkey_form = QFormLayout(hotkey_group)
        self.exit_hotkey = QLineEdit(hotkeys.get("exit", "F5"))
        self.capture_hotkey = QLineEdit(hotkeys.get("poetore_capture", "alt+d"))
        self.cheat_hotkey = QLineEdit(
            hotkeys.get("cheat_sheets_toggle", "shift+space")
        )
        hotkey_form.addRow("キャラクター選択へ戻る:", self.exit_hotkey)
        hotkey_form.addRow("ぽえとれ検索:", self.capture_hotkey)
        hotkey_form.addRow("Cheat sheets表示:", self.cheat_hotkey)
        root.addWidget(hotkey_group)

        common_group = QGroupBox("共通機能")
        common_layout = QVBoxLayout(common_group)
        self.stash_tab_scroll_cb = QCheckBox(
            "Ctrl＋マウスホイールでスタッシュタブを切り替える"
        )
        self.stash_tab_scroll_cb.setChecked(
            bool(self.current_config.get("stash_tab_scroll_enabled", True))
        )
        common_layout.addWidget(self.stash_tab_scroll_cb)
        root.addWidget(common_group)

        poetore = self.current_config.get("poetore")
        poetore = poetore if isinstance(poetore, dict) else {}
        trade_group = QGroupBox("価格データ")
        trade_form = QFormLayout(trade_group)
        self.league_edit = QLineEdit(str(poetore.get("league", "auto")))
        self.league_edit.setPlaceholderText("auto")
        trade_form.addRow("リーグ（autoで自動）:", self.league_edit)
        root.addWidget(trade_group)

        note = QLabel("変更は保存後すぐ反映されます。起動モードは次回起動時に切り替わります。")
        note.setWordWrap(True)
        note.setObjectName("settingsNote")
        root.addWidget(note)

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

    @staticmethod
    def _style_sheet():
        return f"""
            QDialog {{ background: {POETORE_THEME.background}; color: {POETORE_THEME.text}; }}
            QLabel, QCheckBox, QGroupBox {{ color: {POETORE_THEME.text}; }}
            QGroupBox {{
                border: 1px solid rgba(219, 134, 239, 0.5);
                border-radius: 7px;
                margin-top: 10px;
                padding-top: 7px;
            }}
            QGroupBox::title {{ color: {POETORE_THEME.accent}; padding: 0 5px; }}
            QLineEdit, QComboBox {{
                background: {POETORE_THEME.panel};
                color: {POETORE_THEME.text};
                border: 1px solid rgba(219, 134, 239, 0.55);
                border-radius: 5px;
                padding: 5px;
            }}
            QPushButton {{
                background: #241929;
                color: {POETORE_THEME.accent};
                border: 1px solid rgba(219, 134, 239, 0.65);
                border-radius: 5px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #382440; }}
            QLabel#settingsNote {{ color: {POETORE_THEME.muted_text}; font-size: 11px; }}
        """

    def get_settings(self):
        startup = dict(self.current_config.get("startup", {}))
        startup["show_mode_selector"] = self.show_mode_selector_cb.isChecked()
        startup["preferred_mode"] = normalize_app_mode(
            self.preferred_mode_combo.currentData()
        )
        hotkeys = dict(self.current_config.get("hotkeys", {}))
        hotkeys.update(
            {
                "exit": self.exit_hotkey.text().strip() or "none",
                "poetore_capture": self.capture_hotkey.text().strip() or "none",
                "cheat_sheets_toggle": self.cheat_hotkey.text().strip() or "none",
            }
        )
        poetore = dict(self.current_config.get("poetore", {}))
        poetore["league"] = self.league_edit.text().strip() or "auto"
        return {
            "startup": startup,
            "hotkeys": hotkeys,
            "stash_tab_scroll_enabled": self.stash_tab_scroll_cb.isChecked(),
            "poetore": poetore,
        }
