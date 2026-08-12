"""ぽえとれモードの軽量メイン画面。"""

from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject, QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from src.ui.app_theme import POETORE_THEME
from src.utils.chat_command import send_chat_command
from src.ui.custom_command_settings import custom_command_hotkeys, normalized_custom_commands
from src.utils.config_manager import ConfigManager
from src.utils.global_hotkeys import (
    ForegroundSuppressedHotkeyService,
    GlobalHotkeyService,
    is_hotkey_action_allowed,
    suppressed_hotkeys_supported,
)
from src.utils.poe_version_data import POE1, POE2
from src.utils.feature_support import POETORE, is_feature_hotkey_supported, is_feature_supported


POETORE_ACCENT = POETORE_THEME.accent
POETORE_TEXT = POETORE_THEME.text
RATE_REFRESH_MSEC = 31 * 60 * 1000


def _icon_canvas():
    scale = 2
    pixmap = QPixmap(24 * scale, 24 * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    return pixmap, painter


def _finish_icon(pixmap, painter) -> QIcon:
    painter.end()
    return QIcon(pixmap)


def _memo_icon() -> QIcon:
    """Return a compact note page with a folded corner."""
    pixmap, painter = _icon_canvas()
    accent = QColor(POETORE_ACCENT)
    dark = QColor("#15201D")
    page = QPainterPath(QPointF(5.0, 2.8))
    page.lineTo(15.8, 2.8)
    page.lineTo(20.0, 7.0)
    page.lineTo(20.0, 21.0)
    page.lineTo(5.0, 21.0)
    page.closeSubpath()
    painter.setPen(QPen(accent, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QColor(32, 72, 62))
    painter.drawPath(page)
    painter.drawLine(QPointF(15.8, 3.1), QPointF(15.8, 7.0))
    painter.drawLine(QPointF(15.8, 7.0), QPointF(19.7, 7.0))
    painter.setPen(QPen(dark, 1.5, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(8.0, 10.0), QPointF(16.8, 10.0))
    painter.drawLine(QPointF(8.0, 14.0), QPointF(16.8, 14.0))
    painter.drawLine(QPointF(8.0, 18.0), QPointF(14.0, 18.0))
    return _finish_icon(pixmap, painter)


def _image_manager_icon() -> QIcon:
    """Return stacked picture cards to convey image management."""
    pixmap, painter = _icon_canvas()
    accent = QColor(POETORE_ACCENT)
    painter.setPen(QPen(QColor(61, 143, 123), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QColor(24, 49, 43))
    painter.drawRoundedRect(2.8, 3.2, 15.5, 14.5, 2.0, 2.0)
    painter.setPen(QPen(accent, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QColor(32, 72, 62))
    painter.drawRoundedRect(5.5, 6.0, 15.5, 14.5, 2.0, 2.0)
    painter.setBrush(accent)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QPointF(16.4, 10.4), 1.7, 1.7)
    mountain = QPainterPath(QPointF(7.4, 18.4))
    mountain.lineTo(11.5, 13.2)
    mountain.lineTo(14.2, 16.1)
    mountain.lineTo(16.1, 14.3)
    mountain.lineTo(19.2, 18.4)
    mountain.closeSubpath()
    painter.setBrush(QColor(52, 166, 137))
    painter.drawPath(mountain)
    return _finish_icon(pixmap, painter)


def _draw_gear(
    painter,
    center: QPointF,
    radius=3.5,
    tooth_length=1.6,
    stroke_color=None,
    fill_color=None,
):
    dark = QColor("#15201D")
    stroke = QColor(stroke_color) if stroke_color else dark
    fill = QColor(fill_color) if fill_color else QColor(POETORE_ACCENT)
    cx, cy = center.x(), center.y()
    painter.setPen(QPen(stroke, 2.6, Qt.SolidLine, Qt.RoundCap))
    diagonal = tooth_length * 0.72
    for start, end in (
        ((cx, cy - radius - tooth_length), (cx, cy - radius)),
        ((cx, cy + radius), (cx, cy + radius + tooth_length)),
        ((cx - radius - tooth_length, cy), (cx - radius, cy)),
        ((cx + radius, cy), (cx + radius + tooth_length, cy)),
        ((cx - radius - diagonal, cy - radius - diagonal), (cx - radius * 0.72, cy - radius * 0.72)),
        ((cx + radius * 0.72, cy + radius * 0.72), (cx + radius + diagonal, cy + radius + diagonal)),
        ((cx - radius - diagonal, cy + radius + diagonal), (cx - radius * 0.72, cy + radius * 0.72)),
        ((cx + radius * 0.72, cy - radius * 0.72), (cx + radius + diagonal, cy - radius - diagonal)),
    ):
        painter.drawLine(QPointF(*start), QPointF(*end))
    painter.setPen(QPen(stroke, 1.2))
    painter.setBrush(fill)
    painter.drawEllipse(center, radius, radius)
    painter.setBrush(dark)
    painter.drawEllipse(center, radius * 0.36, radius * 0.36)


def _settings_icon() -> QIcon:
    """Return a standalone gear matching the map-management overlay."""
    pixmap, painter = _icon_canvas()
    _draw_gear(
        painter,
        QPointF(12.0, 12.0),
        radius=5.5,
        tooth_length=2.4,
        stroke_color=POETORE_ACCENT,
        fill_color="#20483E",
    )
    return _finish_icon(pixmap, painter)


def _map_mod_manager_icon() -> QIcon:
    """Return a compact folded-map icon with a settings gear overlay."""
    pixmap, painter = _icon_canvas()

    map_path = QPainterPath(QPointF(2.5, 4.5))
    map_path.lineTo(8.5, 2.5)
    map_path.lineTo(14.5, 4.5)
    map_path.lineTo(20.5, 2.5)
    map_path.lineTo(20.5, 16.5)
    map_path.lineTo(14.5, 18.5)
    map_path.lineTo(8.5, 16.5)
    map_path.lineTo(2.5, 18.5)
    map_path.closeSubpath()
    painter.setPen(QPen(QColor(POETORE_ACCENT), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QColor(32, 72, 62))
    painter.drawPath(map_path)
    painter.drawLine(QPointF(8.5, 2.8), QPointF(8.5, 16.2))
    painter.drawLine(QPointF(14.5, 4.8), QPointF(14.5, 18.0))

    _draw_gear(painter, QPointF(17.5, 17.0))
    return _finish_icon(pixmap, painter)


class _RateSignals(QObject):
    ready = Signal(str, float)
    failed = Signal(str)


class _PoetoreModeTitleBar(QWidget):
    """ぽえなび本体と同じ構成のドラッグ可能なタイトルバー。"""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._drag_offset = None
        self.setObjectName("poetoreModeTitleBar")
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 10, 10, 0)
        layout.setSpacing(0)
        layout.addStretch()

        button_style = f"""
            QPushButton {{
                background: transparent;
                color: {POETORE_TEXT};
                border: none;
                font-size: 14px;
                font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background: rgba(101, 255, 202, 0.20);
                border-radius: 3px;
            }}
        """
        close_style = f"""
            QPushButton {{
                background: transparent;
                color: {POETORE_TEXT};
                border: none;
                font-size: 14px;
                font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background: rgba(255, 60, 60, 0.8);
                border-radius: 3px;
                color: #ffffff;
            }}
        """

        self.minimize_button = QPushButton("─")
        self.minimize_button.setObjectName("poetoreMinimizeButton")
        self.minimize_button.setFocusPolicy(Qt.NoFocus)
        self.minimize_button.setFixedSize(30, 22)
        self.minimize_button.setStyleSheet(button_style)
        self.minimize_button.setToolTip("最小化")
        self.minimize_button.clicked.connect(window.minimize_to_tray)
        layout.addWidget(self.minimize_button)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("poetoreCloseButton")
        self.close_button.setFocusPolicy(Qt.NoFocus)
        self.close_button.setFixedSize(30, 22)
        self.close_button.setStyleSheet(close_style)
        self.close_button.setToolTip("閉じる")
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and not self._window.config.get("window_locked", False)
        ):
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class PoetoreModeWindow(QMainWindow):
    MODE_ACTION_DEFAULTS = {
        "exit": "F5",
        "monastery": "F12",
        "poetore_capture": "alt+d",
        "poetore_auto_hide": "ctrl+d",
        "map_check": "alt+f",
        "cheat_sheets_toggle": "shift+space",
    }

    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load_config()
        self._cheat_sheet_overlay = None
        self._map_check_window = None
        self._memo_dialog = None
        self._rate_request_running = False
        self._rate_signals = _RateSignals(self)
        self._rate_signals.ready.connect(self._show_rate)
        self._rate_signals.failed.connect(self._show_rate_error)

        self.setWindowTitle("ぽえとれ")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(500, 300)
        self.resize(558, 360)
        self._build_ui()
        self._build_tray_icon()
        self._apply_window_settings()
        QTimer.singleShot(0, self._apply_startup_position)

        self._start_hotkeys()

        self._rate_timer = QTimer(self)
        self._rate_timer.setInterval(RATE_REFRESH_MSEC)
        self._rate_timer.timeout.connect(self.refresh_currency_rate)
        self._rate_timer.start()
        QTimer.singleShot(0, self.refresh_currency_rate)
        self._prepare_poetore_window()
        self._apply_obs_streaming_mode()

    @staticmethod
    def _asset_path(filename):
        return Path(__file__).resolve().parents[2] / "assets" / "icons" / filename

    @staticmethod
    def _app_asset_path(filename):
        return Path(__file__).resolve().parents[2] / "assets" / "app" / filename

    def _build_tray_icon(self):
        icon = QIcon(str(self._app_asset_path("icon2.ico")))
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.setWindowIcon(icon)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("ぽえとれ")
        self.tray_icon.activated.connect(self._handle_tray_activation)

        menu = QMenu(self)
        self.tray_show_action = QAction("ぽえとれを表示", menu)
        self.tray_show_action.triggered.connect(self.restore_from_tray)
        menu.addAction(self.tray_show_action)
        self.tray_settings_action = QAction("設定", menu)
        self.tray_settings_action.triggered.connect(self.open_settings_from_tray)
        menu.addAction(self.tray_settings_action)
        menu.addSeparator()
        self.tray_exit_action = QAction("終了", menu)
        self.tray_exit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(self.tray_exit_action)
        self.tray_icon.setContextMenu(menu)
        self._tray_notification_shown = False

    def minimize_to_tray(self):
        """トレイ非対応環境では、従来どおりタスクバーへ最小化する。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.showMinimized()
            return
        self.tray_icon.show()
        self.hide()
        if not self._tray_notification_shown:
            self.tray_icon.showMessage(
                "ぽえとれ",
                "タスクトレイに格納しました。",
                QSystemTrayIcon.Information,
                3000,
            )
            self._tray_notification_shown = True

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.tray_icon.hide()

    def open_settings_from_tray(self):
        self.restore_from_tray()
        QTimer.singleShot(0, self.open_settings)

    def quit_from_tray(self):
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _handle_tray_activation(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_from_tray()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("poetoreModeRoot")
        central.setStyleSheet(f"""
            QWidget#poetoreModeRoot {{
                background: {POETORE_THEME.background};
                color: {POETORE_TEXT};
                border: 1px solid #343B3E;
                border-radius: 10px;
            }}
            QWidget#poetoreModeTitleBar {{ border: none; background: transparent; }}
            QFrame#rateCard {{
                background: {POETORE_THEME.panel};
                border: 1px solid #343B3E;
                border-radius: 10px;
            }}
            QPushButton {{
                background: #1A1F21;
                color: {POETORE_TEXT};
                border: 1px solid #3A4245;
                border-radius: 7px;
                padding: 7px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #25332F; border-color: {POETORE_ACCENT}; }}
            QPushButton:pressed {{ background: #276B5A; }}
        """)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = _PoetoreModeTitleBar(self)
        root.addWidget(self.title_bar)

        body = QWidget()
        body.setObjectName("poetoreModeBody")
        body.setStyleSheet("QWidget#poetoreModeBody { border: none; background: transparent; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 8, 24, 18)
        body_layout.setSpacing(16)

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

        self.memo_button = self._header_button("", "共通メモを開く")
        self.memo_button.setIcon(_memo_icon())
        self.memo_button.setIconSize(QSize(24, 24))
        self.cheat_sheets_button = self._header_button(
            "", "Cheat sheetsの画像を登録・管理"
        )
        self.cheat_sheets_button.setIcon(_image_manager_icon())
        self.cheat_sheets_button.setIconSize(QSize(24, 24))
        self.map_mods_button = self._header_button("", "Map Modを登録・管理")
        self.map_mods_button.setIcon(_map_mod_manager_icon())
        self.map_mods_button.setIconSize(QSize(24, 24))
        self.settings_button = self._header_button("", "設定画面を開く")
        self.settings_button.setIcon(_settings_icon())
        self.settings_button.setIconSize(QSize(24, 24))
        self.memo_button.clicked.connect(self.open_memo)
        self.map_mods_button.clicked.connect(self.open_map_mod_manager)
        self.cheat_sheets_button.clicked.connect(self.open_cheat_sheet_manager)
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.memo_button)
        header.addWidget(self.map_mods_button)
        header.addWidget(self.cheat_sheets_button)
        header.addWidget(self.settings_button)
        body_layout.addLayout(header)

        section_title = QLabel("Divine / Chaos 換算")
        section_title.setStyleSheet(
            f"color: {POETORE_ACCENT}; font-size: 15px; font-weight: bold;"
        )
        body_layout.addWidget(section_title)

        self.divine_rate_value = QLabel("取得中…")
        body_layout.addWidget(self._rate_card(self.divine_rate_value))

        footer = QHBoxLayout()
        self.rate_status = QLabel("poe.ninjaから現在のレートを取得しています")
        self.rate_status.setStyleSheet("color: #98A39F; font-size: 11px;")
        self.rate_status.setWordWrap(True)
        footer.addWidget(self.rate_status, 1)
        self.rate_refresh_button = QPushButton("更新")
        self.rate_refresh_button.setFocusPolicy(Qt.NoFocus)
        self.rate_refresh_button.setToolTip("現在の換算レートを再取得")
        self.rate_refresh_button.clicked.connect(self.refresh_currency_rate)
        footer.addWidget(self.rate_refresh_button)
        body_layout.addLayout(footer)
        body_layout.addStretch()

        self.capture_hint = QLabel()
        self.capture_hint.setObjectName("poetoreCaptureHint")
        self.capture_hint.setAlignment(Qt.AlignCenter)
        self.capture_hint.setWordWrap(True)
        self.capture_hint.setStyleSheet(
            f"color: {POETORE_THEME.muted_text}; font-size: 12px;"
        )
        body_layout.addWidget(self.capture_hint)
        root.addWidget(body, 1)
        self.setCentralWidget(central)
        self._update_capture_hint()

    def _apply_window_settings(self):
        self.setWindowOpacity(
            max(0.05, min(1.0, int(self.config.get("window_opacity", 100)) / 100))
        )
        flags = Qt.Window | Qt.FramelessWindowHint
        if self.config.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
        if self._memo_dialog is not None:
            self._memo_dialog.apply_opacity(
                self.config.get("window_opacity", 100),
                self.config.get("text_opacity", 100),
            )

    def _apply_startup_position(self):
        if not self.config.get("snap_to_right_edge", False):
            return
        screens = QApplication.screens()
        if not screens:
            return
        index = int(self.config.get("display_monitor", 0))
        screen = screens[index] if 0 <= index < len(screens) else screens[0]
        available = screen.availableGeometry()
        self.move(available.right() - self.width() + 1, available.top())

    def _header_button(self, text, tooltip):
        button = QPushButton(text)
        button.setFocusPolicy(Qt.NoFocus)
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
        poe_version = self.config.get("poe_version", POE1)
        mode_hotkeys = {
            action: configured.get(action, default)
            for action, default in self.MODE_ACTION_DEFAULTS.items()
            if is_feature_hotkey_supported(action, poe_version)
        }
        mode_hotkeys.update(custom_command_hotkeys(self.config.get("custom_commands", [])))
        capture_hotkey = mode_hotkeys.get("poetore_capture", "none")
        use_suppression = suppressed_hotkeys_supported()
        if use_suppression:
            mode_hotkeys.pop("poetore_capture", None)
        self.hotkey_service = GlobalHotkeyService(
            mode_hotkeys, action_filter=is_hotkey_action_allowed, parent=self,
        )
        self.hotkey_service.command.connect(self.handle_hotkey)
        self.hotkey_service.start()
        self.suppressed_capture_hotkey = None
        if use_suppression:
            self.suppressed_capture_hotkey = ForegroundSuppressedHotkeyService(
                "poetore_capture", capture_hotkey, parent=self,
            )
            self.suppressed_capture_hotkey.command.connect(self.handle_hotkey)
            self.suppressed_capture_hotkey.start()

    @staticmethod
    def _display_hotkey(hotkey):
        value = str(hotkey or "").strip()
        if not value or value.lower() == "none":
            return ""
        display = QKeySequence(value).toString(QKeySequence.PortableText) or value
        return " + ".join(part.strip() for part in display.split("+"))

    def _update_capture_hint(self):
        hotkeys = self.config.get("hotkeys", {})
        interactive = self._display_hotkey(
            hotkeys.get("poetore_capture", "alt+d")
        )
        auto_hide = self._display_hotkey(
            hotkeys.get("poetore_auto_hide", "ctrl+d")
        )
        modes = []
        if interactive:
            modes.append(f"{interactive} 操作モード")
        if auto_hide:
            modes.append(f"{auto_hide} AUTO-HIDE")
        if modes:
            self.capture_hint.setText(
                "アイテムにマウスオーバーして " + " / ".join(modes)
            )
        else:
            self.capture_hint.setText("価格チェックのホットキーが設定されていません。")

    @property
    def active_service_names(self):
        names = {"global_hotkeys", "currency_rate_refresh"}
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
        if command.startswith("custom_command:"):
            index = int(command.split(":", 1)[1])
            commands = normalized_custom_commands(self.config.get("custom_commands", []))
            if 0 <= index < len(commands) and commands[index]["enabled"]:
                self.execute_chat_command(commands[index]["command"])
            return
        if command == "poetore_capture":
            self.capture_poetore_item()
        elif command == "poetore_capture_released":
            window = getattr(self, "_poetore_window", None)
            if window is not None:
                window.capture_hotkey_released()
        elif command == "poetore_auto_hide":
            self.capture_poetore_item(auto_hide=True)
        elif command == "poetore_auto_hide_released":
            window = getattr(self, "_poetore_window", None)
            if window is not None:
                window.capture_hotkey_released()
        elif command == "map_check":
            self.capture_map_check_item()
        elif command == "map_check_released":
            if self._map_check_window is not None:
                self._map_check_window.capture_hotkey_released()
        elif command == "cheat_sheets_toggle":
            self.toggle_cheat_sheets()
        elif command == "cheat_sheets_escape":
            if self._cheat_sheet_overlay is not None and self._cheat_sheet_overlay.isVisible():
                self._cheat_sheet_overlay.hide_and_save()
        elif command == "exit":
            self.execute_chat_command("/exit")
        elif command == "monastery":
            self.execute_chat_command("/monastery")

    def capture_poetore_item(self, auto_hide=False):
        if not is_feature_supported(
            POETORE, self.config.get("poe_version", POE1),
        ):
            return None
        started_at = time.perf_counter()
        from src.poetore.performance import start_search_trace

        trace = start_search_trace(
            "auto_hide_poetore_mode" if auto_hide else "interactive_poetore_mode",
            started_at=started_at,
        )
        trace.mark("hotkey_dispatched")
        from src.poetore.ui import show_poetore_window

        window = show_poetore_window(self, activate=False)
        trace.mark("poetore_window_ready")
        if auto_hide:
            hotkey = self.config.get("hotkeys", {}).get(
                "poetore_auto_hide", "ctrl+d"
            )
            window.capture_from_poe(
                trace, auto_hide=True, capture_hotkey=hotkey,
            )
        else:
            window.capture_from_poe(trace)

    def _save_map_check_config(self, map_check_config):
        self.config["map_check"] = dict(map_check_config)
        ConfigManager.save_config(self.config)

    def _ensure_map_check_window(self):
        from src.ui.map_check import MapCheckWindow

        if self._map_check_window is None:
            map_config = dict(self.config.get("map_check", {}))
            map_config["_font_size"] = self.config.get("poetore", {}).get("result_font_size", "medium")
            self._map_check_window = MapCheckWindow(map_config, self)
            self._map_check_window.config_changed.connect(
                self._save_map_check_config
            )
        else:
            map_config = dict(self.config.get("map_check", {}))
            map_config["_font_size"] = self.config.get("poetore", {}).get("result_font_size", "medium")
            self._map_check_window.reload_config(map_config)
        return self._map_check_window

    def capture_map_check_item(self):
        self._ensure_map_check_window().capture_from_poe()

    def open_map_mod_manager(self):
        from src.ui.map_check import MapModManagerDialog

        dialog = MapModManagerDialog(self.config.get("map_check", {}), self)
        dialog.config_changed.connect(self._save_map_check_config)
        dialog.exec()
        if self._map_check_window is not None:
            self._map_check_window.reload_config(self.config.get("map_check", {}))

    def _prepare_poetore_window(self):
        """Build the search panel after startup without issuing Trade requests."""
        if not is_feature_supported(
            POETORE, self.config.get("poe_version", POE1),
        ):
            return None
        from src.poetore.ui import prepare_poetore_window

        return prepare_poetore_window(self)

    def _apply_obs_streaming_mode(self):
        window = getattr(self, "_poetore_window", None)
        if window is None:
            return
        obs_config = self.config.get("poetore", {}).get("obs_streaming", {})
        enabled = bool(obs_config.get("enabled", False)) if isinstance(obs_config, dict) else False
        window.set_obs_streaming_mode(enabled)

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
        self._memo_dialog = MemoDialog(self, notes_path=notes_path, theme=POETORE_THEME)
        self._memo_dialog.apply_opacity(
            self.config.get("window_opacity", 100),
            self.config.get("text_opacity", 100),
        )
        self._memo_dialog.show()

    def open_settings(self):
        from src.ui.poetore_settings_dialog import PoetoreSettingsDialog

        dialog = PoetoreSettingsDialog(
            self,
            self.config,
            update_check_callback=lambda: self._check_for_updates(dialog),
        )
        if not dialog.exec():
            return
        self.config.update(dialog.get_settings())
        ConfigManager.save_config(self.config)
        from src.app_restart import confirm_mode_switch_restart

        if confirm_mode_switch_restart(self, self.config):
            return
        self._apply_window_settings()
        self._apply_startup_position()
        if getattr(self, "_poetore_window", None) is not None:
            self._poetore_window.apply_result_display_size()
            self._apply_obs_streaming_mode()
        self.hotkey_service.stop()
        if self.suppressed_capture_hotkey is not None:
            self.suppressed_capture_hotkey.stop()
        self._start_hotkeys()
        self._update_capture_hint()
        self.refresh_currency_rate()

    def _check_for_updates(self, parent=None):
        """アプリ情報タブから、通知済みバージョンも含めて手動確認する。"""
        from src.update.startup_gate import run_manual_update_check

        self.config = ConfigManager.load_config()
        if not run_manual_update_check(self.config, parent or self):
            QApplication.instance().quit()

    def _ensure_cheat_sheet_overlay(self):
        from src.ui.cheat_sheets import CheatSheetOverlay

        if self._cheat_sheet_overlay is None:
            overlay = CheatSheetOverlay(
                self.config.get("cheat_sheets", {}), self, theme=POETORE_THEME
            )
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
        dialog = CheatSheetManagerDialog(
            self.config.get("cheat_sheets", {}), self, theme=POETORE_THEME
        )
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
        self.tray_icon.hide()
        self._rate_timer.stop()
        self.hotkey_service.stop()
        if self.suppressed_capture_hotkey is not None:
            self.suppressed_capture_hotkey.stop()
        if self._memo_dialog is not None:
            self._memo_dialog.close()
        if self._cheat_sheet_overlay is not None:
            self._cheat_sheet_overlay.hide_and_save()
            self._cheat_sheet_overlay.close()
        if self._map_check_window is not None:
            self._map_check_window.close()
            self._map_check_window.deleteLater()
            self._map_check_window = None
        if getattr(self, "_poetore_window", None) is not None:
            self._poetore_window.close()
            self._poetore_window.deleteLater()
            self._poetore_window = None
        super().closeEvent(event)
