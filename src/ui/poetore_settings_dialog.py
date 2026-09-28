"""ぽえとれモード専用の軽量設定画面。"""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
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
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode
from src.poetore.hideout_notification import (
    normalize_hideout_notification_settings,
)
from src.poetore.notification_audio import (
    NotificationAudioPlayer,
    bundled_audio_path,
    copy_custom_audio,
    custom_audio_path,
)
from src.poetore.trade import (
    available_pc_leagues,
    default_pc_league,
)
from src.ui.app_info_widget import AppInfoWidget
from src.ui.custom_command_settings import CustomCommandSettingsWidget
from src.ui.dialog_theme import (
    POETORE_DIALOG_THEME,
    apply_dialog_theme,
    build_dialog_stylesheet,
)
from src.ui.settings_dialog import AutoHideHotkeyWidget, HotkeyButton
from src.utils.feature_support import POETORE, is_feature_supported
from src.utils.global_hotkeys import find_duplicate_hotkeys
from src.utils.poe_version_data import POE1, POE2, POE_VERSION_ORDER, get_poe_label


class _LeagueSignals(QObject):
    ready = Signal(object)


class PoetoreSettingsDialog(QDialog):
    @staticmethod
    def _style_sheet():
        return build_dialog_stylesheet(POETORE_DIALOG_THEME)

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
        self.setObjectName("poetoreSettingsDialog")
        self.setMinimumSize(540, 620)
        self.resize(560, 760)
        self.theme = POETORE_DIALOG_THEME
        apply_dialog_theme(self, self.theme)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)
        self.title_label = QLabel("設定")
        self.title_label.setProperty("uiRole", "title")
        root.addWidget(self.title_label)
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
        self.startup_change_note = QLabel(
            "PoEバージョン・起動モードの変更は、次回起動時から適用されます。"
        )
        self.startup_change_note.setObjectName("startupChangeNote")
        self.startup_change_note.setProperty("uiRole", "muted")
        self.startup_change_note.setWordWrap(True)
        startup_layout.addWidget(self.startup_change_note)
        startup_layout.addSpacing(13)
        self.windows_autostart_poetore_checkbox = QCheckBox(
            "Windowsログイン時にぽえとれを自動起動"
        )
        self.windows_autostart_poetore_checkbox.setChecked(
            bool(startup.get("windows_autostart_poetore", False))
        )
        startup_layout.addWidget(self.windows_autostart_poetore_checkbox)
        self.windows_autostart_note = QLabel(
            "有効にすると、次回のWindowsログイン時からぽえとれを自動起動します。"
        )
        self.windows_autostart_note.setObjectName("windowsAutostartNote")
        self.windows_autostart_note.setProperty("uiRole", "muted")
        self.windows_autostart_note.setWordWrap(True)
        startup_layout.addWidget(self.windows_autostart_note)
        basic_layout.addWidget(startup_group)
        self._refresh_app_mode_availability()

        hotkeys = self.current_config.get("hotkeys")
        hotkeys = hotkeys if isinstance(hotkeys, dict) else {}
        hotkey_group = QGroupBox("共通・ぽえとれホットキー")
        hotkey_form = QFormLayout(hotkey_group)
        self.exit_hotkey = HotkeyButton(hotkeys.get("exit", "F5"))
        self.monastery_hotkey = HotkeyButton(hotkeys.get("monastery", "F12"))
        self.capture_hotkey = AutoHideHotkeyWidget(
            hotkeys.get("poetore_capture", "alt+d"), theme=self.theme,
            allow_no_modifier=True,
        )
        self.auto_hide_hotkey = AutoHideHotkeyWidget(
            hotkeys.get("poetore_auto_hide", "ctrl+d"), theme=self.theme
        )
        self.map_check_hotkey = HotkeyButton(hotkeys.get("map_check", "alt+f"))
        self.cheat_hotkey = HotkeyButton(
            hotkeys.get("cheat_sheets_toggle", "shift+space")
        )
        self._expedition_hotkey = str(
            hotkeys.get("expedition_reward_ocr", "alt+e")
        )
        self._desecration_hotkey = str(
            hotkeys.get("desecration_tier_ocr", "alt+r")
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

        error_group = QGroupBox("検索時のエラー処理")
        error_layout = QVBoxLayout(error_group)
        poetore = self.current_config.get("poetore")
        poetore = poetore if isinstance(poetore, dict) else {}
        self.capture_error_notification_cb = QCheckBox(
            "アイテムを取得できなかったときに通知する"
        )
        self.capture_error_notification_cb.setChecked(
            bool(poetore.get("capture_error_notification_enabled", False))
        )
        error_layout.addWidget(self.capture_error_notification_cb)
        basic_layout.addWidget(error_group)

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

        hideout_settings = normalize_hideout_notification_settings(
            poetore.get("hideout_notification")
        )
        hideout_group = QGroupBox("隠れ家滞在通知")
        hideout_layout = QVBoxLayout(hideout_group)
        hideout_form = QFormLayout()
        duration_row = QHBoxLayout()
        self.hideout_minutes_spin = QSpinBox()
        self.hideout_minutes_spin.setRange(0, 60)
        self.hideout_minutes_spin.setSuffix(" 分")
        self.hideout_seconds_spin = QSpinBox()
        self.hideout_seconds_spin.setRange(0, 59)
        self.hideout_seconds_spin.setSuffix(" 秒")
        minutes, seconds = divmod(hideout_settings["duration_seconds"], 60)
        self.hideout_minutes_spin.setValue(minutes)
        self.hideout_seconds_spin.setValue(seconds)
        self.hideout_minutes_spin.valueChanged.connect(
            self._limit_hideout_duration
        )
        self._limit_hideout_duration(self.hideout_minutes_spin.value())
        duration_row.addWidget(self.hideout_minutes_spin)
        duration_row.addWidget(self.hideout_seconds_spin)
        duration_row.addStretch()
        hideout_form.addRow("通知までの時間:", duration_row)
        self.hideout_repeat_cb = QCheckBox("通知を繰り返す")
        self.hideout_repeat_cb.setChecked(hideout_settings["repeat"])
        hideout_form.addRow("", self.hideout_repeat_cb)
        self._hideout_audio_source = hideout_settings["audio_source"]
        self._hideout_audio_file = hideout_settings["custom_audio_file"]
        self._hideout_audio_display_name = hideout_settings[
            "custom_audio_display_name"
        ]
        self.hideout_audio_name = QLabel()
        self._refresh_hideout_audio_name()
        audio_row = QHBoxLayout()
        audio_row.addWidget(self.hideout_audio_name, 1)
        self.hideout_audio_select_button = QPushButton("選択")
        self.hideout_audio_select_button.clicked.connect(
            self._select_hideout_audio
        )
        audio_row.addWidget(self.hideout_audio_select_button)
        self.hideout_audio_reset_button = QPushButton("標準に戻す")
        self.hideout_audio_reset_button.clicked.connect(
            self._reset_hideout_audio
        )
        audio_row.addWidget(self.hideout_audio_reset_button)
        hideout_form.addRow("通知音声:", audio_row)
        volume_row = QHBoxLayout()
        self.hideout_volume_slider = QSlider(Qt.Horizontal)
        self.hideout_volume_slider.setRange(0, 100)
        self.hideout_volume_slider.setValue(hideout_settings["volume"])
        self.hideout_volume_label = QLabel()
        self.hideout_volume_slider.valueChanged.connect(
            self._refresh_hideout_volume_label
        )
        self._refresh_hideout_volume_label()
        volume_row.addWidget(self.hideout_volume_slider, 1)
        volume_row.addWidget(self.hideout_volume_label)
        hideout_form.addRow("音量:", volume_row)
        log_paths = self.current_config.get("client_log_paths")
        log_paths = log_paths if isinstance(log_paths, dict) else {}
        log_row = QHBoxLayout()
        self.hideout_log_path_edit = QLineEdit(
            str(log_paths.get(self.poe_version, "") or "")
        )
        self.hideout_log_path_edit.setPlaceholderText("Client.txtを選択")
        log_row.addWidget(self.hideout_log_path_edit, 1)
        self.hideout_log_path_button = QPushButton("参照")
        self.hideout_log_path_button.clicked.connect(
            self._select_hideout_log_path
        )
        log_row.addWidget(self.hideout_log_path_button)
        hideout_form.addRow("Client.txt:", log_row)
        hideout_layout.addLayout(hideout_form)
        self.hideout_preview_button = QPushButton("試聴")
        self.hideout_preview_button.clicked.connect(self._preview_hideout_audio)
        hideout_layout.addWidget(self.hideout_preview_button)
        hideout_note = QLabel(
            "集中モード中、隠れ家に設定時間滞在すると音声でお知らせします。\n"
            "音量50が音声本来の大きさで、50より上は増幅します。"
        )
        hideout_note.setProperty("uiRole", "muted")
        hideout_note.setWordWrap(True)
        hideout_layout.addWidget(hideout_note)
        self._hideout_preview_player = None
        basic_layout.addWidget(hideout_group)

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
            from src.poetore.poe2.trade import FALLBACK_LEAGUES
            from src.poetore.poe2.trade import (
                default_pc_league as poe2_default_pc_league,
            )
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
        league_row = QHBoxLayout()
        league_row.setContentsMargins(0, 0, 0, 0)
        league_row.setSpacing(6)
        league_row.addWidget(self.league_combo, 1)
        self.league_refresh_button = QPushButton("再取得")
        self.league_refresh_button.setObjectName("leagueRefreshButton")
        self.league_refresh_button.setToolTip("公式サイトからリーグ一覧を再取得")
        self.league_refresh_button.setFixedWidth(72)
        self.league_refresh_button.clicked.connect(
            lambda: self._refresh_trade_leagues(force_refresh=True)
        )
        league_row.addWidget(self.league_refresh_button)
        trade_form.addRow("リーグ:", league_row)
        trade_layout.addLayout(trade_form)
        league_note = QLabel(
            "プライベートリーグで使う場合は、リーグ名を直接手打ちで入力してください。"
        )
        league_note.setObjectName("privateLeagueNote")
        league_note.setProperty("uiRole", "muted")
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
        display_note.setProperty("uiRole", "muted")
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
        self.obs_title_bar_opacity_slider = self._slider_row(
            obs_layout,
            "透過率:",
            obs_streaming.get("title_bar_opacity", 100),
            0,
        )
        self.obs_title_bar_opacity_slider.setObjectName("obsTitleBarOpacity")
        self.obs_title_bar_opacity_slider.setToolTip(
            "待機中に表示される「ぽえとれ検索ウィンドウ」バーの透過率"
        )
        obs_note = QLabel(
            "待機中はタイトルバーだけを表示し、検索すると検索結果を当該タイトルバーの下に"
            "展開します。OBSでは「ぽえとれ - 検索結果ウィンドウ」として認識されます。\n"
            "待機中のタイトルバーは透過率を変更できます。"
        )
        obs_note.setObjectName("obsStreamingNote")
        obs_note.setProperty("uiRole", "muted")
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
        note.setProperty("uiRole", "muted")
        basic_layout.addWidget(note)
        basic_layout.addStretch()
        basic_scroll = QScrollArea()
        basic_scroll.setWidgetResizable(True)
        basic_scroll.setFrameShape(QScrollArea.NoFrame)
        basic_scroll.setWidget(basic_tab)
        tabs.addTab(basic_scroll, "基本設定")
        self.custom_commands_widget = CustomCommandSettingsWidget(
            self.current_config.get("custom_commands", []), theme=self.theme
        )
        tabs.insertTab(1, self.custom_commands_widget, "任意コマンド設定")
        self.app_info_widget = AppInfoWidget(
            self.theme,
            update_check_callback=self.update_check_callback,
        )
        tabs.addTab(self.app_info_widget, "アプリ情報")
        root.addWidget(tabs)

        self.footer_layout = QHBoxLayout()
        self.footer_layout.addStretch()
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setProperty("buttonRole", "secondary")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("保存")
        self.save_button.setProperty("buttonRole", "primary")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        self.footer_layout.addWidget(self.cancel_button)
        self.footer_layout.addWidget(self.save_button)
        root.addLayout(self.footer_layout)

        self._clear_legacy_control_styles()

    def _clear_legacy_control_styles(self):
        """ぽえとれ設定内だけ、旧インラインQSSを共通テーマへ委譲する。"""
        from PySide6.QtWidgets import (
            QDoubleSpinBox,
            QLineEdit,
            QSpinBox,
            QTableWidget,
            QTextEdit,
        )

        widget_types = (
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QGroupBox,
            QLineEdit,
            QPushButton,
            QRadioButton,
            QScrollArea,
            QSlider,
            QSpinBox,
            QTableWidget,
            QTabWidget,
            QTextEdit,
        )
        for widget_type in widget_types:
            for widget in self.findChildren(widget_type):
                widget.setStyleSheet("")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_trade_leagues()

    def _refresh_trade_leagues(self, *, force_refresh: bool = False):
        if self._league_refresh_started:
            return
        self._league_refresh_started = True
        self.league_refresh_button.setEnabled(False)
        self.league_refresh_button.setText("取得中…")

        def run():
            try:
                if self.poe_version == POE2:
                    from src.poetore.poe2.trade import (
                        available_pc_leagues as poe2_available_pc_leagues,
                    )
                    leagues = poe2_available_pc_leagues(force_refresh=force_refresh)
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
        self._league_refresh_started = False
        self.league_refresh_button.setEnabled(True)
        self.league_refresh_button.setText("再取得")
        saved = self._league_selection_value()
        if self.poe_version == POE2:
            from src.poetore.poe2.trade import (
                default_pc_league as poe2_default_pc_league,
            )
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
        startup["windows_autostart_poetore"] = (
            self.windows_autostart_poetore_checkbox.isChecked()
        )
        hotkeys = dict(self.current_config.get("hotkeys", {}))
        hotkeys.update(
            {
                "exit": self.exit_hotkey.key_text,
                "monastery": self.monastery_hotkey.key_text,
                "poetore_capture": self.capture_hotkey.key_text,
                "poetore_auto_hide": self.auto_hide_hotkey.key_text,
                "expedition_reward_ocr": self._expedition_hotkey,
                "desecration_tier_ocr": self._desecration_hotkey,
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
        poetore["capture_error_notification_enabled"] = (
            self.capture_error_notification_cb.isChecked()
        )
        hideout_settings = normalize_hideout_notification_settings({
            "duration_seconds": (
                self.hideout_minutes_spin.value() * 60
                + self.hideout_seconds_spin.value()
            ),
            "repeat": self.hideout_repeat_cb.isChecked(),
            "audio_source": self._hideout_audio_source,
            "custom_audio_display_name": self._hideout_audio_display_name,
            "custom_audio_file": self._hideout_audio_file,
            "volume": self.hideout_volume_slider.value(),
        })
        poetore["hideout_notification"] = hideout_settings
        obs_streaming = dict(poetore.get("obs_streaming", {}))
        obs_streaming["enabled"] = self.obs_streaming_enabled_cb.isChecked()
        obs_streaming["title_bar_opacity"] = (
            self.obs_title_bar_opacity_slider.value()
        )
        poetore["obs_streaming"] = obs_streaming
        if self._reset_result_positions:
            poetore.pop("result_positions", None)
        return {
            "startup": startup,
            "hotkeys": hotkeys,
            "custom_commands": self.custom_commands_widget.commands(),
            "stash_tab_scroll_enabled": self.stash_tab_scroll_cb.isChecked(),
            "poetore": poetore,
            "client_log_paths": {
                **dict(self.current_config.get("client_log_paths", {})),
                self.poe_version: self.hideout_log_path_edit.text().strip(),
            },
            "poe_version": selected_poe_version,
            "poe_version_mode": selected_poe_version if skip_selector else "ask",
            "window_opacity": self.opacity_slider.value(),
            "text_opacity": self.text_opacity_slider.value(),
            "window_locked": self.window_lock_check.isChecked(),
            "always_on_top": self.always_on_top_check.isChecked(),
            "display_monitor": self.monitor_combo.currentData(),
            "snap_to_right_edge": self.snap_right_edge_cb.isChecked(),
        }

    def _limit_hideout_duration(self, minutes):
        if int(minutes) >= 60:
            self.hideout_seconds_spin.setMinimum(0)
            self.hideout_seconds_spin.setValue(0)
            self.hideout_seconds_spin.setEnabled(False)
        else:
            self.hideout_seconds_spin.setEnabled(True)
            self.hideout_seconds_spin.setMinimum(10 if int(minutes) == 0 else 0)

    def _refresh_hideout_volume_label(self, *_args):
        value = self.hideout_volume_slider.value()
        self.hideout_volume_label.setText(
            f"{value}（標準）" if value == 50 else str(value)
        )

    def _refresh_hideout_audio_name(self):
        name = (
            self._hideout_audio_display_name
            if self._hideout_audio_source == "custom"
            else "標準（ずんだもん）"
        )
        self.hideout_audio_name.setText(name)
        self.hideout_audio_name.setToolTip(name)

    def _select_hideout_audio(self):
        source, _selected_filter = QFileDialog.getOpenFileName(
            self, "通知音声を選択", "", "音声ファイル (*.wav *.mp3)"
        )
        if not source:
            return
        try:
            display_name, stored_name = copy_custom_audio(source)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "通知音声", str(error))
            return
        self._hideout_audio_source = "custom"
        self._hideout_audio_display_name = display_name
        self._hideout_audio_file = stored_name
        self._refresh_hideout_audio_name()

    def _select_hideout_log_path(self):
        source, _selected_filter = QFileDialog.getOpenFileName(
            self, "Client.txtを選択", "", "PoEクライアントログ (Client.txt)"
        )
        if source:
            self.hideout_log_path_edit.setText(source)

    def _reset_hideout_audio(self):
        self._hideout_audio_source = "bundled"
        self._hideout_audio_display_name = ""
        self._hideout_audio_file = ""
        self._refresh_hideout_audio_name()

    def _preview_hideout_audio(self):
        if self._hideout_preview_player is None:
            self._hideout_preview_player = NotificationAudioPlayer(self)
            self._hideout_preview_player.failed.connect(
                lambda text: QMessageBox.warning(self, "通知音声", text)
            )
            self._hideout_preview_player.fallback_used.connect(
                lambda text: QMessageBox.information(self, "通知音声", text)
            )
        primary = bundled_audio_path()
        if self._hideout_audio_source == "custom":
            primary = custom_audio_path(self._hideout_audio_file)
        self._hideout_preview_player.play(
            primary, bundled_audio_path(), self.hideout_volume_slider.value()
        )

    def done(self, result):
        if self._hideout_preview_player is not None:
            self._hideout_preview_player.stop()
        super().done(result)

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
            "expedition_reward_ocr": self._expedition_hotkey,
            "desecration_tier_ocr": self._desecration_hotkey,
            "map_check": self.map_check_hotkey.key_text,
            "cheat_sheets_toggle": self.cheat_hotkey.key_text,
        }
        if self.poe_version == POE2:
            hotkeys.pop("map_check")
        else:
            hotkeys.pop("expedition_reward_ocr")
            hotkeys.pop("desecration_tier_ocr")
        if not self.custom_commands_widget.validate(hotkeys):
            return
        duplicates = find_duplicate_hotkeys(hotkeys)
        if duplicates:
            labels = {
                "exit": "キャラクター選択へ戻る",
                "monastery": "修道院へ移動",
                "poetore_capture": "ぽえとれ検索（操作モード）",
                "poetore_auto_hide": "ぽえとれ検索（AUTO-HIDE）",
                "expedition_reward_ocr": "エクスペディション報酬読取",
                "desecration_tier_ocr": "アビス冒涜Modティア読取",
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
