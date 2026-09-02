"""ぽえとれモード専用の軽量設定画面。"""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QApplication,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode
from src.ui.app_theme import POETORE_THEME, SETTINGS_THEME
from src.ui.app_info_widget import AppInfoWidget
from src.poetore.trade import (
    TradeApiError,
    available_pc_leagues,
    default_pc_league,
)
from src.utils.global_hotkeys import find_duplicate_hotkeys
from src.ui.custom_command_settings import CustomCommandSettingsWidget
from src.ui.settings_dialog import AutoHideHotkeyWidget, HotkeyButton
from src.utils.poe_version_data import POE1, POE2, POE_VERSION_ORDER, get_poe_label
from src.utils.feature_support import POETORE, is_feature_supported


class _LeagueSignals(QObject):
    ready = Signal(object)


class PoetoreSettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        current_config=None,
        update_check_callback=None,
    ):
        super().__init__(parent)
        self.current_config = current_config or {}
        self.poe_version = str(self.current_config.get("poe_version", POE1))
        self.update_check_callback = update_check_callback
        self._league_refresh_started = False
        self._league_signals = _LeagueSignals(self)
        self._league_signals.ready.connect(self._show_trade_leagues)
        self.setWindowTitle("設定")
        self.setMinimumSize(540, 620)
        self.resize(560, 760)
        self.setStyleSheet(self._style_sheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)
        tabs = QTabWidget()
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(12, 12, 12, 12)
        basic_layout.setSpacing(12)

        startup_group = QGroupBox("起動設定")
        startup_layout = QVBoxLayout(startup_group)
        startup_layout.addWidget(QLabel("PoEバージョン"))
        self.poe_version_group = QButtonGroup(self)
        self.poe_version_radios = {}
        for version in POE_VERSION_ORDER:
            radio = QRadioButton(get_poe_label(version))
            radio.setChecked(version == self.poe_version)
            self.poe_version_group.addButton(radio)
            self.poe_version_radios[version] = radio
            radio.toggled.connect(
                lambda checked, selected=version: self._on_poe_version_changed(selected, checked)
            )
            startup_layout.addWidget(radio)
        saved_version_mode = str(self.current_config.get("poe_version_mode", "ask"))

        startup = self.current_config.get("startup")
        startup = startup if isinstance(startup, dict) else {}
        startup_layout.addWidget(QLabel("起動モード"))
        preferred = normalize_app_mode(
            startup.get("preferred_mode", POETORE_MODE)
        )
        self.app_mode_group = QButtonGroup(self)
        self.app_mode_radios = {}
        for mode, label in (
            (POENAVI_MODE, "ぽえなび"),
            (POETORE_MODE, "ぽえとれ"),
        ):
            radio = QRadioButton(label)
            radio.setChecked(mode == preferred)
            self.app_mode_group.addButton(radio)
            self.app_mode_radios[mode] = radio
            startup_layout.addWidget(radio)
        self.skip_startup_selector_checkbox = QCheckBox("次回からこの設定で直接起動")
        self.skip_startup_selector_checkbox.setChecked(
            saved_version_mode in POE_VERSION_ORDER
            and not bool(startup.get("show_mode_selector", True))
        )
        startup_layout.addWidget(self.skip_startup_selector_checkbox)
        poe_note = QLabel("変更内容は次回起動時から適用されます。")
        poe_note.setObjectName("poeVersionNote")
        startup_layout.addWidget(poe_note)
        basic_layout.addWidget(startup_group)
        self._refresh_app_mode_availability()

        hotkeys = self.current_config.get("hotkeys")
        hotkeys = hotkeys if isinstance(hotkeys, dict) else {}
        hotkey_group = QGroupBox("共通・ぽえとれホットキー")
        hotkey_form = QFormLayout(hotkey_group)
        self.exit_hotkey = HotkeyButton(hotkeys.get("exit", "F5"))
        self.monastery_hotkey = HotkeyButton(hotkeys.get("monastery", "F12"))
        self.capture_hotkey = AutoHideHotkeyWidget(
            hotkeys.get("poetore_capture", "alt+d"), theme=SETTINGS_THEME
        )
        self.auto_hide_hotkey = AutoHideHotkeyWidget(
            hotkeys.get("poetore_auto_hide", "ctrl+d"), theme=SETTINGS_THEME
        )
        self.map_check_hotkey = HotkeyButton(hotkeys.get("map_check", "alt+f"))
        self.cheat_hotkey = HotkeyButton(
            hotkeys.get("cheat_sheets_toggle", "shift+space")
        )
        for button in (
            self.exit_hotkey, self.monastery_hotkey,
            self.map_check_hotkey, self.cheat_hotkey,
        ):
            # ぽえとれ画面の親スタイルを使い、操作だけぽえなびと共通化する。
            button.setStyleSheet("")
        self.capture_hotkey.key_button.setStyleSheet("")
        self.auto_hide_hotkey.key_button.setStyleSheet("")
        hotkey_form.addRow("キャラクター選択へ戻る:", self.exit_hotkey)
        self.monastery_label = QLabel("修道院へ移動（/monastery）:")
        hotkey_form.addRow(self.monastery_label, self.monastery_hotkey)
        hotkey_form.addRow("ぽえとれ検索（操作モード）:", self.capture_hotkey)
        hotkey_form.addRow("ぽえとれ検索（AUTO-HIDE）:", self.auto_hide_hotkey)
        self.map_check_label = QLabel("Map Modチェック:")
        hotkey_form.addRow(self.map_check_label, self.map_check_hotkey)
        hotkey_form.addRow("Cheat sheets表示:", self.cheat_hotkey)
        basic_layout.addWidget(hotkey_group)
        self._refresh_version_specific_controls()

        common_group = QGroupBox("共通機能")
        common_layout = QVBoxLayout(common_group)
        self.stash_tab_scroll_cb = QCheckBox(
            "Ctrl＋マウスホイールでスタッシュタブを切り替える"
        )
        self.stash_tab_scroll_cb.setChecked(
            bool(self.current_config.get("stash_tab_scroll_enabled", True))
        )
        self.stash_tab_scroll_cb.setToolTip(
            "Awakened PoE Tradeと同じ補助機能です。スタッシュ内ではPoE本体の操作に任せ、\n"
            "カーソルがスタッシュ外にある時だけ左右キーを送信します。PoEが最前面の時だけ有効です。"
        )
        common_layout.addWidget(self.stash_tab_scroll_cb)
        basic_layout.addWidget(common_group)

        poetore = self.current_config.get("poetore")
        poetore = poetore if isinstance(poetore, dict) else {}
        trade_group = QGroupBox("価格データ")
        trade_layout = QVBoxLayout(trade_group)
        trade_form = QFormLayout()
        self.league_combo = QComboBox()
        self.league_combo.setEditable(True)
        self.league_combo.setToolTip(
            "一覧から選択、またはプライベートリーグ名を直接入力"
        )
        league_key = "league_poe2" if self.poe_version == POE2 else "league"
        saved_league = str(poetore.get(league_key, "auto")).strip() or "auto"
        if self.poe_version == POE2:
            from src.poetore.poe2.trade import FALLBACK_LEAGUES, default_pc_league as poe2_default_pc_league
            auto_league = poe2_default_pc_league(FALLBACK_LEAGUES)
            self.league_combo.addItem(f"自動（現行SC: {auto_league}）", "auto")
            for league in FALLBACK_LEAGUES:
                label = f"{league.id}（HC）" if league.hardcore else league.id
                self.league_combo.addItem(label, league.id)
        else:
            self.league_combo.addItem("自動（現行SCを取得中）", "auto")
        if saved_league != "auto" and self.league_combo.findData(saved_league) < 0:
            self.league_combo.addItem(saved_league, saved_league)
        if saved_league != "auto":
            self.league_combo.setCurrentIndex(max(0, self.league_combo.findData(saved_league)))
        trade_form.addRow("リーグ:", self.league_combo)
        trade_layout.addLayout(trade_form)
        league_note = QLabel(
            "プライベートリーグで使う場合は、リーグ名を直接手打ちで入力してください。"
        )
        league_note.setObjectName("privateLeagueNote")
        league_note.setWordWrap(True)
        trade_layout.addWidget(league_note)
        basic_layout.addWidget(trade_group)

        display_group = QGroupBox("検索結果・マップチェック画面")
        display_form = QFormLayout(display_group)
        self.result_font_size_combo = QComboBox()
        self.result_font_size_combo.addItem("小", "small")
        self.result_font_size_combo.addItem("中", "medium")
        self.result_font_size_combo.addItem("大", "large")
        saved_result_font_size = str(
            poetore.get("result_font_size", "medium")
        ).casefold()
        result_font_index = self.result_font_size_combo.findData(
            saved_result_font_size
        )
        self.result_font_size_combo.setCurrentIndex(
            result_font_index if result_font_index >= 0
            else self.result_font_size_combo.findData("medium")
        )
        display_form.addRow("フォントサイズ:", self.result_font_size_combo)
        display_note = QLabel(
            "文字に合わせてボタンや入力欄、検索結果ウィンドウの大きさも調整します。"
        )
        display_note.setObjectName("resultFontSizeNote")
        display_note.setWordWrap(True)
        display_form.addRow("", display_note)
        self._reset_result_positions = False
        self.reset_result_positions_button = QPushButton("手動位置をリセット")
        self.reset_result_positions_button.setToolTip(
            "スタッシュ側・インベントリ側に保存した検索結果位置を両方消去します"
        )
        self.reset_result_positions_button.clicked.connect(
            self._mark_result_positions_for_reset
        )
        self.result_positions_reset_note = QLabel("")
        self.result_positions_reset_note.setObjectName("resultPositionsResetNote")
        reset_row = QHBoxLayout()
        reset_row.addWidget(self.reset_result_positions_button)
        reset_row.addWidget(self.result_positions_reset_note)
        reset_row.addStretch()
        display_form.addRow("検索結果の位置:", reset_row)
        basic_layout.addWidget(display_group)

        obs_streaming = poetore.get("obs_streaming", {})
        obs_streaming = obs_streaming if isinstance(obs_streaming, dict) else {}
        obs_group = QGroupBox("OBS配信")
        obs_layout = QVBoxLayout(obs_group)
        self.obs_streaming_enabled_cb = QCheckBox(
            "検索結果ウィンドウをOBS配信用にする"
        )
        self.obs_streaming_enabled_cb.setObjectName("obsStreamingEnabled")
        self.obs_streaming_enabled_cb.setChecked(
            bool(obs_streaming.get("enabled", False))
        )
        obs_layout.addWidget(self.obs_streaming_enabled_cb)
        obs_note = QLabel(
            "待機中はタイトルバーだけを表示し、検索すると検索結果を当該タイトルバーの下に"
            "展開します。OBSでは「ぽえとれ - 検索結果ウィンドウ」として認識されます。"
        )
        obs_note.setObjectName("obsStreamingNote")
        obs_note.setWordWrap(True)
        obs_layout.addWidget(obs_note)
        basic_layout.addWidget(obs_group)

        window_group = QGroupBox("ウィンドウ設定（本体・共通UI）")
        window_layout = QVBoxLayout(window_group)
        self.opacity_slider = self._slider_row(
            window_layout, "透過率:", self.current_config.get("window_opacity", 100), 5
        )
        self.text_opacity_slider = self._slider_row(
            window_layout, "文字透過率:", self.current_config.get("text_opacity", 100), 0
        )
        self.window_lock_check = QCheckBox("ウィンドウの移動・リサイズを禁止する")
        self.window_lock_check.setChecked(self.current_config.get("window_locked", False))
        window_layout.addWidget(self.window_lock_check)
        self.always_on_top_check = QCheckBox("常に最前面に表示する")
        self.always_on_top_check.setChecked(self.current_config.get("always_on_top", True))
        window_layout.addWidget(self.always_on_top_check)
        self.snap_right_edge_cb = QCheckBox("起動時にモニター右端に配置")
        self.snap_right_edge_cb.setChecked(
            self.current_config.get("snap_to_right_edge", False)
        )
        window_layout.addWidget(self.snap_right_edge_cb)

        monitor_row = QFormLayout()
        self.monitor_combo = QComboBox()
        screens = QApplication.screens()
        for index, screen in enumerate(screens):
            geometry = screen.geometry()
            name = f"モニター {index + 1}（{geometry.width()}x{geometry.height()}）"
            if screen == QApplication.primaryScreen():
                name += " [メイン]"
            self.monitor_combo.addItem(name, index)
        current_monitor = int(self.current_config.get("display_monitor", 0))
        if 0 <= current_monitor < len(screens):
            self.monitor_combo.setCurrentIndex(current_monitor)
        monitor_row.addRow("起動時の配置先:", self.monitor_combo)
        window_layout.addLayout(monitor_row)
        self.monitor_combo.setEnabled(self.snap_right_edge_cb.isChecked())
        self.snap_right_edge_cb.toggled.connect(self.monitor_combo.setEnabled)
        basic_layout.addWidget(window_group)

        note = QLabel(
            "変更は保存後すぐ反映されます。起動モードを変更した場合は、"
            "保存後に再起動を確認します。"
        )
        note.setWordWrap(True)
        note.setObjectName("settingsNote")
        basic_layout.addWidget(note)
        basic_layout.addStretch()
        basic_scroll = QScrollArea()
        basic_scroll.setWidgetResizable(True)
        basic_scroll.setFrameShape(QScrollArea.NoFrame)
        basic_scroll.setWidget(basic_tab)
        tabs.addTab(basic_scroll, "基本設定")
        self.custom_commands_widget = CustomCommandSettingsWidget(
            self.current_config.get("custom_commands", []), theme=SETTINGS_THEME
        )
        tabs.insertTab(1, self.custom_commands_widget, "任意コマンド設定")
        tabs.addTab(
            AppInfoWidget(
                SETTINGS_THEME,
                update_check_callback=self.update_check_callback,
            ),
            "アプリ情報",
        )
        root.addWidget(tabs)

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
        theme = SETTINGS_THEME
        return f"""
            QDialog {{ background: {theme.background}; color: {theme.text}; font-size: 13px; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: {theme.background};
            }}
            QLabel, QCheckBox, QRadioButton, QGroupBox {{ color: {theme.text}; }}
            QGroupBox {{
                background: {theme.panel};
                border: 1px solid #465046;
                border-radius: 7px;
                margin-top: 10px;
                padding-top: 7px;
            }}
            QGroupBox::title {{
                color: {theme.accent};
                font-weight: 600;
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }}
            QLineEdit, QComboBox {{
                background: #151A15;
                color: {theme.text};
                border: 1px solid #596359;
                border-radius: 5px;
                padding: 5px;
            }}
            QComboBox QAbstractItemView {{
                background: {theme.panel};
                color: {theme.text};
                selection-background-color: {theme.accent};
                selection-color: {theme.background};
            }}
            QTabWidget::pane {{ border: 1px solid #465046; }}
            QTabBar::tab {{
                background: {theme.panel}; color: {theme.text};
                border: 1px solid #465046;
                padding: 7px 14px;
            }}
            QTabBar::tab:selected {{ color: {theme.accent}; border-bottom-color: {theme.accent}; font-weight: 600; }}
            QSlider::groove:horizontal {{ background: #555; height: 6px; border-radius: 3px; }}
            QSlider::handle:horizontal {{
                background: {theme.accent}; width: 16px;
                margin: -5px 0; border-radius: 8px;
            }}
            QPushButton {{
                background: {theme.panel};
                color: {theme.text};
                border: 1px solid #596359;
                border-radius: 5px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #293229; border-color: {theme.accent}; }}
            QPushButton:focus {{ border-color: {theme.accent}; }}
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {theme.accent}; }}
            QLabel#settingsNote {{ color: {theme.muted_text}; font-size: 13px; }}
            QLabel#privateLeagueNote {{
                color: {theme.muted_text};
                font-size: 13px;
            }}
            QLabel#resultFontSizeNote {{
                color: {theme.muted_text};
                font-size: 13px;
            }}
        """

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_trade_leagues()

    def _refresh_trade_leagues(self):
        if self._league_refresh_started:
            return
        self._league_refresh_started = True

        def run():
            try:
                if self.poe_version == POE2:
                    from src.poetore.poe2.trade import available_pc_leagues as poe2_available_pc_leagues
                    leagues = poe2_available_pc_leagues()
                else:
                    leagues = available_pc_leagues()
            except Exception:
                if self.poe_version == POE2:
                    from src.poetore.poe2.trade import FALLBACK_LEAGUES
                    leagues = FALLBACK_LEAGUES
                else:
                    leagues = ()
            self._league_signals.ready.emit(leagues)

        threading.Thread(target=run, daemon=True).start()

    def _show_trade_leagues(self, leagues):
        saved = self._league_selection_value()
        if self.poe_version == POE2:
            from src.poetore.poe2.trade import default_pc_league as poe2_default_pc_league
            auto_league = poe2_default_pc_league(tuple(leagues))
        else:
            auto_league = default_pc_league(tuple(leagues))
        self.league_combo.blockSignals(True)
        self.league_combo.clear()
        self.league_combo.addItem(f"自動（現行SC: {auto_league}）", "auto")
        for league in leagues:
            label = f"{league.id}（HC）" if league.hardcore else league.id
            self.league_combo.addItem(label, league.id)
        if saved != "auto" and self.league_combo.findData(saved) < 0:
            self.league_combo.addItem(saved, saved)
        self.league_combo.setCurrentIndex(
            max(0, self.league_combo.findData(saved))
        )
        self.league_combo.blockSignals(False)

    def _league_selection_value(self):
        index = self.league_combo.currentIndex()
        text = self.league_combo.currentText().strip()
        if index >= 0 and text == self.league_combo.itemText(index):
            value = self.league_combo.itemData(index)
            if value:
                return str(value)
        return text or "auto"

    @staticmethod
    def _slider_row(layout, label_text, value, minimum):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        slider = QSlider()
        slider.setOrientation(Qt.Horizontal)
        slider.setRange(minimum, 100)
        slider.setValue(int(value))
        value_label = QLabel(f"{slider.value()}%")
        value_label.setFixedWidth(40)
        slider.valueChanged.connect(lambda new_value: value_label.setText(f"{new_value}%"))
        row.addWidget(slider)
        row.addWidget(value_label)
        layout.addLayout(row)
        return slider

    def _on_poe_version_changed(self, poe_version, checked):
        if not checked:
            return
        self.poe_version = poe_version
        self._refresh_app_mode_availability()
        self._refresh_version_specific_controls()

    def _refresh_version_specific_controls(self):
        """選択中のゲーム版で利用できる設定だけを表示する。"""
        monastery_visible = self.poe_version == POE1
        self.monastery_label.setVisible(monastery_visible)
        self.monastery_hotkey.setVisible(monastery_visible)
        self.map_check_label.setVisible(monastery_visible)
        self.map_check_hotkey.setVisible(monastery_visible)

    def _refresh_app_mode_availability(self):
        supported = is_feature_supported(POETORE, self.poe_version)
        poetore_radio = self.app_mode_radios[POETORE_MODE]
        poetore_radio.setEnabled(supported)
        poetore_radio.setToolTip("" if supported else "PoE2版は現在テスト中です")
        if not supported:
            if poetore_radio.isChecked():
                self.app_mode_radios[POENAVI_MODE].setChecked(True)

    def get_settings(self):
        selected_poe_version = next(
            (
                version for version, radio in self.poe_version_radios.items()
                if radio.isChecked()
            ),
            self.poe_version,
        )
        startup = dict(self.current_config.get("startup", {}))
        selected_app_mode = next(
            (
                mode for mode, radio in self.app_mode_radios.items()
                if radio.isChecked()
            ),
            POETORE_MODE,
        )
        if not is_feature_supported(POETORE, selected_poe_version):
            selected_app_mode = POENAVI_MODE
        skip_selector = self.skip_startup_selector_checkbox.isChecked()
        startup["show_mode_selector"] = not skip_selector
        startup["preferred_mode"] = normalize_app_mode(selected_app_mode)
        hotkeys = dict(self.current_config.get("hotkeys", {}))
        hotkeys.update(
            {
                "exit": self.exit_hotkey.key_text,
                "monastery": self.monastery_hotkey.key_text,
                "poetore_capture": self.capture_hotkey.key_text,
                "poetore_auto_hide": self.auto_hide_hotkey.key_text,
                "map_check": self.map_check_hotkey.key_text,
                "cheat_sheets_toggle": self.cheat_hotkey.key_text,
            }
        )
        poetore = dict(self.current_config.get("poetore", {}))
        league_key = "league_poe2" if self.poe_version == POE2 else "league"
        poetore[league_key] = self._league_selection_value()
        poetore["result_font_size"] = (
            self.result_font_size_combo.currentData() or "medium"
        )
        obs_streaming = dict(poetore.get("obs_streaming", {}))
        obs_streaming["enabled"] = self.obs_streaming_enabled_cb.isChecked()
        poetore["obs_streaming"] = obs_streaming
        if self._reset_result_positions:
            poetore.pop("result_positions", None)
        return {
            "startup": startup,
            "hotkeys": hotkeys,
            "custom_commands": self.custom_commands_widget.commands(),
            "stash_tab_scroll_enabled": self.stash_tab_scroll_cb.isChecked(),
            "poetore": poetore,
            "poe_version": selected_poe_version,
            "poe_version_mode": selected_poe_version if skip_selector else "ask",
            "window_opacity": self.opacity_slider.value(),
            "text_opacity": self.text_opacity_slider.value(),
            "window_locked": self.window_lock_check.isChecked(),
            "always_on_top": self.always_on_top_check.isChecked(),
            "display_monitor": self.monitor_combo.currentData(),
            "snap_to_right_edge": self.snap_right_edge_cb.isChecked(),
        }

    def _mark_result_positions_for_reset(self):
        self._reset_result_positions = True
        self.result_positions_reset_note.setText("保存時にリセットします")
        self.reset_result_positions_button.setEnabled(False)

    def accept(self):
        hotkeys = {
            "exit": self.exit_hotkey.key_text,
            "monastery": self.monastery_hotkey.key_text,
            "poetore_capture": self.capture_hotkey.key_text,
            "poetore_auto_hide": self.auto_hide_hotkey.key_text,
            "map_check": self.map_check_hotkey.key_text,
            "cheat_sheets_toggle": self.cheat_hotkey.key_text,
        }
        if self.poe_version == POE2:
            hotkeys.pop("map_check")
        if not self.custom_commands_widget.validate(hotkeys):
            return
        duplicates = find_duplicate_hotkeys(hotkeys)
        if duplicates:
            labels = {
                "exit": "キャラクター選択へ戻る",
                "monastery": "修道院へ移動",
                "poetore_capture": "ぽえとれ検索（操作モード）",
                "poetore_auto_hide": "ぽえとれ検索（AUTO-HIDE）",
                "map_check": "Map Modチェック",
                "cheat_sheets_toggle": "Cheat sheets表示",
            }
            details = "\n".join(
                f"{key}: {'、'.join(labels[action] for action in actions)}"
                for key, actions in duplicates.items()
            )
            QMessageBox.warning(
                self,
                "ホットキー重複",
                f"同じキーが複数の操作に設定されています。\n\n{details}",
            )
            return
        super().accept()
