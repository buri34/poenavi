"""ぽえとれモードの軽量メイン画面。"""

from pathlib import Path
import threading

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import Styles
from src.ui.app_theme import POETORE_THEME
from src.utils.chat_command import send_chat_command
from src.utils.config_manager import ConfigManager
from src.utils.global_hotkeys import GlobalHotkeyService
from src.utils.poe_version_data import POE1, POE2
from src.utils.stash_tab_scroll import StashTabScrollController


POETORE_ACCENT = POETORE_THEME.accent
POETORE_TEXT = POETORE_THEME.text
RATE_REFRESH_MSEC = 31 * 60 * 1000


class _RateSignals(QObject):
    ready = Signal(str, float)
    failed = Signal(str)


class PoetoreModeWindow(QMainWindow):
    MODE_ACTION_DEFAULTS = {
        "exit": "F5",
        "poetore_capture": "alt+d",
        "cheat_sheets_toggle": "shift+space",
    }

    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load_config()
        self._cheat_sheet_overlay = None
        self._memo_dialog = None
        self._rate_request_running = False
        self._rate_signals = _RateSignals(self)
        self._rate_signals.ready.connect(self._show_rate)
        self._rate_signals.failed.connect(self._show_rate_error)

        self.setWindowTitle("ぽえとれ")
        self.setMinimumSize(520, 300)
        self.resize(620, 360)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self._build_ui()

        self.stash_tab_scroll = StashTabScrollController(
            enabled=self.config.get("stash_tab_scroll_enabled", True)
        )
        self.stash_tab_scroll.start()
        self._start_hotkeys()

        self._rate_timer = QTimer(self)
        self._rate_timer.setInterval(RATE_REFRESH_MSEC)
        self._rate_timer.timeout.connect(self.refresh_currency_rate)
        self._rate_timer.start()
        QTimer.singleShot(0, self.refresh_currency_rate)

    @staticmethod
    def _asset_path(filename):
        return Path(__file__).resolve().parents[2] / "assets" / "icons" / filename

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("poetoreModeRoot")
        central.setStyleSheet(f"""
            QWidget#poetoreModeRoot {{
                background: {POETORE_THEME.background};
                color: {POETORE_TEXT};
            }}
            QFrame#rateCard {{
                background: {POETORE_THEME.panel};
                border: 1px solid rgba(219, 134, 239, 0.42);
                border-radius: 10px;
            }}
            QPushButton {{
                background: #241929;
                color: {POETORE_ACCENT};
                border: 1px solid rgba(219, 134, 239, 0.55);
                border-radius: 7px;
                padding: 7px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #382440; border-color: {POETORE_ACCENT}; }}
            QPushButton:pressed {{ background: #4A2D54; }}
        """)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("ぽえとれ")
        title.setStyleSheet(
            f"color: {POETORE_ACCENT}; font-size: 26px; font-weight: bold;"
        )
        subtitle = QLabel("価格チェック・トレード支援")
        subtitle.setStyleSheet(
            f"color: {POETORE_THEME.muted_text}; font-size: 12px;"
        )
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.memo_button = self._header_button("📝", "共通メモを開く")
        self.cheat_sheets_button = self._header_button(
            "🖼", "Cheat sheetsの画像を登録・管理"
        )
        self.settings_button = self._header_button("⚙", "設定画面を開く")
        self.memo_button.clicked.connect(self.open_memo)
        self.cheat_sheets_button.clicked.connect(self.open_cheat_sheet_manager)
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.memo_button)
        header.addWidget(self.cheat_sheets_button)
        header.addWidget(self.settings_button)
        root.addLayout(header)

        section_title = QLabel("Divine / Chaos 換算")
        section_title.setStyleSheet(
            f"color: {POETORE_ACCENT}; font-size: 15px; font-weight: bold;"
        )
        root.addWidget(section_title)

        self.divine_rate_value = QLabel("取得中…")
        root.addWidget(self._rate_card(self.divine_rate_value))

        footer = QHBoxLayout()
        self.rate_status = QLabel("poe.ninjaから現在のレートを取得しています")
        self.rate_status.setStyleSheet("color: #A897AE; font-size: 11px;")
        self.rate_status.setWordWrap(True)
        footer.addWidget(self.rate_status, 1)
        refresh_button = QPushButton("更新")
        refresh_button.setToolTip("現在の換算レートを再取得")
        refresh_button.clicked.connect(self.refresh_currency_rate)
        footer.addWidget(refresh_button)
        root.addLayout(footer)
        root.addStretch()
        self.setCentralWidget(central)

    def _header_button(self, text, tooltip):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setFixedSize(35, 35)
        return button

    def _rate_card(self, value_label):
        card = QFrame()
        card.setObjectName("rateCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        divine_icon = QLabel()
        divine_icon.setObjectName("divineCurrencyIcon")
        divine_pixmap = QPixmap(str(self._asset_path("DivineOrb.png")))
        divine_icon.setPixmap(divine_pixmap.scaled(
            QSize(52, 52),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        ))
        divine_icon.setFixedSize(52, 52)
        divine_icon.setToolTip("Divine Orb")
        layout.addWidget(divine_icon)
        value_label.setStyleSheet(
            f"color: {POETORE_TEXT}; font-size: 20px; font-weight: bold;"
        )
        layout.addWidget(value_label)
        chaos_icon = QLabel()
        chaos_icon.setObjectName("chaosCurrencyIcon")
        chaos_pixmap = QPixmap(str(self._asset_path("ChaosOrb.png")))
        chaos_icon.setPixmap(chaos_pixmap.scaled(
            QSize(46, 46),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        ))
        chaos_icon.setFixedSize(46, 46)
        chaos_icon.setToolTip("Chaos Orb")
        layout.addWidget(chaos_icon)
        layout.addStretch()
        return card

    def _start_hotkeys(self):
        configured = self.config.get("hotkeys", {})
        mode_hotkeys = {
            action: configured.get(action, default)
            for action, default in self.MODE_ACTION_DEFAULTS.items()
        }
        self.hotkey_service = GlobalHotkeyService(mode_hotkeys, parent=self)
        self.hotkey_service.command.connect(self.handle_hotkey)
        self.hotkey_service.start()

    @property
    def active_service_names(self):
        names = {"global_hotkeys", "stash_tab_scroll", "currency_rate_refresh"}
        if self._cheat_sheet_overlay is not None:
            names.add("cheat_sheets")
        return frozenset(names)

    def _configured_league(self):
        return str(self.config.get("poetore", {}).get("league", "auto"))

    def refresh_currency_rate(self):
        if self._rate_request_running:
            return
        self._rate_request_running = True
        self.rate_status.setText("poe.ninjaから現在のレートを取得しています")

        def run():
            try:
                from src.poetore.poe_ninja import default_poe_ninja_service
                from src.poetore.trade import available_pc_leagues, default_pc_league

                configured = self._configured_league()
                league = (
                    default_pc_league(available_pc_leagues())
                    if configured == "auto"
                    else configured
                )
                rate = default_poe_ninja_service.divine_chaos_rate(league)
                if rate is None:
                    raise ValueError("Divine Orbの換算レートが見つかりませんでした。")
                self._rate_signals.ready.emit(league, rate)
            except Exception as exc:
                self._rate_signals.failed.emit(str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _show_rate(self, league, rate):
        self._rate_request_running = False
        self.divine_rate_value.setText(f"1 = {rate:,.1f} Chaos")
        self.rate_status.setText(f"{league} ・ poe.ninja ・ 31分ごとに自動更新")

    def _show_rate_error(self, message):
        self._rate_request_running = False
        self.divine_rate_value.setText("取得できませんでした")
        self.rate_status.setText(f"レート取得失敗：{message}")

    def handle_hotkey(self, command):
        if command == "poetore_capture":
            self.capture_poetore_item()
        elif command == "cheat_sheets_toggle":
            self.toggle_cheat_sheets()
        elif command == "cheat_sheets_escape":
            if self._cheat_sheet_overlay is not None and self._cheat_sheet_overlay.isVisible():
                self._cheat_sheet_overlay.hide_and_save()
        elif command == "exit":
            self.execute_chat_command("/exit")

    def capture_poetore_item(self):
        from src.poetore.ui import show_poetore_window

        show_poetore_window(self, activate=False).capture_from_poe()

    def open_memo(self):
        if self._memo_dialog is not None:
            if self._memo_dialog.isVisible():
                self._memo_dialog._save_and_close()
            else:
                self._memo_dialog.show()
                self._memo_dialog.raise_()
            return
        from src.ui.memo_dialog import MemoDialog

        poe_version = self.config.get("poe_version", POE1)
        filename = "notes_poe2.json" if poe_version == POE2 else "notes_poe1.json"
        notes_path = str(ConfigManager.get_user_data_path(filename))
        self._memo_dialog = MemoDialog(self, notes_path=notes_path)
        self._memo_dialog.apply_opacity(
            self.config.get("window_opacity", 100),
            self.config.get("text_opacity", 100),
        )
        self._memo_dialog.show()

    def open_settings(self):
        from src.ui.poetore_settings_dialog import PoetoreSettingsDialog

        dialog = PoetoreSettingsDialog(self, self.config)
        if not dialog.exec():
            return
        self.config.update(dialog.get_settings())
        ConfigManager.save_config(self.config)
        self.hotkey_service.stop()
        self.stash_tab_scroll.stop()
        self.stash_tab_scroll = StashTabScrollController(
            enabled=self.config.get("stash_tab_scroll_enabled", True)
        )
        self.stash_tab_scroll.start()
        self._start_hotkeys()
        self.refresh_currency_rate()

    def _ensure_cheat_sheet_overlay(self):
        from src.ui.cheat_sheets import CheatSheetOverlay

        if self._cheat_sheet_overlay is None:
            overlay = CheatSheetOverlay(self.config.get("cheat_sheets", {}), self)
            overlay.config_changed.connect(self._save_cheat_sheet_config)
            overlay.manage_requested.connect(self.open_cheat_sheet_manager)
            self._cheat_sheet_overlay = overlay
        return self._cheat_sheet_overlay

    def _save_cheat_sheet_config(self, cheat_sheet_config):
        self.config["cheat_sheets"] = dict(cheat_sheet_config)
        ConfigManager.save_config(self.config)

    def toggle_cheat_sheets(self):
        self._ensure_cheat_sheet_overlay().toggle()

    def open_cheat_sheet_manager(self):
        from src.ui.cheat_sheets import CheatSheetManagerDialog

        overlay = self._ensure_cheat_sheet_overlay()
        was_visible = overlay.isVisible()
        if was_visible:
            overlay.hide_and_save()
        dialog = CheatSheetManagerDialog(self.config.get("cheat_sheets", {}), self)
        if dialog.exec():
            self._save_cheat_sheet_config(dialog.result_config())
            overlay.reload(self.config["cheat_sheets"])
            if self.config["cheat_sheets"].get("images"):
                overlay.show()
                overlay.raise_()

    def execute_chat_command(self, command):
        """共通F5操作。PoEチャットへ貼り付けて送信する。"""
        send_chat_command(command)

    def closeEvent(self, event):
        self._rate_timer.stop()
        self.hotkey_service.stop()
        self.stash_tab_scroll.stop()
        if self._memo_dialog is not None:
            self._memo_dialog.close()
        if self._cheat_sheet_overlay is not None:
            self._cheat_sheet_overlay.hide_and_save()
            self._cheat_sheet_overlay.close()
        super().closeEvent(event)
