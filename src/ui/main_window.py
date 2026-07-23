import html
import json
import os
import re
import sys
import time
from pynput import keyboard as pynput_keyboard
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QMenu, QFrame, QScrollArea, QSplitter,
                               QSizeGrip, QMessageBox, QRadioButton, QButtonGroup, QApplication)
from PySide6.QtCore import Qt, QTimer, Signal, QRect, QEvent, QEventLoop, QPoint, QSize, QMimeData, QUrl
from PySide6.QtGui import QCursor, QMouseEvent, QIcon, QDesktopServices
from src.ui.styles import Styles
from src.ui.settings_dialog import AreaNoteDialog, SettingsDialog
from src.ui.map_viewer import MapThumbnailWidget
from src.utils.config_manager import ConfigManager
from src.utils.lap_recorder import LapRecorder
from src.utils.segment_recorder import SegmentRecorder
from src.utils.log_watcher import LogWatcher
from src.utils.log_path_detector import fill_missing_client_log_paths
from src.utils.performance_metrics import measure
from src.utils.window_focus import get_foreground_window, focus_window, get_next_visible_window_after
from src.utils.zone_lookup import get_zone_info, get_level_advice
from src.utils.guide_data import load_guide_data, get_zone_guide, get_zone_guide_level, format_guide_html, get_mini_navi_content
from src.utils.poe_version_data import POE1, POE2, get_lap_labels, get_poe_label, get_timer_filename, get_progress_flags_filename
from src.utils.zone_master_data import load_zone_master_data
from src.utils.poe_progress_data import get_auto_lap_triggers, get_clear_message, get_special_lap_event
from src.utils.pob_importer import import_pob, get_pob_skill_sets
from src.utils.gem_resolver import resolve_gem_acquisition
from src.utils.poelab_links import POELAB_HOME, find_daily_notes_url
from src.utils.area_notes import get_area_note, set_area_note
from src.ui.gem_tracker_widget import GemTrackerWidget, PoBImportDialog, PoBSkillSetSelectionDialog
from src.ui.update_dialogs import UpdateAvailableDialog, UpdateProgressDialog
from src.update.qt_controller import UpdateController
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout


DEFAULT_CLICK_THROUGH_HOTKEY = "F6"


class MiniNaviLockButtonWindow(QWidget):
    """クリック透過中でも押せる、みになび専用の別ウィンドウ鍵ボタン。"""

    def __init__(self, overlay):
        super().__init__(None)
        self.overlay = overlay
        self.setWindowFlags(_with_optional_mini_always_on_top(Qt.Tool | Qt.FramelessWindowHint, overlay.main_window))
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.restore_button = QPushButton("本体")
        self.restore_button.setFixedSize(44, 28)
        self.restore_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.restore_button.setToolTip("ぽえなび本体の表示／非表示を切り替えます")
        self.restore_button.setStyleSheet("""
            QPushButton {
                background: rgba(10, 10, 10, 220);
                color: #ffffff;
                border: 1px solid rgba(176, 255, 123, 140);
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(73, 110, 50, 230);
                border-color: rgba(176, 255, 123, 220);
            }
        """)
        self.restore_button.clicked.connect(self.overlay.toggle_main_window)
        layout.addWidget(self.restore_button)

        self.button = QPushButton("🔒")
        self.button.setFixedSize(30, 28)
        self.button.setCursor(QCursor(Qt.PointingHandCursor))
        self.button.setStyleSheet("""
            QPushButton {
                background: rgba(10, 10, 10, 220);
                color: #ffffff;
                border: 1px solid rgba(176, 255, 123, 140);
                border-radius: 6px;
                font-size: 15px;
            }
            QPushButton:hover {
                background: rgba(73, 110, 50, 230);
                border-color: rgba(176, 255, 123, 220);
            }
        """)
        self.button.clicked.connect(self.overlay.toggle_locked)
        layout.addWidget(self.button)

    def sync_from_overlay(self):
        cfg = self.overlay.config()
        main_hidden = self.overlay.is_main_window_hidden()
        show_lock_button = bool(cfg.get("show_lock_button", True))
        if not self.overlay.isVisible() or not cfg.get("enabled", False):
            self.hide()
            return
        self.restore_button.setVisible(True)
        self.button.setVisible(show_lock_button)
        width = 44 + (30 if show_lock_button else 0)
        if show_lock_button:
            width += 4
        self.setFixedWidth(width)
        self.button.setText("🔒" if cfg.get("locked", True) else "🔓")
        self.move(self.overlay.x() + self.overlay.width() - self.width() - 4, self.overlay.y() + 4)
        self.show()
        self.raise_()

    def enterEvent(self, event):
        self.overlay._show_strong_opacity()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.overlay._maybe_start_fade_timer()
        super().leaveEvent(event)


class MiniNaviOverlay(QWidget):
    """みになび表示ウィンドウ。"""

    WAITING_FOR_AREA_TEXT = "エリアに入場すると攻略ガイドが表示されます"
    COMPACT_DEFAULT_WIDTH = 390
    COMPACT_DEFAULT_HEIGHT = 100

    DIRECTION_ARROWS = {
        "n": "⬆", "s": "⬇", "e": "➡", "w": "⬅",
        "ne": "⬈", "nw": "⬉", "se": "⬊", "sw": "⬋",
    }
    ICONS = {
        "quest": "❗",
        "boss": "⚔️",
        "town": "🏠",
        "move": "🚪",
        "logout": "⏻",
        "note": "ℹ️",
        "star": "⭐",
        "trial": "🏛️",
        "craft": "🔨",
    }
    IMAGE_ICONS = {
        "wp": "wp.png",
        "portal": "portal.png",
    }

    DEFAULT_CONFIG = {
        "enabled": False,
        "display_mode": "standard",
        "locked": True,
        "click_through_when_locked": True,
        "opacity": 0.72,
        "faded_opacity": 0.38,
        "fade_enabled": True,
        "fade_delay_ms": 5000,
        "window_opacity": 100,
        "text_opacity": 100,
        "font_size": 18,
        "max_lines": 3,
        "position": {"x": 80, "y": 160},
        "width": 800,
        "height": 130,
        "show_lock_button": True,
        "always_on_top": True,
    }

    def __init__(self, parent=None):
        # Windowsでは親を持つツールウィンドウは、親の最小化・非表示に追従して
        # 一緒に隠れる。設定や終了処理の所有者は参照として保持しつつ、Qt上は
        # 独立したトップレベルウィンドウにする。
        super().__init__(None)
        self.main_window = parent
        self.setWindowFlags(_with_optional_mini_always_on_top(Qt.Tool | Qt.FramelessWindowHint, self.main_window))
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._drag_pos = None
        self._resize_edges = ""
        self._resize_start_pos = None
        self._resize_start_geom = None
        self._resize_margin = 8
        self._current_content = None
        self._current_exp_guide = None
        self._current_zone_id = None
        self._current_has_area_note = False
        self._muted_content = False
        self._lock_button_hidden_for_drag = False
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_to_idle_opacity)
        self.setMouseTracking(True)
        self.setMinimumSize(220, 70)

        self.outer = QFrame(self)
        self.outer.setObjectName("miniNaviOuter")
        layout = QHBoxLayout(self.outer)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setSpacing(8)

        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(2)

        self.arrow_label = QLabel("")
        self.arrow_label.setAlignment(Qt.AlignCenter)
        self.arrow_label.setFixedSize(118, 30)
        self.arrow_label.installEventFilter(self)
        left_column.addStretch(1)
        left_column.addWidget(self.arrow_label, stretch=0)

        self.exp_label = QLabel("")
        self.exp_label.setTextFormat(Qt.RichText)
        self.exp_label.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        self.exp_label.setFixedWidth(118)
        self.exp_label.setWordWrap(False)
        self.exp_label.installEventFilter(self)
        left_column.addWidget(self.exp_label, stretch=0)
        left_column.addStretch(1)
        layout.addLayout(left_column)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(5)

        self.area_note_badge = QLabel("エリアメモあり")
        self.area_note_badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.area_note_badge.setStyleSheet(
            "color: #f0c674; font-size: 12px; font-weight: bold; "
            "padding-right: 54px; background: transparent;"
        )
        self.area_note_badge.installEventFilter(self)
        self.area_note_badge.hide()
        right_column.addWidget(self.area_note_badge, stretch=0, alignment=Qt.AlignRight)

        self.text_label = QLabel("")
        self.text_label.setTextFormat(Qt.RichText)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.text_label.setMinimumWidth(150)
        self.text_label.installEventFilter(self)
        right_column.addWidget(self.text_label, stretch=1)

        layout.addLayout(right_column, stretch=1)

        self.size_grip = QSizeGrip(self.outer)
        self.size_grip.setStyleSheet("background: transparent;")
        layout.addWidget(self.size_grip, 0, Qt.AlignRight | Qt.AlignBottom)
        self.outer.installEventFilter(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.outer)
        self.lock_button_window = MiniNaviLockButtonWindow(self)
        self.apply_settings(refresh_window_flags=False)
        self.hide()

    def config(self) -> dict:
        parent_config = getattr(self.main_window, "config", {}) if self.main_window else {}
        overlay_config = parent_config.setdefault("mini_guide_overlay", {}) if isinstance(parent_config, dict) else {}
        merged = dict(self.DEFAULT_CONFIG)
        if isinstance(overlay_config, dict):
            merged.update(overlay_config)
        return merged

    def apply_settings(self, refresh_window_flags: bool = False):
        cfg = self.config()
        if refresh_window_flags:
            self._apply_window_flags()
        geometry = self._geometry_config()
        if self.is_compact_mode() and not geometry:
            default_geometry = self._compact_default_geometry()
            self.resize(default_geometry.width(), default_geometry.height())
            self.move(default_geometry.topLeft())
        else:
            self.resize(
                int(geometry.get("width", cfg.get("width", 800))),
                int(geometry.get("height", cfg.get("height", 130))),
            )
            pos = geometry.get("position", {}) if isinstance(geometry.get("position"), dict) else {}
            self.move(int(pos.get("x", cfg.get("position", {}).get("x", 80))), int(pos.get("y", cfg.get("position", {}).get("y", 160))))
        self._show_strong_opacity(restart_fade=False)
        font_size = int(cfg.get("font_size", 18))
        window_opacity_pct = max(5, min(int(cfg.get("window_opacity", 100)), 100))
        bg_alpha = int(window_opacity_pct / 100.0 * 255)
        border_alpha = int(window_opacity_pct / 100.0 * 140)
        self.outer.setStyleSheet(f"""
            #miniNaviOuter {{
                background-color: rgba(10, 10, 10, {bg_alpha});
                border: 1px solid rgba(176, 255, 123, {border_alpha});
                border-radius: 8px;
            }}
        """)
        if self.is_compact_mode():
            self.outer.layout().setContentsMargins(6, 5, 6, 5)
            self.outer.layout().setSpacing(4)
            self.arrow_label.setFixedSize(40, 24)
            self.exp_label.setFixedWidth(40)
            self.arrow_label.setStyleSheet("color: #FF69B4; font-size: 24px; font-weight: bold; line-height: 100%; background: transparent;")
            self.exp_label.setStyleSheet("color: #ffffff; font-size: 10px; line-height: 110%; background: transparent;")
        else:
            self.outer.layout().setContentsMargins(10, 8, 12, 8)
            self.outer.layout().setSpacing(8)
            self.arrow_label.setFixedSize(118, 30)
            self.exp_label.setFixedWidth(118)
            self.arrow_label.setStyleSheet("color: #FF69B4; font-size: 36px; font-weight: bold; line-height: 100%; background: transparent;")
            self.exp_label.setStyleSheet("color: #ffffff; font-size: 15px; line-height: 110%; background: transparent;")
        text_color = "#999999" if self._muted_content else "#ffffff"
        self.text_label.setStyleSheet(f"color: {text_color}; font-size: {font_size}px; line-height: 120%; background: transparent;")
        self._apply_text_opacity(int(cfg.get("text_opacity", 100)))
        self.size_grip.setVisible(not bool(cfg.get("locked", True)))
        self._apply_click_through()
        self._sync_lock_button()

    def _apply_text_opacity(self, opacity_pct: int):
        """みになび本文・矢印・経験値表示の文字透過率を適用。"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        opacity = max(0.0, min(int(opacity_pct) / 100.0, 1.0))
        for widget in (self.arrow_label, self.exp_label, self.text_label, self.area_note_badge):
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(opacity)
            widget.setGraphicsEffect(effect)

    def update_content(
        self,
        mini_navi: dict | None,
        exp_guide: dict | None = None,
        muted: bool = False,
        zone_id: str | None = None,
        has_area_note: bool = False,
    ):
        self._current_content = mini_navi
        self._current_exp_guide = exp_guide
        self._muted_content = muted
        self._current_zone_id = zone_id
        self._current_has_area_note = bool(has_area_note)
        cfg = self.config()
        if not cfg.get("enabled", False):
            self.hide()
            self.lock_button_window.hide()
            return
        if not isinstance(mini_navi, dict):
            self.hide()
            self.lock_button_window.hide()
            return
        text = mini_navi.get("text", "") or ""
        direction = mini_navi.get("direction", "none") or "none"
        # 既存configに max_lines=3 が保存されていても、みになび本文が欠けないよう最低4行は表示する。
        lines = [line for line in text.splitlines() if line.strip()]
        if not self.is_compact_mode():
            max_lines = max(4, min(int(cfg.get("max_lines", 4)), 6))
            lines = lines[:max_lines]
        if not lines and direction not in self.DIRECTION_ARROWS:
            self.hide()
            self.lock_button_window.hide()
            return

        arrow = self.DIRECTION_ARROWS.get(direction, "")
        self.arrow_label.setText(arrow)
        self.arrow_label.setVisible(bool(arrow))
        self.exp_label.setText(self._render_exp_guide(exp_guide))
        self.exp_label.setVisible(bool(exp_guide) and not self.is_compact_mode())
        self.text_label.setAlignment(Qt.AlignCenter if muted else Qt.AlignVCenter | Qt.AlignLeft)
        self.text_label.setText("<br>".join(self._render_line(line) for line in lines))
        self.area_note_badge.setVisible(bool(has_area_note) and not muted)
        self.apply_settings(refresh_window_flags=False)
        self._fit_height_to_content()
        self.show()
        self.raise_()
        self._apply_click_through()
        self._sync_lock_button()
        self._show_strong_opacity(restart_fade=True)

    def show_waiting_for_area(self):
        """街エリアでは、起動済みと分かる待機メッセージを表示する。"""
        self.update_content(
            {"text": self.WAITING_FOR_AREA_TEXT, "direction": "none"},
            muted=True,
        )

    def show_last_content_or_waiting(self):
        """街では前エリアの表示を維持し、履歴がない時だけ待機表示する。"""
        if isinstance(self._current_content, dict):
            self.update_content(
                self._current_content,
                self._current_exp_guide,
                muted=self._muted_content,
                zone_id=getattr(self, "_current_zone_id", None),
                has_area_note=getattr(self, "_current_has_area_note", False),
            )
            return
        self.show_waiting_for_area()

    def toggle_enabled(self):
        cfg = self._mutable_config()
        cfg["enabled"] = not bool(cfg.get("enabled", self.DEFAULT_CONFIG["enabled"]))
        self._save_parent_config()
        self.update_content(
            self._current_content,
            self._current_exp_guide,
            zone_id=getattr(self, "_current_zone_id", None),
            has_area_note=getattr(self, "_current_has_area_note", False),
        )

    def toggle_locked(self):
        # ロック切替で apply_settings() が保存済みサイズへ戻してしまわないよう、
        # いま画面に出ているジオメトリを先に保存する。
        self._remember_current_geometry_to_config()
        cfg = self._mutable_config()
        cfg["locked"] = not bool(cfg.get("locked", self.DEFAULT_CONFIG["locked"]))
        self._save_parent_config()
        self.apply_settings(refresh_window_flags=False)
        self._show_strong_opacity(restart_fade=bool(cfg.get("locked", True)))

    def _mutable_config(self) -> dict:
        parent_config = getattr(self.main_window, "config", {}) if self.main_window else {}
        return parent_config.setdefault("mini_guide_overlay", {})

    def is_compact_mode(self) -> bool:
        return self.config().get("display_mode", "standard") == "compact"

    def _geometry_config(self) -> dict:
        config = self._mutable_config()
        if self.is_compact_mode():
            return config.setdefault("compact_geometry", {})
        return config

    def _available_screen_geometry(self) -> QRect:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
        return QRect(0, 0, self.COMPACT_DEFAULT_WIDTH, self.COMPACT_DEFAULT_HEIGHT)

    def _compact_default_geometry(self) -> QRect:
        available = self._available_screen_geometry()
        width = min(self.COMPACT_DEFAULT_WIDTH, available.width())
        height = min(self.COMPACT_DEFAULT_HEIGHT, available.height())
        x = available.x() + (available.width() - width) // 2
        y = available.bottom() - height + 1
        return QRect(x, y, width, height)

    def _save_parent_config(self):
        if self.main_window and hasattr(self.main_window, "config"):
            ConfigManager.save_config(self.main_window.config)
            if hasattr(self.main_window, "_refresh_mini_navi_toggle"):
                self.main_window._refresh_mini_navi_toggle()

    def is_main_window_hidden(self) -> bool:
        return bool(self.main_window and getattr(self.main_window, "_hidden_for_mini_navi", False))

    def toggle_main_window(self):
        if not self.main_window:
            return
        if self.is_main_window_hidden():
            if hasattr(self.main_window, "restore_from_mini_navi"):
                self.main_window.restore_from_mini_navi()
        elif hasattr(self.main_window, "hide_for_mini_navi"):
            self.main_window.hide_for_mini_navi()

    def _remember_current_geometry_to_config(self):
        cfg = self._geometry_config()
        cfg["position"] = {"x": self.x(), "y": self.y()}
        cfg["width"] = self.width()
        cfg["height"] = self.height()

    def _save_geometry_to_config(self):
        self._remember_current_geometry_to_config()
        self._save_parent_config()

    def eventFilter(self, watched, event):
        drag_widgets = tuple(
            widget for widget in (
                getattr(self, "outer", None),
                getattr(self, "arrow_label", None),
                getattr(self, "exp_label", None),
                getattr(self, "text_label", None),
            ) if widget is not None
        )
        if watched in drag_widgets:
            event_type = event.type()
            if event_type == QEvent.MouseButtonPress:
                pos = watched.mapTo(self, event.position().toPoint())
                if self._handle_overlay_press(event, pos):
                    return True
            if event_type == QEvent.MouseMove:
                pos = watched.mapTo(self, event.position().toPoint())
                if self._handle_overlay_move(event, pos):
                    return True
            if event_type == QEvent.MouseButtonRelease:
                pos = watched.mapTo(self, event.position().toPoint())
                if self._handle_overlay_release(event, pos):
                    return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent):
        if self._handle_overlay_press(event, event.position().toPoint()):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._handle_overlay_move(event, event.position().toPoint()):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._handle_overlay_release(event, event.position().toPoint()):
            return
        super().mouseReleaseEvent(event)

    def _handle_overlay_press(self, event: QMouseEvent, pos: QPoint) -> bool:
        if self.config().get("locked", True):
            return False
        if event.button() != Qt.LeftButton:
            return False
        edges = self._hit_test_edges(pos)
        if edges:
            self._resize_edges = edges
            self._resize_start_pos = event.globalPosition().toPoint()
            self._resize_start_geom = self.geometry()
        else:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        if hasattr(self, "lock_button_window") and self.lock_button_window.isVisible():
            self.lock_button_window.hide()
            self._lock_button_hidden_for_drag = True
        self._show_strong_opacity(restart_fade=False)
        event.accept()
        return True

    def _handle_overlay_move(self, event: QMouseEvent, pos: QPoint) -> bool:
        if self.config().get("locked", True):
            self.unsetCursor()
            return False
        if self._resize_edges and self._resize_start_geom is not None and event.buttons() & Qt.LeftButton:
            self._resize_window(event.globalPosition().toPoint())
            event.accept()
            return True
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return True
        self._update_resize_cursor(pos)
        return False

    def _handle_overlay_release(self, event: QMouseEvent, pos: QPoint) -> bool:
        moved = self._drag_pos is not None or bool(self._resize_edges)
        self._drag_pos = None
        self._resize_edges = ""
        self._resize_start_pos = None
        self._resize_start_geom = None
        self._update_resize_cursor(pos)
        if moved:
            self._save_geometry_to_config()
            if self._lock_button_hidden_for_drag:
                self._lock_button_hidden_for_drag = False
                self._sync_lock_button()
            self._maybe_start_fade_timer()
            event.accept()
            return True
        return False

    def enterEvent(self, event):
        self._show_strong_opacity(restart_fade=False)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._resize_edges:
            self.unsetCursor()
        self._maybe_start_fade_timer()
        super().leaveEvent(event)

    def moveEvent(self, event):
        self._sync_lock_button()
        super().moveEvent(event)

    def resizeEvent(self, event):
        self._update_text_width_for_current_size()
        self._sync_lock_button()
        super().resizeEvent(event)

    def hideEvent(self, event):
        self.lock_button_window.hide()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._save_geometry_to_config()
        self.lock_button_window.close()
        super().closeEvent(event)

    def _apply_window_flags(self):
        was_visible = self.isVisible()
        lock_was_visible = self.lock_button_window.isVisible()
        self.setWindowFlags(_with_optional_mini_always_on_top(Qt.Tool | Qt.FramelessWindowHint, self.main_window))
        self.lock_button_window.setWindowFlags(_with_optional_mini_always_on_top(Qt.Tool | Qt.FramelessWindowHint, self.main_window))
        if was_visible:
            self.show()
            self.raise_()
        if lock_was_visible:
            self.lock_button_window.show()
            self.lock_button_window.raise_()

    def _hit_test_edges(self, pos: QPoint) -> str:
        margin = self._resize_margin
        edges = ""
        if pos.x() <= margin:
            edges += "l"
        elif pos.x() >= self.width() - margin:
            edges += "r"
        if pos.y() <= margin:
            edges += "t"
        elif pos.y() >= self.height() - margin:
            edges += "b"
        return edges

    def _update_resize_cursor(self, pos: QPoint):
        if self.config().get("locked", True):
            self.unsetCursor()
            return
        edges = self._hit_test_edges(pos)
        if edges in ("lt", "rb"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in ("rt", "lb"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edges in ("l", "r"):
            self.setCursor(Qt.SizeHorCursor)
        elif edges in ("t", "b"):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()

    def _resize_window(self, global_pos: QPoint):
        delta = global_pos - self._resize_start_pos
        geom = QRect(self._resize_start_geom)
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()

        if "l" in self._resize_edges:
            new_left = geom.left() + delta.x()
            if geom.right() - new_left + 1 >= min_w:
                geom.setLeft(new_left)
        if "r" in self._resize_edges:
            geom.setRight(max(geom.left() + min_w - 1, geom.right() + delta.x()))
        if "t" in self._resize_edges:
            new_top = geom.top() + delta.y()
            if geom.bottom() - new_top + 1 >= min_h:
                geom.setTop(new_top)
        if "b" in self._resize_edges:
            geom.setBottom(max(geom.top() + min_h - 1, geom.bottom() + delta.y()))
        self.setGeometry(geom)
        self._update_text_width_for_current_size()
        self._fit_height_to_content()
        self._sync_lock_button()

    def _update_text_width_for_current_size(self):
        """ウィンドウ幅に合わせて本文ラベル幅を更新する。"""
        if not hasattr(self, "text_label") or not hasattr(self, "arrow_label"):
            return
        if not self.is_compact_mode():
            self.text_label.setFixedWidth(max(150, self.width() - self.arrow_label.width() - 72))
            return

        left_width = max(
            self.arrow_label.width() if self.arrow_label.isVisible() else 0,
            self.exp_label.width() if self.exp_label.isVisible() else 0,
        )
        grip_width = self.size_grip.width() if self.size_grip.isVisible() else 0
        visible_columns = int(left_width > 0) + int(grip_width > 0)
        layout = self.outer.layout()
        available_width = layout.contentsRect().width()
        if available_width <= 0:
            return
        text_width = available_width - left_width - grip_width - layout.spacing() * visible_columns
        self.text_label.setFixedWidth(max(1, text_width))

    def _fit_height_to_content(self):
        """フォントサイズ変更時に本文が切れない高さまで自動拡張する。"""
        self._update_text_width_for_current_size()
        self.text_label.adjustSize()
        margins = self.outer.layout().contentsMargins()
        left_column_height = self.arrow_label.sizeHint().height()
        if self.exp_label.isVisible():
            left_column_height += self.exp_label.sizeHint().height()
        needed_height = max(
            self.minimumHeight(),
            self.text_label.sizeHint().height() + margins.top() + margins.bottom() + 14,
            left_column_height + margins.top() + margins.bottom() + 4,
        )
        if self.is_compact_mode():
            available = self._available_screen_geometry()
            self.resize(self.width(), min(needed_height, available.height()))
            x = min(max(self.x(), available.left()), available.right() - self.width() + 1)
            y = min(max(self.y(), available.top()), available.bottom() - self.height() + 1)
            self.move(x, y)
            self._sync_lock_button()
        elif needed_height > self.height():
            self.resize(self.width(), needed_height)
            self._sync_lock_button()

    def _render_exp_guide(self, exp_guide: dict | None) -> str:
        if not isinstance(exp_guide, dict):
            return ""
        player_level = exp_guide.get("player_level")
        enemy_level = exp_guide.get("enemy_level")
        status = html.escape(str(exp_guide.get("status", "")))
        if not player_level or not enemy_level or not status:
            return ""
        return (
            f"<span style='color:#dddddd;'>自Lv.{int(player_level)} / 敵Lv.{int(enemy_level)}</span><br>"
            f"<b>{status}</b>"
        )

    def _render_line(self, line: str) -> str:
        rendered = html.escape(str(line))
        rendered = re.sub(
            r"&lt;span style=(?:&#x27;|&quot;)\s*color:\s*(#[0-9a-fA-F]{3,8})\s*;?\s*(?:&#x27;|&quot;)\s*&gt;",
            r"<span style='color:\1'>",
            rendered,
            flags=re.IGNORECASE,
        )
        rendered = rendered.replace("&lt;/span&gt;", "</span>")
        for key in self.IMAGE_ICONS:
            rendered = rendered.replace(f"[{key}]", self._image_icon_html(key))
        for key, icon in self.ICONS.items():
            rendered = rendered.replace(f"[{key}]", f"<span style='color:#7db7ff;'>{icon}</span>")
        return self._preserve_html_spaces(rendered)

    def _assets_dir(self) -> str:
        """assetsフォルダのパス（exeフォルダ優先 → _MEIPASS）。"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            exe_assets = os.path.join(exe_dir, "assets")
            if os.path.exists(exe_assets):
                return exe_assets
            return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "assets")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")

    def _image_icon_html(self, key: str) -> str:
        filename = self.IMAGE_ICONS.get(key)
        if not filename:
            return ""
        path = os.path.join(self._assets_dir(), "icons", filename)
        if not os.path.exists(path):
            return ""
        src = path.replace("\\", "/")
        # QLabelのRichText内で本文と高さを揃えやすいよう、16px固定でインライン表示する。
        return f"<img src='{html.escape(src, quote=True)}' width='16' height='16'>"

    def _preserve_html_spaces(self, rendered: str) -> str:
        """HTMLタグ内は触らず、本文側の半角スペースを表示上も保持する。"""
        parts = re.split(r"(<[^>]+>)", rendered)
        preserved = []
        for part in parts:
            if part.startswith("<") and part.endswith(">"):
                preserved.append(part)
            else:
                preserved.append(
                    part
                    .replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
                    .replace("\u00a0", "&nbsp;")
                    .replace(" ", "&nbsp;")
                )
        return "".join(preserved)

    def _strong_opacity(self) -> float:
        # 通常表示時はウィンドウ全体を透過しない。
        # 透明度は背景alpha/text opacityで制御し、100%設定時に完全不透明になるようにする。
        return 1.0

    def _idle_opacity(self) -> float:
        cfg = self.config()
        return max(0.15, min(float(cfg.get("faded_opacity", 0.38)), self._strong_opacity()))

    def _show_strong_opacity(self, restart_fade: bool = False):
        self._fade_timer.stop()
        self.setWindowOpacity(self._strong_opacity())
        self.lock_button_window.setWindowOpacity(self._strong_opacity())
        if restart_fade:
            self._maybe_start_fade_timer()

    def _fade_to_idle_opacity(self):
        cfg = self.config()
        if not cfg.get("fade_enabled", True) or not cfg.get("locked", True):
            return
        self.setWindowOpacity(self._idle_opacity())
        # 鍵は見失わないよう本体より少し濃くする。
        self.lock_button_window.setWindowOpacity(max(self._idle_opacity(), 0.65))

    def _maybe_start_fade_timer(self):
        cfg = self.config()
        if not self.isVisible() or not cfg.get("fade_enabled", True) or not cfg.get("locked", True):
            return
        self._fade_timer.start(max(500, int(cfg.get("fade_delay_ms", 3500))))

    def _sync_lock_button(self):
        if hasattr(self, "lock_button_window"):
            self.lock_button_window.sync_from_overlay()

    def _apply_click_through(self):
        cfg = self.config()
        enabled = bool(cfg.get("locked", True) and cfg.get("click_through_when_locked", True))
        if sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        else:
            self.setWindowFlag(Qt.WindowTransparentForInput, enabled)

def _is_always_on_top_enabled(parent=None):
    """設定に応じて最前面表示を有効にするか返す。"""
    if parent is not None and hasattr(parent, "config"):
        return parent.config.get("always_on_top", True)
    return ConfigManager.load_config().get("always_on_top", True)


def _with_optional_always_on_top(flags, parent=None):
    if _is_always_on_top_enabled(parent):
        return flags | Qt.WindowStaysOnTopHint
    return flags & ~Qt.WindowStaysOnTopHint


def _is_mini_always_on_top_enabled(parent=None):
    """みになび専用の最前面表示設定。未設定時はON。"""
    if parent is not None and hasattr(parent, "config"):
        config = parent.config
    else:
        config = ConfigManager.load_config()
    mini_config = config.get("mini_guide_overlay", {}) if isinstance(config, dict) else {}
    if isinstance(mini_config, dict):
        return mini_config.get("always_on_top", True)
    return True


def _with_optional_mini_always_on_top(flags, parent=None):
    if _is_mini_always_on_top_enabled(parent):
        return flags | Qt.WindowStaysOnTopHint
    return flags & ~Qt.WindowStaysOnTopHint


class GemTrackerPopupDialog(QDialog):
    """ジェム取得リストを大きく表示するポップアウトウィンドウ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ジェム取得")
        self.resize(520, 720)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.setWindowFlags(_with_optional_always_on_top(Qt.Tool | Qt.Window, parent))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("💎 ジェム取得")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 14px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("閉じる")
        close_btn.setStyleSheet(Styles.BUTTON)
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self.gem_tracker = GemTrackerWidget()
        layout.addWidget(self.gem_tracker, stretch=1)


class SearchStringPasteTestDialog(QDialog):
    """検索文字列メニュー → PoE復帰 → 検索欄貼り付けの技術検証用ダイアログ"""

    def __init__(self, target_hwnd, choices=None, parent=None, owner=None):
        super().__init__(parent)
        self.owner = owner
        self.target_hwnd = target_hwnd
        self.choices = choices or []
        self.setWindowTitle("店売り・スタッシュ検索")
        self.setWindowFlags(_with_optional_always_on_top(Qt.Tool | Qt.FramelessWindowHint, parent))
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("🔍 店売り・スタッシュ検索")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("選択後、ホットキー時点のウィンドウへ戻して Ctrl+F → 貼り付けます。")
        hint.setStyleSheet("color: #cccccc; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for preset in self.choices:
            name = preset.get("name", "")
            query = preset.get("query", "")
            btn = QPushButton(name or query)
            btn.setToolTip(query)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setStyleSheet(Styles.BUTTON)
            btn.clicked.connect(lambda _checked=False, value=query: self._select(value))
            layout.addWidget(btn)

        cancel = QPushButton("キャンセル")
        cancel.setAutoDefault(False)
        cancel.setDefault(False)
        cancel.setStyleSheet(Styles.BUTTON)
        cancel.clicked.connect(self.close)
        layout.addWidget(cancel)

        self.adjustSize()
        pos = QCursor.pos()
        self.move(pos.x() + 12, pos.y() + 12)

    def _select(self, text):
        self.hide()
        parent = self.parent()
        if self.owner is not None:
            self.owner._debug_search(f"select preset text={text!r} initial_target={self.target_hwnd} title={self.owner._window_title(self.target_hwnd)!r}")
        if self.owner is not None:
            self.owner._set_clipboard_text_debug("search preset select", text)
        else:
            QApplication.clipboard().setText(text)
        QApplication.processEvents()
        time.sleep(0.05)
        if self.owner is not None:
            self.owner._debug_search(f"clipboard after preset copy={self.owner._clipboard_text_preview()!r}")

        target_hwnd = self.target_hwnd
        if target_hwnd and hasattr(parent, "_own_top_level_hwnds") and int(target_hwnd) in parent._own_top_level_hwnds():
            if self.owner is not None:
                self.owner._debug_search(f"target was own window; finding external behind hwnd={target_hwnd}")
            target_hwnd = get_next_visible_window_after(target_hwnd, skip_current_process=True)

        if not target_hwnd:
            QMessageBox.warning(self.parent(), "検索文字列の貼り付け", "復帰先ウィンドウを取得できませんでした。")
            return

        self.target_hwnd = target_hwnd
        if self.owner is not None:
            self.owner._search_paste_in_progress = True
            self.owner._debug_search(f"paste in progress ON target={target_hwnd} title={self.owner._window_title(target_hwnd)!r}")
        QTimer.singleShot(220, lambda: self._focus_and_paste(text, target_hwnd))

    def _focus_and_paste(self, text, target_hwnd):
        if self.owner is not None:
            self.owner._debug_search(f"focus start target={target_hwnd} title={self.owner._window_title(target_hwnd)!r} foreground_before={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r}")
        focused = focus_window(target_hwnd, wait_seconds=0.65)
        if self.owner is not None:
            self.owner._debug_search(f"focus result={focused} foreground_after={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r}")
        if not focused:
            QMessageBox.warning(
                self.parent(),
                "検索文字列の貼り付け",
                "元のウィンドウを前面化できませんでした。文字列はクリップボードへコピー済みです。",
            )
            if self.owner is not None:
                self.owner._search_paste_in_progress = False
                self.owner._debug_search("paste in progress OFF: focus failed")
            return
        QTimer.singleShot(650, lambda: self._paste_to_search(text))

    def _paste_to_search(self, text):
        try:
            controller = pynput_keyboard.Controller()
            ctrl = pynput_keyboard.Key.ctrl

            def tap(key):
                if self.owner is not None:
                    self.owner._debug_search(f"tap {key!r} foreground={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r} clipboard={self.owner._clipboard_text_preview()!r}")
                controller.press(key)
                controller.release(key)

            if self.owner is not None:
                self.owner._debug_search(f"send keys start text={text!r} foreground={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r}")
            with controller.pressed(ctrl):
                if self.owner is not None:
                    self.owner._debug_search("press Ctrl+F")
                tap('f')
            time.sleep(0.20)
            with controller.pressed(ctrl):
                if self.owner is not None:
                    self.owner._debug_search("press Ctrl+V")
                tap('v')
            time.sleep(0.08)
            print(f"[SEARCH TEST] pasted: {text}")
        except Exception as exc:
            print(f"[SEARCH TEST] paste failed: {exc}")
        finally:
            if self.owner is not None:
                self.owner._search_paste_in_progress = False
                self.owner._debug_search("paste in progress OFF: done")

class PoeVersionSelectionDialog(QDialog):
    """起動時のPoEバージョン選択ダイアログ"""

    def __init__(self, parent=None, current_version=POE1):
        super().__init__(parent)
        self.setWindowTitle("PoEバージョン選択")
        self.setModal(True)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.resize(680, 360)
        self.selected_version = current_version

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        title = QLabel("起動する対象を選んでください")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        tile_row = QHBoxLayout()
        tile_row.setSpacing(14)
        self.poe1_tile = self._create_version_tile(POE1, "PoE1", current_version == POE1)
        self.poe2_tile = self._create_version_tile(POE2, "PoE2", current_version == POE2)
        tile_row.addWidget(self.poe1_tile)
        tile_row.addWidget(self.poe2_tile)
        layout.addLayout(tile_row)

        desc2 = QLabel("※ デフォルトでは起動時に毎回確認します。設定画面からPoE1/PoE2固定にもできます。")
        desc2.setStyleSheet("color: rgba(176, 255, 123, 0.78); font-size: 12px;")
        desc2.setWordWrap(True)
        layout.addWidget(desc2)

        button_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        button_row.addStretch()
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addStretch()
        layout.addLayout(button_row)

    def _assets_dir(self):
        """assetsフォルダのパス（exeフォルダ優先 → _MEIPASS）"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isdir(os.path.join(exe_dir, "assets")):
                return os.path.join(exe_dir, "assets")
            return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "assets")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")

    def _version_icon_path(self, version):
        """バージョンタイル用アイコン候補を返す"""
        base = self._assets_dir()
        names = {
            POE1: ["poe1.png", "poe1.jpg", "poe1.ico", os.path.join("icons", "poe1.png"), os.path.join("icons", "poe1.jpg")],
            POE2: ["poe2.png", "poe2.jpg", "poe2.ico", os.path.join("icons", "poe2.png"), os.path.join("icons", "poe2.jpg")],
        }.get(version, [])
        for name in names:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path
        return None

    def _create_version_tile(self, version, title, checked=False):
        btn = QPushButton(title)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setMinimumHeight(180)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(26, 35, 24, 235), stop:1 rgba(5, 8, 6, 245));
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.28);
                border-radius: 12px;
                padding: 16px;
                text-align: center;
                font-size: 28px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(176, 255, 123, 0.72);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(40, 58, 34, 245), stop:1 rgba(8, 15, 10, 250));
            }}
            QPushButton:checked {{
                border: 2px solid {Styles.TEXT_COLOR};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(73, 110, 50, 245), stop:1 rgba(15, 27, 16, 250));
            }}
        """)
        icon_path = self._version_icon_path(version)
        if icon_path:
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(150, 150))
        self.group.addButton(btn)
        return btn

    def _accept(self):
        self.selected_version = POE2 if self.poe2_tile.isChecked() else POE1
        self.accept()



class GuideDetailLevelSelectionDialog(QDialog):
    """PoE2用のガイド表示レベル初回選択ダイアログ"""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"

    def __init__(self, parent=None, current_level=BEGINNER):
        super().__init__(parent)
        self.setWindowTitle("ガイド表示の選択")
        self.setModal(True)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.resize(780, 460)
        self.selected_level = current_level if current_level in (self.BEGINNER, self.INTERMEDIATE) else self.BEGINNER

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        title = QLabel("PoE2のガイド表示を選んでください")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("後から設定画面でいつでも変更できます。")
        desc.setStyleSheet("color: rgba(176, 255, 123, 0.78); font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        tile_row = QHBoxLayout()
        tile_row.setSpacing(14)
        self.beginner_tile = self._create_level_tile(
            self.BEGINNER,
            "初心者向け（詳細）",
            "目的・進み方・補足をしっかり表示します。\n初見や慣れていないエリア向けです。",
            self.selected_level == self.BEGINNER,
        )
        self.intermediate_tile = self._create_level_tile(
            self.INTERMEDIATE,
            "中級者向け（要点）",
            "次の目標と重要ポイントを短く表示します。\n周回に慣れてきた方向けです。",
            self.selected_level == self.INTERMEDIATE,
        )
        tile_row.addWidget(self.beginner_tile)
        tile_row.addWidget(self.intermediate_tile)
        layout.addLayout(tile_row)

        note = QLabel("※ この選択画面はPoE2モードの初回のみ表示されます。")
        note.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        button_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        button_row.addStretch()
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addStretch()
        layout.addLayout(button_row)

    def _assets_dir(self):
        """assetsフォルダのパス（exeフォルダ優先 → _MEIPASS）"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isdir(os.path.join(exe_dir, "assets")):
                return os.path.join(exe_dir, "assets")
            return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "assets")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")

    def _level_image_path(self, level):
        """ガイド表示レベル選択タイル用の画像候補を返す"""
        base = self._assets_dir()
        names = {
            self.BEGINNER: [os.path.join("guide", "beginner.png")],
            self.INTERMEDIATE: [os.path.join("guide", "intermediate.png")],
        }.get(level, [])
        for name in names:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path
        return None

    def _create_level_tile(self, level, title, description, checked=False):
        btn = QPushButton(f"{title}\n\n{description}")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setMinimumHeight(260)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(26, 35, 24, 235), stop:1 rgba(5, 8, 6, 245));
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.28);
                border-radius: 12px;
                padding: 12px;
                text-align: center;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(176, 255, 123, 0.72);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(40, 58, 34, 245), stop:1 rgba(8, 15, 10, 250));
            }}
            QPushButton:checked {{
                border: 2px solid {Styles.TEXT_COLOR};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(73, 110, 50, 245), stop:1 rgba(15, 27, 16, 250));
            }}
        """)
        image_path = self._level_image_path(level)
        if image_path:
            btn.setIcon(QIcon(image_path))
            btn.setIconSize(QSize(320, 180))
        self.group.addButton(btn)
        return btn

    def _accept(self):
        self.selected_level = self.INTERMEDIATE if self.intermediate_tile.isChecked() else self.BEGINNER
        self.accept()


class RouteSelectionDialog(QDialog):
    """ルート選択ダイアログ（初回セットアップ用）"""
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("ルート設定")
        self.setFixedSize(400, 270)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        config = config or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc = QLabel("攻略ルートを選択してください。後から設定画面で変更できます。")
        desc.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        combo_style = f"""
            QComboBox {{
                background-color: #2a2a2a; color: {Styles.TEXT_COLOR};
                border: 1px solid #555; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: #2a2a2a; color: {Styles.TEXT_COLOR};
                selection-background-color: #444;
            }}
        """
        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 12px;"
        
        form = QFormLayout()
        
        self.act3_combo = QComboBox()
        self.act3_combo.addItem("通常ルート（図書館スキップ）", "standard")
        self.act3_combo.addItem("図書館寄り道ルート", "library_detour")
        self.act3_combo.setStyleSheet(combo_style)
        cur3 = ConfigManager.effective_poe1_route_act3(config)
        idx3 = self.act3_combo.findData(cur3)
        if idx3 >= 0:
            self.act3_combo.setCurrentIndex(idx3)
        lbl3 = QLabel("Act3 ルート:")
        lbl3.setStyleSheet(label_style)
        form.addRow(lbl3, self.act3_combo)
        
        self.act8_combo = QComboBox()
        self.act8_combo.addItem("通常ルート", "standard")
        self.act8_combo.addItem("隠れた裏道（The Hidden Underbelly）ルート", "underbelly")
        self.act8_combo.setStyleSheet(combo_style)
        cur8 = ConfigManager.effective_poe1_route_act8(config)
        idx8 = self.act8_combo.findData(cur8)
        if idx8 >= 0:
            self.act8_combo.setCurrentIndex(idx8)
        lbl8 = QLabel("Act8 ルート:")
        lbl8.setStyleSheet(label_style)
        form.addRow(lbl8, self.act8_combo)
        
        layout.addLayout(form)
        layout.addStretch()
        
        tip = QLabel("あまり経験のない方は、Act3ルートは「図書館寄り道ルート」、\nAct8ルートは「通常ルート」を選択するのがおすすめです。")
        tip.setStyleSheet(f"color: #aaaaaa; font-size: 13px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)
    
    def get_routes(self) -> dict:
        return {
            "poe1_route_act3": self.act3_combo.currentData(),
            "poe1_route_act8": self.act8_combo.currentData(),
        }


class MemoDialog(QDialog):
    """ゲーム中メモ帳ダイアログ（フレームレス・色付きテキスト対応）"""
    
    COLORS = [
        ("#ff6666", "赤"), ("#4488ff", "青"), ("#ff8800", "オレンジ"),
        ("#44cc44", "緑"), ("#dddd44", "黄"), ("#dd66ff", "紫"), ("#ffffff", "白"),
    ]
    
    def __init__(self, parent=None, notes_path: str = ""):
        super().__init__(parent)
        self.setWindowFlags(_with_optional_always_on_top(Qt.Window | Qt.FramelessWindowHint, parent))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(350, 300)
        self.notes_path = notes_path
        self._drag_pos = None
        self._resize_edge = None
        self._EDGE_MARGIN = 8
        self.setMinimumSize(200, 150)
        self.setMouseTracking(True)
        
        # メインコンテナ（角丸背景）
        container = QWidget(self)
        self._container = container
        self._default_bg_alpha = 230
        container.setStyleSheet(f"""
            QWidget {{
                background: rgba(20, 20, 20, 230);
                border: 1px solid rgba(176,255,123,0.4);
                border-radius: 6px;
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 4, 8, 8)
        container_layout.setSpacing(4)
        
        # タイトルバー（ドラッグ用）
        title_bar = QWidget()
        self._title_bar = title_bar
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background: transparent; border: none;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(4, 0, 4, 0)
        
        title_label = QLabel("📝 共通メモ")
        title_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 15px; font-weight: bold; border: none;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: #888; border: none; font-size: 14px; }}
            QPushButton:hover {{ color: #ff6666; }}
        """)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        container_layout.addWidget(title_bar)
        
        text_style = f"""
            QTextEdit {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px; 
                padding: 5px; font-size: 13px;
                font-family: "MS Gothic", "Yu Gothic", "Meiryo", monospace;
            }}
        """
        
        # カラーツールバー
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background: transparent; border: none;")
        self._toolbar_widget = toolbar_widget
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(18, 18)
            cbtn.setToolTip(f"{color_name}")
            cbtn.setStyleSheet(f"""
                QPushButton {{ background: {color_code}; border: 1px solid rgba(255,255,255,0.3); border-radius: 2px; }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, c=color_code: self._set_color(c))
            toolbar.addWidget(cbtn)
        
        reset_btn = QPushButton("✕")
        reset_btn.setFixedSize(18, 18)
        reset_btn.setToolTip("色をリセット")
        reset_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(40,40,40,200); color: #888; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 2px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        reset_btn.clicked.connect(self._reset_color)
        toolbar.addWidget(reset_btn)
        toolbar.addStretch()
        container_layout.addWidget(toolbar_widget)
        
        # テキストエディタ
        from src.ui.settings_dialog import RichTextEdit
        self.text_edit = RichTextEdit()
        self.text_edit.setStyleSheet(text_style)
        self._load_notes()
        container_layout.addWidget(self.text_edit)
        
        # ダイアログ全体のレイアウト
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
    
    def apply_opacity(self, bg_opacity_pct: int, text_opacity_pct: int):
        """本体ウィンドウの透過率設定をメモにも反映"""
        # 背景透過率
        alpha = int(bg_opacity_pct / 100.0 * self._default_bg_alpha)
        te_alpha = int(bg_opacity_pct / 100.0 * 200)  # テキストエディタ背景(元: rgba(26,26,26,200))
        self._container.setStyleSheet(f"""
            QWidget {{
                background: rgba(20, 20, 20, {alpha});
                border: 1px solid rgba(176,255,123,0.4);
                border-radius: 6px;
            }}
        """)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{ 
                background: rgba(26, 26, 26, {te_alpha}); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px; 
                padding: 5px; font-size: 13px;
                font-family: "MS Gothic", "Yu Gothic", "Meiryo", monospace;
            }}
        """)
        # 文字透過率（テキストエディタ・タイトル・ツールバーに適用）
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        opacity = text_opacity_pct / 100.0
        for w in (self.text_edit, self._title_bar, self._toolbar_widget):
            effect = QGraphicsOpacityEffect(w)
            effect.setOpacity(opacity)
            w.setGraphicsEffect(effect)

    def _get_edge(self, pos):
        """マウス位置からリサイズ方向を判定"""
        m = self._EDGE_MARGIN
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        edge = ""
        if y < m: edge += "t"
        elif y > h - m: edge += "b"
        if x < m: edge += "l"
        elif x > w - m: edge += "r"
        return edge
    
    def _edge_cursor(self, edge):
        if edge in ("t", "b"): return Qt.SizeVerCursor
        if edge in ("l", "r"): return Qt.SizeHorCursor
        if edge in ("tl", "br"): return Qt.SizeFDiagCursor
        if edge in ("tr", "bl"): return Qt.SizeBDiagCursor
        return Qt.ArrowCursor
    
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        edge = self._get_edge(event.position().toPoint())
        if edge:
            self._resize_edge = edge
            self._resize_start = event.globalPosition().toPoint()
            self._resize_geo = self.geometry()
            event.accept()
        elif event.position().y() < 32:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if self._resize_edge and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_start
            geo = QRect(self._resize_geo)
            if "r" in self._resize_edge: geo.setRight(geo.right() + delta.x())
            if "b" in self._resize_edge: geo.setBottom(geo.bottom() + delta.y())
            if "l" in self._resize_edge: geo.setLeft(geo.left() + delta.x())
            if "t" in self._resize_edge: geo.setTop(geo.top() + delta.y())
            if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
                self.setGeometry(geo)
            event.accept()
        elif self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            edge = self._get_edge(event.position().toPoint())
            self.setCursor(self._edge_cursor(edge))
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self.setCursor(Qt.ArrowCursor)
    
    def _set_color(self, color: str):
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        from PySide6.QtGui import QColor
        fmt.setForeground(QColor(color))
        cursor.mergeCharFormat(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)
    
    def _reset_color(self):
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat()
        from PySide6.QtGui import QColor
        fmt.setForeground(QColor(Styles.TEXT_COLOR))
        cursor.mergeCharFormat(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)
    
    def _load_notes(self):
        if self.notes_path and os.path.exists(self.notes_path):
            try:
                with open(self.notes_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                html = data.get("content", "")
                if html:
                    self.text_edit.set_from_html(html)
            except Exception as e:
                print(f"[MemoDialog] Failed to load notes: {e}")
    
    def _save_notes(self):
        try:
            html = self.text_edit.to_storage_html()
            data = {"content": html}
            if self.notes_path:
                os.makedirs(os.path.dirname(self.notes_path), exist_ok=True)
            with open(self.notes_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[MemoDialog] Notes saved to {self.notes_path}")
        except Exception as e:
            print(f"[MemoDialog] Failed to save notes: {e}")
    
    def _save_and_close(self):
        self._save_notes()
        self.hide()
    
    def closeEvent(self, event):
        self._save_notes()
        event.accept()


class VendorSearchPresetDialog(QDialog):
    """ベンダー検索プリセット編集ダイアログ"""

    DEFAULT_PRESETS = [
        {"name": "新規プリセット", "query": "", "enabled": True},
    ]
    POE1_DEFAULT_PRESETS = [
        {"name": "3リンク（色問わず）", "query": r"-\w-", "enabled": True},
    ]
    MAX_SEARCH_QUERY_LENGTH = 250

    def __init__(self, parent=None, presets_path: str = "", poe_version: str = POE2):
        super().__init__(parent)
        from PySide6.QtWidgets import (
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
            QLineEdit, QTextEdit, QCheckBox, QGridLayout, QSpinBox,
        )

        self.QTableWidgetItem = QTableWidgetItem
        self.presets_path = presets_path
        self.poe_version = poe_version
        self._syncing = False
        self._dirty = False
        self.option_checkboxes = []
        self.helper_categories = {}
        self._poe1_other_links_checkbox = None
        self._poe1_other_link_spins = {}
        self._last_poe1_other_links_pattern = ""
        self._last_poe1_generated_patterns = set()
        self._last_poe1_selected_labels = set()
        self._saved_snapshot = []
        self.setWindowFlags(_with_optional_always_on_top(Qt.Window | Qt.FramelessWindowHint, parent))
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 初期表示は従来どおり広めに開く。小さいモニターでは手動リサイズ + REGEX欄スクロールで対応。
        self.resize(1450, 850)
        self._drag_pos = None
        self._resize_edge = None
        self._EDGE_MARGIN = 8
        self.setMinimumSize(1150, 460)
        self.setMouseTracking(True)

        container = QWidget(self)
        self._container = container
        self._default_bg_alpha = 230
        container.setStyleSheet("""
            QWidget {
                background: rgba(20, 20, 20, 230);
                border: 1px solid rgba(176,255,123,0.4);
                border-radius: 6px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 4, 8, 8)
        container_layout.setSpacing(6)

        title_bar = QWidget()
        self._title_bar = title_bar
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background: transparent; border: none;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(4, 0, 4, 0)
        title_label = QLabel(
            "🔍 PoE1 店売り検索プリセット" if self.poe_version == POE1 else "🔍 PoE2 店売り・スタッシュ検索プリセット"
        )
        title_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 15px; font-weight: bold; border: none;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size: 14px; }
            QPushButton:hover { color: #ff6666; }
        """)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        container_layout.addWidget(title_bar)

        hint_text = "左は一覧表示です。表示名・検索文字列は右側の編集枠で調整します。有効にチェックをつけたプリセットだけが検索ホットキー時のメニューに表示されます。"
        if self.poe_version == POE1:
            hint_text += " PoE1ではAct中の3リンク装備購入など、ベンダー検索向けのプリセットを管理します。"
        hint = QLabel(hint_text)
        hint.setStyleSheet("color: #aaaaaa; font-size: 13px; border: none;")
        hint.setWordWrap(True)
        container_layout.addWidget(hint)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)
        container_layout.addLayout(body_layout, stretch=1)

        # 左: 一覧（表示用 + 有効チェックのみ編集可）
        left_panel = QWidget()
        left_panel.setStyleSheet("background: transparent; border: none;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        body_layout.addWidget(left_panel, stretch=9)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["有効", "表示名", "検索文字列"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR};
                alternate-background-color: rgba(45, 55, 40, 120);
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px;
                gridline-color: rgba(176,255,123,0.15); font-size: 14px;
                selection-background-color: rgba(176,255,123,0.35);
                selection-color: #ffffff;
            }}
            QTableWidget::item:selected {{
                background: rgba(176,255,123,0.35);
                color: #ffffff;
            }}
            QTableWidget::item:focus {{ border: 1px solid #b0ff7b; }}
            QHeaderView::section {{
                background: rgba(40,40,40,230); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.25); padding: 6px;
            }}
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._load_selected_to_editor)
        self.table.itemChanged.connect(self._table_item_changed)
        left_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        for label, handler in [
            ("追加", self._add_row),
            ("削除", self._delete_selected),
            ("上へ", lambda: self._move_selected(-1)),
            ("下へ", lambda: self._move_selected(1)),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(Styles.BUTTON)
            btn.clicked.connect(handler)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.setStyleSheet(self._save_button_style())
        self.save_btn.clicked.connect(self._save_presets)
        btn_row.addWidget(self.save_btn)
        left_layout.addLayout(btn_row)

        # 右: 編集欄 + regex支援チェックボックス
        right_panel = QWidget()
        right_panel.setStyleSheet("background: rgba(10,10,10,120); border: 1px solid rgba(176,255,123,0.25); border-radius: 5px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(8)
        body_layout.addWidget(right_panel, stretch=16)

        editor_title = QLabel("編集")
        editor_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 16px; font-weight: bold; border: none;")
        right_layout.addWidget(editor_title)

        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 13px; border: none;"
        input_style = f"""
            QLineEdit, QTextEdit {{
                background: rgba(26,26,26,220); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.35); border-radius: 4px;
                padding: 7px; font-size: 14px;
            }}
        """

        name_label = QLabel("表示名")
        name_label.setStyleSheet(label_style)
        right_layout.addWidget(name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setStyleSheet(input_style)
        self.name_edit.textChanged.connect(self._editor_changed)
        right_layout.addWidget(self.name_edit)

        query_header = QHBoxLayout()
        query_header.setContentsMargins(0, 0, 0, 0)
        query_label = QLabel("検索文字列")
        query_label.setStyleSheet(label_style)
        query_header.addWidget(query_label)
        clear_query_btn = QPushButton("クリア")
        clear_query_btn.setFixedHeight(24)
        clear_query_btn.setStyleSheet(Styles.BUTTON)
        clear_query_btn.clicked.connect(self._clear_query)
        query_header.addWidget(clear_query_btn)
        query_header.addStretch()
        self.query_length_label = QLabel(f"0/{self.MAX_SEARCH_QUERY_LENGTH}")
        self.query_length_label.setStyleSheet("color: #aaaaaa; font-size: 12px; border: none;")
        query_header.addWidget(self.query_length_label)
        right_layout.addLayout(query_header)
        self.query_edit = QTextEdit()
        self.query_edit.setFixedHeight(92)
        self.query_edit.setStyleSheet(input_style)
        self.query_edit.textChanged.connect(self._editor_changed)
        right_layout.addWidget(self.query_edit)

        if self.poe_version != POE1:
            limit_note = "PoE2の検索窓は250文字が上限です。超過すると貼り付けができません。"
            self.query_limit_note = QLabel(limit_note)
            self.query_limit_note.setStyleSheet("color: #aaaaaa; font-size: 12px; border: none;")
            right_layout.addWidget(self.query_limit_note)

        helper_title = QLabel("PoE1検索作成支援（チェックすると検索文字列に追加）" if self.poe_version == POE1 else "正規表現の作成支援（チェックすると検索文字列に追加）")
        helper_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 15px; font-weight: bold; border: none; margin-top: 4px;")
        right_layout.addWidget(helper_title)

        # REGEX候補は項目が多いため、小さいモニターでも編集欄全体を見失わないよう
        # この候補エリアだけ縦横スクロール可能にする。
        helper_scroll = QScrollArea()
        helper_scroll.setWidgetResizable(True)
        helper_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        helper_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        helper_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: rgba(10,10,10,80);
                border: 1px solid rgba(176,255,123,0.18);
                border-radius: 4px;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: rgba(30,30,30,150);
                border: none;
                margin: 0;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: rgba(176,255,123,0.45);
                border-radius: 4px;
                min-height: 24px;
                min-width: 24px;
            }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background: rgba(176,255,123,0.70);
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                width: 0;
                height: 0;
            }}
        """)
        helper_content = QWidget()
        helper_content.setStyleSheet("background: transparent; border: none;")
        helper_content.setMinimumWidth(900)
        helper_layout = QVBoxLayout(helper_content)
        helper_layout.setContentsMargins(4, 4, 8, 4)
        helper_layout.setSpacing(8)
        self._build_regex_helper(helper_layout, QCheckBox, QGridLayout, QSpinBox)
        helper_layout.addStretch()
        helper_scroll.setWidget(helper_content)
        right_layout.addWidget(helper_scroll, stretch=1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        self._syncing = True
        try:
            self._load_presets()
        finally:
            self._syncing = False
        self._load_selected_to_editor()
        self._capture_saved_snapshot()

    def _save_button_style(self):
        return """
            QPushButton {
                background: #44cc66;
                color: #071407;
                border: 1px solid #b0ff7b;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover { background: #66e685; }
            QPushButton:pressed { background: #2fa84f; }
        """

    def _set_dirty(self, dirty=True):
        self._dirty = bool(dirty)
        if hasattr(self, "save_btn"):
            self.save_btn.setText("保存 *" if self._dirty else "保存")

    def _update_query_length_label(self):
        if not hasattr(self, "query_length_label"):
            return
        length = len(self._query_text()) if hasattr(self, "query_edit") else 0
        over_limit = length > self.MAX_SEARCH_QUERY_LENGTH
        color = "#ff6666" if over_limit else "#aaaaaa"
        self.query_length_label.setText(f"{length}/{self.MAX_SEARCH_QUERY_LENGTH}")
        self.query_length_label.setStyleSheet(f"color: {color}; font-size: 12px; border: none; font-weight: {'bold' if over_limit else 'normal'};")
        if hasattr(self, "query_limit_note"):
            note_color = "#ffaaaa" if over_limit else "#aaaaaa"
            self.query_limit_note.setStyleSheet(f"color: {note_color}; font-size: 12px; border: none;")

    def _capture_saved_snapshot(self):
        self._saved_snapshot = self.presets()
        self._set_dirty(False)

    def _has_unsaved_changes(self):
        return getattr(self, "_dirty", False) or self.presets() != getattr(self, "_saved_snapshot", [])

    def _mark_dirty(self):
        if not getattr(self, "_syncing", False):
            self._set_dirty(True)

    def _table_item_changed(self, item):
        if getattr(self, "_syncing", False):
            return
        # 有効チェックのON/OFFも保存対象。
        self._set_dirty(True)

    WEAPON_BASE_AND_CATEGORY = "武器ベース"
    WEAPON_BASE_OR_CATEGORY = "武器ベース（OR条件）"
    WEAPON_BASE_OPTIONS = [
        ("弓", "弓$"),
        ("クロスボウ", "ロスボウ$"),
        ("槍（スピア）", "スピア$"),
        ("クォータースタッフ", "タースタッフ$"),
        ("ワンド", "ワンド$"),
        ("スタッフ", "(^|[^ー])スタッフ$"),
        ("セプター", "プター$"),
        ("片手メイス", "片手メイス$"),
        ("両手メイス", "両手メイス$"),
        ("タリスマン", "スマン$"),
        ("矢筒", "矢筒$"),
        ("盾", "盾$"),
        ("バックラー", "ックラー$"),
        ("フォーカス", "ォーカス$"),
    ]

    REGEX_HELPER_GROUPS = [
        (
            "共通",
            [
            ("移動スピード+", "動ス"),
            ("最大ライフ+", "大ラ"),
            ("耐性+", "耐"),
            ("スピリット+", "ト +"),
            ("筋力", "筋"),
            ("器用さ", "器"),
            ("知性", "知"),
        ],
        ),
        (
            "ビルド別",
            [
            ("全ての近接スキルのレベル+", "接スキ"),
            ("全ての投射物スキルのレベル+", "物スキ"),
            ("全てのスペルスキル+", "てのス"),
            ("火スペルスキル+", "火スペ"),
            ("冷気スペルスキル+", "気スペ"),
            ("雷スペルスキル+", "雷スペ"),
            ("混沌スペルスキル+", "沌スペ"),
            ("物理スペルスキル+", "理スペ"),
            ("ミニオンスキル+", "てのミ"),
            ("物理ダメージが#%増加する", "理ダ.*増"),
            ("#の物理ダメージを追加する", "理.*ジを追"),
            ("#の火ダメージを追加する", "火.*ジを追"),
            ("#の冷気ダメージを追加する", "気.*ジを追"),
            ("#の雷ダメージを追加する", "雷.*ジを追"),
            ("#の物理ダメージをアタックに追加する", "理ダ.*をア"),
            ("#の火ダメージをアタックに追加する", "火ダ.*をア"),
            ("#の冷気ダメージをアタックに追加する", "気ダ.*をア"),
            ("#の雷ダメージをアタックに追加する", "雷ダ.*をア"),
            ("スペルダメージが#%増加する ", "ルダ.*増"),
            ("ダメージの#%を追加火ダメ獲得", "加火"),
            ("ダメージの#%を追加冷気ダメ獲得", "加冷"),
            ("ダメージの#%を追加雷ダメ獲", "加雷"),
        ],
        ),
        (WEAPON_BASE_AND_CATEGORY, WEAPON_BASE_OPTIONS),
        (WEAPON_BASE_OR_CATEGORY, WEAPON_BASE_OPTIONS),
    ]

    POE1_REGEX_HELPER_GROUPS = [
        (
            'Link colors (3L)',
            [
                ('rrr', 'r-r-r'),
                ('ggg', 'g-g-g'),
                ('bbb', 'b-b-b'),
                ('rrg', 'r-r-g|r-g-r|g-r-r'),
                ('rrb', 'r-r-b|r-b-r|b-r-r'),
                ('ggb', 'g-g-b|g-b-g|b-g-g'),
                ('ggr', 'g-g-r|g-r-g|r-g-g'),
                ('bbr', 'b-b-r|b-r-b|r-b-b'),
                ('bbg', 'b-b-g|b-g-b|g-b-b'),
                ('rgb', ':.*(?=\\S*r)(?=\\S*g)(?=\\S*b)'),
                ('rr*', 'r-r-|-r-r|r-.-r'),
                ('gg*', 'g-g-|-g-g|g-.-g'),
                ('bb*', 'b-b-|-b-b|b-.-b'),
                ('r**', '.-.-r|.-r-.|r-.-.'),
                ('g**', '.-.-g|.-g-.|g-.-.'),
                ('b**', '.-.-b|.-b-.|b-.-.'),
            ],
        ),
        (
            'Link colors (2L)',
            [
                ('rr', 'r-r'),
                ('gg', 'g-g'),
                ('bb', 'b-b'),
                ('rb', 'r-b|b-r'),
                ('gr', 'g-r|r-g'),
                ('bg', 'b-g|g-b'),
            ],
        ),
        (
            'Any links',
            [
                ('Any 3 link', '-\\w-'),
                ('Any 4 link', '-\\w-.-'),
                ('Any 5 link', '(-\\w){4}'),
                ('Any 6 link', '(-\\w){5}'),
                ('Any 6 socket', '(\\w\\W){5}'),
            ],
        ),
        (
            'Movement Speed',
            [
                ('Movement speed (10%)', 'Runn'),
                ('Movement speed (15%)', 'rint'),
            ],
        ),
        (
            'Misc',
            [
                ('+1 wand (any)', '全てのスペ'),
                ('+1 lightning wand', 'derha'),
                ('+1 fire wand', '"me Sh"'),
                ('+1 cold wand', 'singe'),
                ('+1 phys wand', 'Litho'),
                ('+1 chaos wand', 'Lord'),
                ('Physical damage', 'Glint|Heav'),
                ('フラット元素ダメージ', 'Heat|roste|Humm'),
                ('Fire DOT multi', 'Earn'),
                ('Cold DOT multi', 'Incl'),
                ('Chaos DOT multi', 'Wani'),
            ],
        ),
        (
            'Weapon Bases',
            [
                ('Axe', '斧$'),
                ('Mace', 'メイス$'),
                ('Sword', '剣$'),
                ('Staff', 'スタッフ$'),
                ('Sceptre', 'セプター$'),
                ('Claw', '鉤爪$'),
                ('Bow', '弓$'),
                ('Wand', 'ワンド$'),
                ('Dagger', '短剣$'),
                ('Shield', 'ック率:'),
            ],
        ),
    ]

    POE1_REGEX_HELPER_CATEGORY_LABELS = {
        'Any links': '任意リンク・任意ソケット',
        'Link colors (2L)': 'リンク色（2リンク）',
        'Link colors (3L)': 'リンク色（3リンク）',
        'Misc': 'その他',
        'Movement Speed': '移動速度',
        'Other Links': 'その他リンク',
        'Weapon Bases': '武器ベース（上記の条件とOR条件で絞り込み。チェックした武器は条件に依らず、すべてハイライトされます）',
    }

    POE1_REGEX_HELPER_LABELS = {
        'フラット元素ダメージ': 'フラット元素ダメージ',
        '+1 chaos wand': '全ての混沌スペルスキル+1',
        '+1 cold wand': '全ての冷気スペルスキル+1',
        '+1 fire wand': '全ての火スペルスキル+1',
        '+1 lightning wand': '全ての雷スペルスキル+1',
        '+1 phys wand': '全ての物理スペルスキル+1',
        '+1 wand (any)': '全てのスペルスキル+1',
        'Any 3 link': '3リンク',
        'Any 4 link': '4リンク',
        'Any 5 link': '5リンク',
        'Any 6 link': '6リンク',
        'Any 6 socket': '6ソケット',
        'Axe': '斧',
        'Bow': '弓',
        'Chaos DOT multi': '混沌継続ダメージ',
        'Claw': '鉤爪',
        'Cold DOT multi': '冷気継続ダメージ',
        'Dagger': '短剣',
        'Fire DOT multi': '火継続ダメージ',
        'Mace': 'メイス',
        'Movement speed (10%)': '移動スピード10%',
        'Movement speed (15%)': '移動スピード15%',
        'Physical damage': '物理ダメージ',
        'Sceptre': 'セプター',
        'Shield': '盾',
        'Staff': 'スタッフ',
        'Sword': '剣',
        'Wand': 'ワンド',
        'b**': 'B●-＊-＊',
        'bb': 'B●-B●',
        'bb*': 'B●-B●-＊',
        'bbb': 'B●-B●-B●',
        'bbg': 'B●-B●-G●',
        'bbr': 'B●-B●-R●',
        'bg': 'B●-G●',
        'g**': 'G●-＊-＊',
        'gg': 'G●-G●',
        'gg*': 'G●-G●-＊',
        'ggb': 'G●-G●-B●',
        'ggg': 'G●-G●-G●',
        'ggr': 'G●-G●-R●',
        'gr': 'G●-R●',
        'r**': 'R●-＊-＊',
        'rb': 'R●-B●',
        'rgb': 'R●-G●-B●',
        'rr': 'R●-R●',
        'rr*': 'R●-R●-＊',
        'rrb': 'R●-R●-B●',
        'rrg': 'R●-R●-G●',
        'rrr': 'R●-R●-R●',
    }

    def _default_presets(self):
        return self.POE1_DEFAULT_PRESETS if self.poe_version == POE1 else self.DEFAULT_PRESETS

    def _load_regex_helper_groups(self):
        """REGEX支援チェックボックス候補を返す。tasks配下の作業CSVには依存しない。"""
        groups = self.POE1_REGEX_HELPER_GROUPS if self.poe_version == POE1 else self.REGEX_HELPER_GROUPS
        return [(category, list(options)) for category, options in groups]

    def _build_regex_helper(self, parent_layout, QCheckBox, QGridLayout, QSpinBox=None):
        assets_dir = os.path.join(ConfigManager._get_base_dir(), "assets")
        if not os.path.exists(os.path.join(assets_dir, "checkmark_lime.svg")):
            assets_dir = os.path.join(getattr(sys, "_MEIPASS", ConfigManager._get_base_dir()), "assets")
        checkmark_path = os.path.join(assets_dir, "checkmark_lime.svg").replace("\\", "/")
        checkbox_style = f"""
            QCheckBox {{ color: {Styles.TEXT_COLOR}; font-size: 14px; spacing: 8px; border: none; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid rgba(176,255,123,0.75);
                border-radius: 2px;
                background: rgba(230,230,230,0.18);
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid #b0ff7b;
                background: rgba(176,255,123,0.18);
            }}
            QCheckBox::indicator:checked {{
                background: rgba(20, 28, 20, 220);
                border: 1px solid #b0ff7b;
                image: url("{checkmark_path}");
            }}
        """
        section_style = "color: #44cc66; font-size: 16px; font-weight: bold; border: none; margin-top: 6px;"
        self.option_checkboxes = []
        self.helper_categories = {}
        if self.poe_version == POE1:
            self._build_poe1_regex_helper(parent_layout, QCheckBox, QGridLayout, QSpinBox, checkbox_style, section_style)
            return
        groups = self._load_regex_helper_groups()
        if not groups:
            note = QLabel("REGEX支援候補が空です。")
            note.setStyleSheet("color: #ffaaaa; font-size: 13px; border: none;")
            parent_layout.addWidget(note)
            return
        for group_title, options in groups:
            section_text = group_title
            if group_title == self.WEAPON_BASE_AND_CATEGORY:
                section_text = "武器ベース（共通・ビルド別とAND条件で絞り込み。チェックすると特定の武器に限定した検索文字列になります）"
            elif group_title == self.WEAPON_BASE_OR_CATEGORY:
                section_text = "武器ベース（共通・ビルド別とOR条件で絞り込み。チェックした武器は共通・ビルド別の条件に依らず、すべてハイライトされます）"
            section = QLabel(section_text)
            section.setStyleSheet(section_style)
            parent_layout.addWidget(section)
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(26)
            grid.setVerticalSpacing(8)
            columns = 4
            row_offset = 0
            added_damage_row_aligned = False
            attack_row_aligned = False
            for index, (label, token) in enumerate(options):
                position = index + row_offset
                if (
                    group_title == "ビルド別"
                    and not added_damage_row_aligned
                    and "ダメージを追加" in label
                    and "アタック" not in label
                ):
                    if position % columns != 0:
                        row_offset += columns - (position % columns)
                        position = index + row_offset
                    added_damage_row_aligned = True
                if (
                    group_title == "ビルド別"
                    and not attack_row_aligned
                    and "アタックに追加" in label
                ):
                    if position % columns != 0:
                        row_offset += columns - (position % columns)
                        position = index + row_offset
                    attack_row_aligned = True
                cb = QCheckBox(label)
                cb.setToolTip(token)
                cb.setStyleSheet(checkbox_style)
                cb.toggled.connect(lambda checked, t=token: self._regex_option_toggled(t, checked))
                self.option_checkboxes.append((cb, token, group_title))
                self.helper_categories[token] = group_title
                grid.addWidget(cb, position // columns, position % columns)
            parent_layout.addLayout(grid)


    def _poe1_category_display_name(self, category):
        return self.POE1_REGEX_HELPER_CATEGORY_LABELS.get(category, category)

    def _poe1_label_display_name(self, label):
        return self.POE1_REGEX_HELPER_LABELS.get(label, label)

    def _poe1_checkbox_label_key(self, checkbox):
        return checkbox.property("poe1_label_key") or checkbox.text()

    def _poe1_icon_path(self, color):
        filename = {"r": "red.png", "g": "green.png", "b": "blue.png"}.get(color)
        if not filename:
            return ""
        candidates = [
            os.path.join(ConfigManager._get_base_dir(), "assets", "icons", filename),
            os.path.join(getattr(sys, "_MEIPASS", ConfigManager._get_base_dir()), "assets", "icons", filename),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path.replace("\\", "/")
        return ""

    def _poe1_link_icon_html(self, label):
        label = (label or "").strip().lower()
        if not re.fullmatch(r"[rgb*]{2,3}", label):
            return ""
        parts = []
        for ch in label:
            if ch == "*":
                parts.append('<span style="font-size:16px; color:#dddddd;">＊</span>')
                continue
            icon_path = self._poe1_icon_path(ch)
            if not icon_path:
                return ""
            parts.append(f'<img src="{icon_path}" width="20" height="18" style="vertical-align:middle;"/>')
        return '<span style="white-space:nowrap;">' + '<span style="color:#aaaaaa; padding:0 2px;">-</span>'.join(parts) + '</span>'

    def _toggle_checkbox_from_label(self, checkbox):
        checkbox.setChecked(not checkbox.isChecked())

    def _build_poe1_regex_helper(self, parent_layout, QCheckBox, QGridLayout, QSpinBox, checkbox_style, section_style):
        """PoE1用REGEX作成支援UI。よく使われるPoE1 regexサイトのカテゴリ構成に寄せる。"""
        groups = self._load_regex_helper_groups()
        for group_title, options in groups:
            section = QLabel(self._poe1_category_display_name(group_title))
            section.setStyleSheet(section_style)
            parent_layout.addWidget(section)

            if group_title == "Other Links":
                self._build_poe1_other_links(parent_layout, QCheckBox, QSpinBox, checkbox_style)
                continue

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(8)
            columns = 3 if group_title in ("Movement Speed", "Misc", "Weapon Bases") else 2
            for index, (label, token) in enumerate(options):
                icon_html = self._poe1_link_icon_html(label) if group_title in ("Link colors (3L)", "Link colors (2L)") else ""
                cb = QCheckBox("" if icon_html else self._poe1_label_display_name(label))
                cb.setProperty("poe1_label_key", label)
                cb.setToolTip(token)
                cb.setStyleSheet(checkbox_style)
                cb.toggled.connect(lambda checked, t=token: self._regex_option_toggled(t, checked))
                self.option_checkboxes.append((cb, token, group_title))
                self.helper_categories[token] = group_title
                if group_title == "Link colors (3L)":
                    if index < 6:
                        row, col = index, 0
                    elif index < 12:
                        row, col = index - 6, 1
                    else:
                        row, col = index - 12, 2
                elif group_title == "Link colors (2L)":
                    row, col = index % 2, index // 2
                elif group_title == "Any links":
                    if index < 2:
                        row, col = index, 0
                    elif index < 4:
                        row, col = index - 2, 1
                    else:
                        row, col = index - 4, 2
                elif group_title == "Weapon Bases":
                    if index < 3:
                        row, col = index, 0
                    elif index < 6:
                        row, col = index - 3, 1
                    elif index < 9:
                        row, col = index - 6, 2
                    else:
                        row, col = index - 9, 3
                else:
                    row, col = index // columns, index % columns
                if icon_html:
                    item = QWidget()
                    item_layout = QHBoxLayout(item)
                    item_layout.setContentsMargins(0, 0, 0, 0)
                    item_layout.setSpacing(6)
                    item_layout.addWidget(cb)
                    label_widget = QLabel(icon_html)
                    label_widget.setTextFormat(Qt.RichText)
                    label_widget.setToolTip(token)
                    label_widget.setCursor(QCursor(Qt.PointingHandCursor))
                    label_widget.setStyleSheet("border: none; padding: 1px 2px;")
                    label_widget.mousePressEvent = lambda _event, c=cb: self._toggle_checkbox_from_label(c)
                    item_layout.addWidget(label_widget)
                    item_layout.addStretch()
                    grid.addWidget(item, row, col)
                else:
                    grid.addWidget(cb, row, col)
            parent_layout.addLayout(grid)

            if group_title == "Any links":
                other_section = QLabel(self._poe1_category_display_name("Other Links"))
                other_section.setStyleSheet(section_style)
                parent_layout.addWidget(other_section)
                self._build_poe1_other_links(parent_layout, QCheckBox, QSpinBox, checkbox_style)

    def _build_poe1_other_links(self, parent_layout, QCheckBox, QSpinBox, checkbox_style):
        if QSpinBox is None:
            return
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        enable_cb = QCheckBox("有効化")
        enable_cb.setMinimumHeight(28)
        enable_cb.setStyleSheet(checkbox_style + """
            QCheckBox { padding: 4px 8px; }
            QCheckBox::indicator { width: 20px; height: 20px; }
        """)
        enable_cb.toggled.connect(lambda _checked: self._poe1_other_links_changed())
        self._poe1_other_links_checkbox = enable_cb
        row.addWidget(enable_cb)
        row.addStretch()
        parent_layout.addLayout(row)

        spin_style = f"""
            QSpinBox {{
                background: rgba(245,245,245,230); color: #111;
                border: 1px solid rgba(176,255,123,0.45); border-radius: 3px;
                padding: 4px 20px 4px 6px; font-size: 14px;
            }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 16px;
                height: 14px;
                border-left: 1px solid rgba(0,0,0,0.35);
                border-bottom: 1px solid rgba(0,0,0,0.25);
                background: rgba(235,235,235,245);
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 16px;
                height: 14px;
                border-left: 1px solid rgba(0,0,0,0.35);
                background: rgba(225,225,225,245);
            }}
            QSpinBox::up-arrow {{
                width: 0px; height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #111;
            }}
            QSpinBox::down-arrow {{
                width: 0px; height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #111;
            }}
        """
        color_row = QHBoxLayout()
        color_row.setContentsMargins(24, 0, 0, 0)
        color_row.setSpacing(8)
        color_defs = [("R", "#c76a46"), ("G", "#b9c85a"), ("B", "#7f8fcf")]
        self._poe1_other_link_spins = {}
        for key, color in color_defs:
            spin = QSpinBox()
            spin.setRange(0, 6)
            spin.setValue(0)
            spin.setFixedSize(70, 32)
            spin.setStyleSheet(spin_style)
            spin.valueChanged.connect(lambda _value: self._poe1_other_links_changed())
            self._poe1_other_link_spins[key] = spin
            color_row.addWidget(spin)
            label = QLabel(key.lower())
            label.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold; border: none;")
            color_row.addWidget(label)
        color_row.addStretch()
        parent_layout.addLayout(color_row)

    def _poe1_other_links_pattern(self):
        if self.poe_version != POE1:
            return ""
        cb = getattr(self, "_poe1_other_links_checkbox", None)
        spins = getattr(self, "_poe1_other_link_spins", {})
        if cb is None or not cb.isChecked() or not spins:
            return ""
        counts = {key: spin.value() for key, spin in spins.items()}
        total = sum(counts.values())
        if total < 2 or total > 6:
            return ""
        # 参考サイト式: 全順列列挙ではなく、ソケット色数lookahead + 最低リンク条件で短く表現する。
        # 例 G=4 → ts:.+(?=(\S*g){4})
        # 例 R=1, G=4 → ts:.+(?=(\S*r){1})(?=(\S*g){4})
        parts = ["ts:.+"]
        color_counts = [
            (color, counts.get(key, 0))
            for key, color in (("R", "r"), ("G", "g"), ("B", "b"))
            if counts.get(key, 0)
        ]
        for index, (color, count) in enumerate(color_counts):
            is_last_of_three_colors = len(color_counts) == 3 and index == len(color_counts) - 1
            if is_last_of_three_colors:
                parts.append(f"(\\S*{color}){{{count}}}")
            else:
                parts.append(f"(?=(\\S*{color}){{{count}}})")
        return "".join(parts)

    def _poe1_other_links_changed(self):
        if getattr(self, "_syncing", False):
            return
        self._regex_option_toggled("", True)

    def _clear_query(self):
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            self.query_edit.clear()
            for cb, _token, _category in getattr(self, "option_checkboxes", []):
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            if self._poe1_other_links_checkbox is not None:
                self._poe1_other_links_checkbox.blockSignals(True)
                self._poe1_other_links_checkbox.setChecked(False)
                self._poe1_other_links_checkbox.blockSignals(False)
            for spin in getattr(self, "_poe1_other_link_spins", {}).values():
                spin.blockSignals(True)
                spin.setValue(0)
                spin.blockSignals(False)
            self._last_poe1_other_links_pattern = ""
            self._last_poe1_generated_patterns = set()
            self._last_poe1_selected_labels = set()
        finally:
            self._syncing = False
        self._editor_changed()

    def _item(self, text=""):
        item = self.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _current_row(self):
        return self.table.currentRow()

    def _load_selected_to_editor(self):
        if getattr(self, "_syncing", False):
            return
        row = self._current_row()
        self._syncing = True
        try:
            if row < 0:
                self.name_edit.clear()
                self.query_edit.clear()
                return
            name_item = self.table.item(row, 1)
            query_item = self.table.item(row, 2)
            self.name_edit.setText(name_item.text() if name_item else "")
            self.query_edit.setPlainText(query_item.text() if query_item else "")
            self._refresh_regex_checkboxes()
        finally:
            self._syncing = False
            self._update_query_length_label()

    def _editor_changed(self):
        self._update_query_length_label()
        if getattr(self, "_syncing", False):
            return
        row = self._current_row()
        if row < 0:
            return
        name = self.name_edit.text().strip()
        query = self.query_edit.toPlainText().strip()
        self._syncing = True
        try:
            if self.table.item(row, 1):
                self.table.item(row, 1).setText(name)
            if self.table.item(row, 2):
                self.table.item(row, 2).setText(query)
            self._refresh_regex_checkboxes()
        finally:
            self._syncing = False
        self._set_dirty(True)

    ATTACK_DAMAGE_TOKEN_ORDER = [
        ("理ダ.*をア", "理"),
        ("火ダ.*をア", "火"),
        ("気ダ.*をア", "気"),
        ("雷ダ.*をア", "雷"),
    ]
    ADDED_DAMAGE_TOKEN_ORDER = [
        ("理.*ジを追", "理"),
        ("火.*ジを追", "火"),
        ("気.*ジを追", "気"),
        ("雷.*ジを追", "雷"),
    ]
    SPELL_SKILL_TOKEN_ORDER = [
        ("火スペ", "火"),
        ("気スペ", "気"),
        ("雷スペ", "雷"),
        ("沌スペ", "沌"),
        ("理スペ", "理"),
    ]

    def _query_text(self):
        return self.query_edit.toPlainText().strip()

    def _token_map(self, token_order):
        return dict(token_order)

    def _attack_token_map(self):
        return self._token_map(self.ATTACK_DAMAGE_TOKEN_ORDER)

    def _added_damage_token_map(self):
        return self._token_map(self.ADDED_DAMAGE_TOKEN_ORDER)

    def _spell_skill_token_map(self):
        return self._token_map(self.SPELL_SKILL_TOKEN_ORDER)

    def _is_attack_damage_token(self, token):
        return token in self._attack_token_map()

    def _is_added_damage_token(self, token):
        return token in self._added_damage_token_map()

    def _is_spell_skill_token(self, token):
        return token in self._spell_skill_token_map()

    def _is_combined_damage_token(self, token):
        return self._is_attack_damage_token(token) or self._is_added_damage_token(token) or self._is_spell_skill_token(token)

    def _damage_combined_pattern(self, selected_tokens, token_order, suffix):
        chars = "".join(name for token, name in token_order if token in selected_tokens)
        if len(chars) < 2:
            return ""
        return f"[{chars}]{suffix}"

    def _attack_damage_combined_pattern(self, selected_tokens):
        return self._damage_combined_pattern(selected_tokens, self.ATTACK_DAMAGE_TOKEN_ORDER, "ダ.*をア")

    def _added_damage_combined_pattern(self, selected_tokens):
        return self._damage_combined_pattern(selected_tokens, self.ADDED_DAMAGE_TOKEN_ORDER, ".*ジを追")

    def _spell_skill_combined_pattern(self, selected_tokens):
        return self._damage_combined_pattern(selected_tokens, self.SPELL_SKILL_TOKEN_ORDER, "スペ")

    def _all_damage_patterns(self, token_order, combined_pattern_func):
        patterns = [token for token, _name in token_order]
        tokens = [token for token, _name in token_order]
        for mask in range(1, 1 << len(tokens)):
            selected = [token for i, token in enumerate(tokens) if mask & (1 << i)]
            combined = combined_pattern_func(selected)
            if combined:
                patterns.append(combined)
        return patterns

    def _all_attack_damage_patterns(self):
        return self._all_damage_patterns(self.ATTACK_DAMAGE_TOKEN_ORDER, self._attack_damage_combined_pattern)

    def _all_added_damage_patterns(self):
        return self._all_damage_patterns(self.ADDED_DAMAGE_TOKEN_ORDER, self._added_damage_combined_pattern)

    def _all_spell_skill_patterns(self):
        return self._all_damage_patterns(self.SPELL_SKILL_TOKEN_ORDER, self._spell_skill_combined_pattern)

    def _all_combined_damage_patterns(self):
        return self._all_attack_damage_patterns() + self._all_added_damage_patterns() + self._all_spell_skill_patterns()

    def _combined_attack_damage_matches(self, query):
        return re.findall(r"\[([^\[\]]*)\]ダ\.\*をア", query)

    def _combined_added_damage_matches(self, query):
        return re.findall(r"\[([^\[\]]*)\]\.\*ジを追", query)

    def _combined_spell_skill_matches(self, query):
        return re.findall(r"\[([^\[\]]*)\]スペ", query)

    def _split_query_patterns(self, query):
        """検索文字列をトップレベルの | で分割する。引用/括弧/文字クラス内の | は分割しない。"""
        query = (query or "").strip().strip("|")
        if not query:
            return []
        patterns = []
        buf = []
        paren_depth = 0
        bracket_depth = 0
        in_quote = False
        for ch in query:
            if ch == '"':
                in_quote = not in_quote
            elif not in_quote and ch == "(":
                paren_depth += 1
            elif not in_quote and ch == ")" and paren_depth > 0:
                paren_depth -= 1
            elif not in_quote and ch == "[":
                bracket_depth += 1
            elif not in_quote and ch == "]" and bracket_depth > 0:
                bracket_depth -= 1
            if ch == "|" and not in_quote and paren_depth == 0 and bracket_depth == 0:
                part = "".join(buf).strip()
                if part:
                    patterns.append(part)
                buf = []
            else:
                buf.append(ch)
        part = "".join(buf).strip()
        if part:
            patterns.append(part)
        return patterns

    def _join_query_patterns(self, patterns):
        seen = []
        for pattern in patterns:
            pattern = (pattern or "").strip()
            if pattern and pattern not in seen:
                seen.append(pattern)
        return "|".join(seen)

    def _remove_exact_query_pattern_from_text(self, query, pattern):
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if p != pattern])

    def _remove_attack_damage_patterns_from_text(self, query):
        attack_patterns = set(self._all_attack_damage_patterns())
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if p not in attack_patterns])

    def _remove_combined_damage_patterns_from_text(self, query):
        damage_patterns = set(self._all_combined_damage_patterns())
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if p not in damage_patterns])

    def _has_plain_query_token(self, token):
        return token in self._split_query_patterns(self._query_text())

    def _selected_damage_tokens_from_query(self, token_order, combined_matches_func):
        selected = set()
        combined_names = set()
        for pattern in self._split_query_patterns(self._query_text()):
            if pattern in dict(token_order):
                selected.add(pattern)
                continue
            for group in combined_matches_func(pattern):
                combined_names.update(ch for ch in group if ch.strip())
        for token, name in token_order:
            if name in combined_names:
                selected.add(token)
        return selected

    def _selected_attack_damage_tokens_from_query(self):
        return self._selected_damage_tokens_from_query(
            self.ATTACK_DAMAGE_TOKEN_ORDER,
            self._combined_attack_damage_matches,
        )

    def _selected_added_damage_tokens_from_query(self):
        return self._selected_damage_tokens_from_query(
            self.ADDED_DAMAGE_TOKEN_ORDER,
            self._combined_added_damage_matches,
        )

    def _selected_spell_skill_tokens_from_query(self):
        return self._selected_damage_tokens_from_query(
            self.SPELL_SKILL_TOKEN_ORDER,
            self._combined_spell_skill_matches,
        )

    def _has_query_token(self, token):
        if self._is_attack_damage_token(token):
            return token in self._selected_attack_damage_tokens_from_query()
        if self._is_added_damage_token(token):
            return token in self._selected_added_damage_tokens_from_query()
        if self._is_spell_skill_token(token):
            return token in self._selected_spell_skill_tokens_from_query()
        return self._has_plain_query_token(token)

    def _pattern_has_helper_token(self, pattern, token):
        pattern = (pattern or "").strip()
        if pattern == token:
            return True
        if pattern.startswith("(") and pattern.endswith(")"):
            return token in self._split_query_patterns(pattern[1:-1])
        return False

    def _and_base_tokens_from_query(self):
        base_tokens = {token for _label, token in self.WEAPON_BASE_OPTIONS}
        selected = set()
        quoted_and_re = re.compile(r'^"(?P<mod>.*)""(?P<base>.*)"$')
        for pattern in self._split_query_patterns(self._query_text()):
            match = quoted_and_re.fullmatch(pattern)
            if match:
                base_expr = match.group("base")
                selected.update(token for token in base_tokens if self._pattern_has_helper_token(base_expr, token))
        return selected

    def _or_base_tokens_from_query(self):
        base_tokens = {token for _label, token in self.WEAPON_BASE_OPTIONS}
        selected = set()
        quoted_and_re = re.compile(r'^"(?P<mod>.*)""(?P<base>.*)"$')
        for pattern in self._split_query_patterns(self._query_text()):
            match = quoted_and_re.fullmatch(pattern)
            if match:
                mod_expr = match.group("mod")
                selected.update(token for token in base_tokens if self._pattern_has_helper_token(mod_expr, token))
                continue
            if pattern in base_tokens:
                selected.add(pattern)
                continue
            if pattern.startswith("(") and pattern.endswith(")"):
                selected.update(token for token in base_tokens if self._pattern_has_helper_token(pattern, token))
        return selected

    def _append_query_token(self, token):
        patterns = self._split_query_patterns(self._query_text())
        if token not in patterns:
            patterns.append(token)
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _remove_query_token(self, token):
        self.query_edit.setPlainText(self._remove_exact_query_pattern_from_text(self._query_text(), token))

    def _set_attack_damage_selection(self, selected_tokens):
        patterns = self._split_query_patterns(self._remove_attack_damage_patterns_from_text(self._query_text()))
        selected_tokens = [token for token, _name in self.ATTACK_DAMAGE_TOKEN_ORDER if token in selected_tokens]
        if len(selected_tokens) == 1:
            patterns.append(selected_tokens[0])
        else:
            combined = self._attack_damage_combined_pattern(selected_tokens)
            if combined:
                patterns.append(combined)
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _append_damage_group_expr(self, parts, tokens, token_order, combined_pattern_func):
        selected_tokens = [token for token, _name in token_order if token in tokens]
        if len(selected_tokens) == 1:
            parts.append(selected_tokens[0])
        elif len(selected_tokens) > 1:
            parts.append(combined_pattern_func(selected_tokens))
        return selected_tokens

    def _helper_group_expr(self, tokens, force_group=False):
        tokens = [token for token in tokens if token]
        if not tokens:
            return ""
        parts = []
        attack_tokens = self._append_damage_group_expr(
            parts,
            tokens,
            self.ATTACK_DAMAGE_TOKEN_ORDER,
            self._attack_damage_combined_pattern,
        )
        added_damage_tokens = self._append_damage_group_expr(
            parts,
            tokens,
            self.ADDED_DAMAGE_TOKEN_ORDER,
            self._added_damage_combined_pattern,
        )
        spell_skill_tokens = self._append_damage_group_expr(
            parts,
            tokens,
            self.SPELL_SKILL_TOKEN_ORDER,
            self._spell_skill_combined_pattern,
        )
        grouped_tokens = set(attack_tokens + added_damage_tokens + spell_skill_tokens)
        other_tokens = [token for token in tokens if token not in grouped_tokens]
        parts.extend(other_tokens)
        if len(parts) == 1 and not force_group:
            return parts[0]
        return f"({'|'.join(parts)})"

    def _poe1_helper_tokens(self):
        if self.poe_version != POE1:
            return []
        return [token for _cb, token, _category in getattr(self, "option_checkboxes", []) if token]

    def _poe1_token_alternatives(self, token):
        token = (token or "").strip()
        if not token:
            return []
        # PoE1の既存REGEXサイトに合わせ、OR式は括らずフラットな候補列として扱う。
        return self._split_query_patterns(token) if "|" in token else [token]

    def _poe1_pattern_matches_token(self, pattern, token):
        pattern = (pattern or "").strip()
        token = (token or "").strip()
        if not pattern or not token:
            return False
        if pattern == token:
            return True
        if pattern.startswith("(") and pattern.endswith(")") and pattern[1:-1] == token:
            return True
        return pattern in self._poe1_token_alternatives(token)

    def _expand_poe1_link_pattern(self, pattern):
        """r-r-[gb] のような圧縮リンク表現を個別候補へ展開する。"""
        pattern = (pattern or "").strip()
        parts = pattern.split("-")
        if len(parts) < 2:
            return [pattern] if pattern else []
        expanded = [""]
        for part in parts:
            if re.fullmatch(r"\[[rgb.]+\]", part):
                choices = list(part[1:-1])
            else:
                choices = [part]
            expanded = [f"{prefix}-{choice}" if prefix else choice for prefix in expanded for choice in choices]
        return expanded

    def _expanded_poe1_query_patterns(self):
        expanded = []
        for pattern in self._split_query_patterns(self._query_text()):
            expanded.extend(self._expand_poe1_link_pattern(pattern))
        return expanded

    def _poe1_query_has_token(self, token):
        query_patterns = set(self._expanded_poe1_query_patterns())
        alternatives = set(self._poe1_token_alternatives(token))
        if not alternatives:
            return False
        # 圧縮後の [gb] なども展開して、候補の全パターンが揃っていたらチェックONに戻す。
        return alternatives.issubset(query_patterns)

    def _poe1_any_link_level(self, label):
        match = re.fullmatch(r"Any (\d+) link", (label or "").strip())
        return int(match.group(1)) if match else 0

    def _compress_poe1_any_link_entries(self, entries):
        """Any 3/4/5/6 link は大きいリンク数が小さいリンク数を包含する。"""
        if not entries:
            return []
        level, token = max(entries, key=lambda item: item[0])
        return self._poe1_token_alternatives(token)

    def _poe1_color_sort_key(self, value):
        # 参考サイトの出力に寄せる（例: [gr], [gb]）。
        order = {"g": 0, "r": 1, "b": 2, ".": 3}
        return order.get(value, 99)

    def _poe1_color_class(self, values):
        return "[" + "".join(sorted(set(values), key=self._poe1_color_sort_key)) + "]"

    def _poe1_simple_3link_label(self, label):
        label = (label or "").strip().lower()
        return label if re.fullmatch(r"[rgb]{3}", label) else ""

    def _poe1_majority_and_minority_color(self, label):
        label = self._poe1_simple_3link_label(label)
        if not label:
            return "", ""
        counts = {color: label.count(color) for color in "rgb"}
        majority = next((color for color, count in counts.items() if count == 2), "")
        minority = next((color for color, count in counts.items() if count == 1), "")
        return majority, minority

    def _compress_poe1_link_color_entries(self, entries):
        """Link colors (3L) の選択を参考サイト風に圧縮する。"""
        labels = [(label, token) for label, token in entries if self._poe1_simple_3link_label(label)]
        if len(labels) == 2:
            (label1, token1), (label2, token2) = labels
            maj1, min1 = self._poe1_majority_and_minority_color(label1)
            maj2, min2 = self._poe1_majority_and_minority_color(label2)
            if maj1 and maj2:
                # rrb + rrg → r-r-[gb]|r-[gb]-r|[gb]-r-r
                if maj1 == maj2 and min1 != min2:
                    cls = self._poe1_color_class([min1, min2])
                    return [f"{maj1}-{maj1}-{cls}", f"{maj1}-{cls}-{maj1}", f"{cls}-{maj1}-{maj1}"]
                # rrg + ggr → g-[gr]-r|r-[gr]-g|g-r-g|r-g-r
                if {maj1, min1} == {maj2, min2} and maj1 != maj2:
                    a = maj1
                    b = maj2
                    cls = self._poe1_color_class([a, b])
                    return [f"{b}-{cls}-{a}", f"{a}-{cls}-{b}", f"{b}-{a}-{b}", f"{a}-{b}-{a}"]
        flat = []
        for _label, token in entries:
            flat.extend(self._poe1_token_alternatives(token))
        return self._compress_poe1_link_patterns(flat)

    def _dedupe_poe1_covered_link_patterns(self, patterns):
        """ワイルドカード系リンク表現が包含する具体候補を削る。

        例: rr* の `r-r-|-r-r|r-.-r` は r-r-r を含むので、rrrを同時選択しても追加しない。
        """
        patterns = [p for p in patterns if p]
        covered_by_wildcards = set()
        for pattern in patterns:
            parts = pattern.split("-")
            if len(parts) < 2:
                continue
            wildcard_positions = [i for i, part in enumerate(parts) if part in ("", ".")]
            if not wildcard_positions:
                continue
            concrete_parts = [part for part in parts if part not in ("", ".")]
            if not concrete_parts:
                continue
            for wildcard_color in "rgb":
                expanded = [wildcard_color if part in ("", ".") else part for part in parts]
                covered_by_wildcards.add("-".join(expanded))
        return [pattern for pattern in patterns if pattern not in covered_by_wildcards]

    def _compress_poe1_link_patterns(self, patterns):
        """r-r-b + r-r-g のような同形リンク候補を r-r-[gb] に圧縮する。"""
        remaining = list(patterns)
        compressed = []
        changed = True
        color_re = re.compile(r"^[rgb.]$")

        while changed:
            changed = False
            used = set()
            best_group = None

            for length in sorted({len(p.split("-")) for p in remaining if "-" in p}, reverse=True):
                length_patterns = [(i, p, p.split("-")) for i, p in enumerate(remaining) if len(p.split("-")) == length]
                for pos in reversed(range(length)):
                    groups = {}
                    for i, pattern, parts in length_patterns:
                        if i in used or not all(color_re.fullmatch(part) for part in parts):
                            continue
                        key = tuple(part if idx != pos else "*" for idx, part in enumerate(parts))
                        groups.setdefault(key, []).append((i, parts[pos], parts))
                    for key, entries in groups.items():
                        values = {value for _i, value, _parts in entries}
                        if len(values) >= 2 and len(entries) > 1:
                            best_group = (pos, key, entries)
                            break
                    if best_group:
                        break
                if best_group:
                    break

            if not best_group:
                break

            pos, _key, entries = best_group
            indexes = {i for i, _value, _parts in entries}
            base_parts = list(entries[0][2])
            values = sorted({value for _i, value, _parts in entries}, key=self._poe1_color_sort_key)
            base_parts[pos] = f"[{''.join(values)}]"
            compressed.append("-".join(base_parts))
            remaining = [p for i, p in enumerate(remaining) if i not in indexes]
            changed = True

        return remaining + compressed

    def _regenerate_poe1_query_from_helper_checkboxes(self):
        manual_patterns = [
            pattern for pattern in self._split_query_patterns(self._query_text())
            if not self._is_helper_generated_pattern(pattern)
        ]
        helper_patterns = []
        link_color_entries = []
        any_link_entries = []
        selected_labels = set()
        selected_options = []
        for cb, token, category in getattr(self, "option_checkboxes", []):
            if not cb.isChecked():
                continue
            label = self._poe1_checkbox_label_key(cb)
            selected_labels.add((category, label))
            selected_options.append((label, token, category))
            any_link_level = self._poe1_any_link_level(label) if category == "Any links" else 0
            if any_link_level:
                any_link_entries.append((any_link_level, token))

        max_any_link_level = max((level for level, _token in any_link_entries), default=0)
        any_link_covers_color_links = max_any_link_level >= 3
        for label, token, category in selected_options:
            if category == "Any links" and self._poe1_any_link_level(label):
                continue
            # Any 3+ link は 2L/3L の具体色指定も包含するので、出力には足さない。
            if any_link_covers_color_links and category in ("Link colors (3L)", "Link colors (2L)"):
                continue
            if category == "Link colors (3L)" and self._poe1_simple_3link_label(label):
                link_color_entries.append((label, token))
                continue
            helper_patterns.extend(self._poe1_token_alternatives(token))
        if link_color_entries:
            helper_patterns.extend(self._compress_poe1_link_color_entries(link_color_entries))
        if any_link_entries:
            helper_patterns.extend(self._compress_poe1_any_link_entries(any_link_entries))
        other_links_pattern = self._poe1_other_links_pattern()
        if other_links_pattern:
            helper_patterns.extend(self._poe1_token_alternatives(other_links_pattern))
        helper_patterns = self._dedupe_poe1_covered_link_patterns(helper_patterns)
        helper_patterns = self._compress_poe1_link_patterns(helper_patterns)
        self._last_poe1_other_links_pattern = other_links_pattern
        self._last_poe1_generated_patterns = set(helper_patterns)
        self._last_poe1_selected_labels = selected_labels
        self.query_edit.setPlainText(self._join_query_patterns(manual_patterns + helper_patterns))

    def _is_helper_generated_pattern(self, pattern):
        if not pattern:
            return False
        if pattern in getattr(self, "_last_poe1_generated_patterns", set()):
            return True
        helper_tokens = {token for _cb, token, _category in getattr(self, "option_checkboxes", [])}
        if self.poe_version == POE1:
            if any(self._poe1_pattern_matches_token(pattern, token) for token in helper_tokens):
                return True
            last_other = getattr(self, "_last_poe1_other_links_pattern", "")
            if last_other and self._poe1_pattern_matches_token(pattern, last_other):
                return True
        if pattern in helper_tokens:
            return True
        if pattern == getattr(self, "_last_poe1_other_links_pattern", ""):
            return True
        if pattern in self._all_combined_damage_patterns():
            return True
        if re.fullmatch(r'".*"".*"', pattern):
            return True
        # ORでまとめたヘルパー表現も再生成対象として扱う。
        if pattern.startswith("(") and pattern.endswith(")"):
            inner = pattern[1:-1]
            return any(part in helper_tokens or part in self._all_combined_damage_patterns() for part in self._split_query_patterns(inner))
        return False

    def _strip_helper_generated_patterns(self, query):
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if not self._is_helper_generated_pattern(p)])

    def _selected_helper_tokens_from_checkboxes(self):
        selected = {"mod": [], "base": [], "base_or": [], "other": []}
        for cb, token, category in getattr(self, "option_checkboxes", []):
            if not cb.isChecked():
                continue
            if category in ("共通", "ビルド別"):
                selected["mod"].append(token)
            elif category == self.WEAPON_BASE_AND_CATEGORY:
                selected["base"].append(token)
            elif category == self.WEAPON_BASE_OR_CATEGORY:
                selected["base_or"].append(token)
            else:
                selected["other"].append(token)
        return selected

    def _regenerate_query_from_helper_checkboxes(self):
        poe_version = getattr(self, "poe_version", POE2)
        if poe_version == POE1:
            self._regenerate_poe1_query_from_helper_checkboxes()
            return
        manual_query = self._strip_helper_generated_patterns(self._query_text())
        patterns = self._split_query_patterns(manual_query)
        selected = self._selected_helper_tokens_from_checkboxes()
        base_expr = self._helper_group_expr(selected["base"])
        mod_or_tokens = selected["mod"] + selected["base_or"]
        if base_expr:
            mod_or_expr = self._helper_group_expr(mod_or_tokens)
            if mod_or_expr:
                patterns.append(f'"{mod_or_expr}""{base_expr}"')
            else:
                patterns.append(base_expr)
        else:
            mod_or_expr = self._helper_group_expr(mod_or_tokens)
            if mod_or_expr:
                patterns.append(mod_or_expr)
        patterns.extend(selected["other"])
        other_links_pattern = self._poe1_other_links_pattern() if poe_version == POE1 else ""
        if other_links_pattern:
            patterns.append(other_links_pattern)
        self._last_poe1_other_links_pattern = other_links_pattern
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _regex_option_toggled(self, token, checked):
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            self._regenerate_query_from_helper_checkboxes()
        finally:
            self._syncing = False
        self._editor_changed()
        self._refresh_regex_checkboxes()

    def _refresh_regex_checkboxes(self):
        query = self._query_text()
        if self.poe_version == POE1:
            selected_labels = getattr(self, "_last_poe1_selected_labels", set())
            generated_patterns = getattr(self, "_last_poe1_generated_patterns", set())
            current_patterns = set(self._split_query_patterns(self._query_text()))
            use_label_state = bool(current_patterns) and bool(selected_labels) and generated_patterns.issubset(current_patterns)
            for cb, token, category in getattr(self, "option_checkboxes", []):
                cb.blockSignals(True)
                if use_label_state:
                    cb.setChecked((category, self._poe1_checkbox_label_key(cb)) in selected_labels)
                else:
                    cb.setChecked(self._poe1_query_has_token(token))
                cb.blockSignals(False)
            other_cb = getattr(self, "_poe1_other_links_checkbox", None)
            if other_cb is not None:
                other_cb.blockSignals(True)
                other_cb.setChecked(bool(getattr(self, "_last_poe1_other_links_pattern", "") and self._poe1_query_has_token(self._last_poe1_other_links_pattern)))
                other_cb.blockSignals(False)
            return
        and_base_tokens = self._and_base_tokens_from_query()
        or_base_tokens = self._or_base_tokens_from_query()
        for cb, token, category in getattr(self, "option_checkboxes", []):
            cb.blockSignals(True)
            if category in ("共通", "ビルド別"):
                cb.setChecked(self._has_query_token(token) or token in query)
            elif category == self.WEAPON_BASE_AND_CATEGORY:
                cb.setChecked(token in and_base_tokens)
            elif category == self.WEAPON_BASE_OR_CATEGORY:
                cb.setChecked(token in or_base_tokens)
            else:
                cb.setChecked(self._has_query_token(token))
            cb.blockSignals(False)

    def _enabled_item(self, enabled=True):
        item = self.QTableWidgetItem("")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
        return item

    def _append_preset(self, preset):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, self._enabled_item(bool(preset.get("enabled", True))))
        self.table.setItem(row, 1, self._item(preset.get("name", "")))
        self.table.setItem(row, 2, self._item(preset.get("query", "")))
        if self.table.currentRow() < 0:
            self.table.selectRow(row)

    def _load_presets(self):
        presets = []
        if self.presets_path and os.path.exists(self.presets_path):
            try:
                with open(self.presets_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                presets = data.get("presets", [])
            except Exception as e:
                print(f"[VendorSearchPresetDialog] Failed to load presets: {e}")
        if not presets:
            presets = self._default_presets()
        self.table.setRowCount(0)
        for preset in presets:
            self._append_preset(preset)

    def presets(self):
        result = []
        for row in range(self.table.rowCount()):
            enabled_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            query_item = self.table.item(row, 2)
            name = name_item.text().strip() if name_item else ""
            query = query_item.text().strip() if query_item else ""
            if not name and not query:
                continue
            result.append({
                "enabled": enabled_item.checkState() == Qt.Checked if enabled_item else True,
                "name": name or query,
                "query": query,
            })
        return result

    def _find_over_limit_presets(self, presets):
        return [
            (index + 1, preset.get("name", ""), len(preset.get("query", "")))
            for index, preset in enumerate(presets)
            if len(preset.get("query", "")) > self.MAX_SEARCH_QUERY_LENGTH
        ]

    def _save_presets(self):
        try:
            presets = self.presets()
            over_limit = self._find_over_limit_presets(presets)
            if over_limit:
                details = "\n".join(
                    f"{row}行目: {name or '（名称なし）'}（{length}文字）"
                    for row, name, length in over_limit[:5]
                )
                if len(over_limit) > 5:
                    details += f"\n...ほか{len(over_limit) - 5}件"
                QMessageBox.warning(
                    self,
                    "検索文字列が長すぎます",
                    f"PoE2の検索窓は{self.MAX_SEARCH_QUERY_LENGTH}文字が上限です。\n"
                    "上限を超えるプリセットは正しく貼り付けできないため、保存を中止しました。\n\n"
                    f"{details}",
                )
                return
            data = {"presets": presets}
            with open(self.presets_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._capture_saved_snapshot()
            print(f"[VendorSearchPresetDialog] Presets saved to {self.presets_path}")
        except Exception as e:
            print(f"[VendorSearchPresetDialog] Failed to save presets: {e}")

    def _add_row(self):
        self._append_preset({"name": "新規プリセット", "query": "", "enabled": True})
        self.table.selectRow(self.table.rowCount() - 1)
        self._set_dirty(True)

    def _delete_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.table.removeRow(row)
        self._set_dirty(True)

    def _move_selected(self, delta):
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.table.rowCount():
            return
        values = []
        for col in range(3):
            item = self.table.takeItem(row, col)
            values.append(item)
        self.table.removeRow(row)
        self.table.insertRow(target)
        for col, item in enumerate(values):
            self.table.setItem(target, col, item)
        self.table.selectRow(target)
        self._set_dirty(True)

    def _get_edge(self, pos):
        m = self._EDGE_MARGIN
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        edge = ""
        if y < m: edge += "t"
        elif y > h - m: edge += "b"
        if x < m: edge += "l"
        elif x > w - m: edge += "r"
        return edge

    def _edge_cursor(self, edge):
        if edge in ("t", "b"): return Qt.SizeVerCursor
        if edge in ("l", "r"): return Qt.SizeHorCursor
        if edge in ("tl", "br"): return Qt.SizeFDiagCursor
        if edge in ("tr", "bl"): return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        edge = self._get_edge(event.position().toPoint())
        if edge:
            self._resize_edge = edge
            self._resize_start = event.globalPosition().toPoint()
            self._resize_geo = self.geometry()
            event.accept()
        elif event.position().y() < 32:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._resize_edge and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_start
            geo = QRect(self._resize_geo)
            if "r" in self._resize_edge: geo.setRight(geo.right() + delta.x())
            if "b" in self._resize_edge: geo.setBottom(geo.bottom() + delta.y())
            if "l" in self._resize_edge: geo.setLeft(geo.left() + delta.x())
            if "t" in self._resize_edge: geo.setTop(geo.top() + delta.y())
            if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
                self.setGeometry(geo)
            event.accept()
        elif self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            edge = self._get_edge(event.position().toPoint())
            self.setCursor(self._edge_cursor(edge))

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self.setCursor(Qt.ArrowCursor)

    def _save_and_close(self):
        self._save_presets()
        self.hide()

    def closeEvent(self, event):
        if not self._has_unsaved_changes():
            event.accept()
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("未保存の変更")
        msg.setText("保存していない変更があります。保存しますか？")
        msg.setIcon(QMessageBox.Question)
        save_button = msg.addButton("保存", QMessageBox.AcceptRole)
        discard_button = msg.addButton("保存せずに閉じる", QMessageBox.DestructiveRole)
        cancel_button = msg.addButton("キャンセル", QMessageBox.RejectRole)
        msg.setDefaultButton(save_button)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == save_button:
            self._save_presets()
            event.accept()
        elif clicked == discard_button:
            self._syncing = True
            try:
                self._load_presets()
            finally:
                self._syncing = False
            self._load_selected_to_editor()
            self._capture_saved_snapshot()
            event.accept()
        else:
            event.ignore()


class MainWindow(QMainWindow):
    # Qt may call an overridden showEvent from QMainWindow.__init__ before
    # this class' __init__ body can initialize instance attributes.
    _initial_positioned = False
    _pending_initial_map_auto_open = False
    _main_window_initialized = False

    POELAB_ZONE_TYPES = {
        "act4_area3": "normal",
        "act8_area2": "cruel",
        "act10_area8": "merciless",
    }

    # ホットキーイベントをメインスレッドで処理するためのシグナル
    hotkey_signal = Signal(str)
    poelab_url_resolved = Signal(str)
    poelab_url_failed = Signal(str)

    def __init__(self):
        super().__init__()

        # Qt can deliver showEvent while startup dialogs are running.  Keep
        # showEvent side-effect free until every widget/state it uses exists.
        self._main_window_initialized = False

        # 設定読み込み
        self.config = ConfigManager.load_config()
        self.setWindowTitle(f"ぽえなび [{get_poe_label(self.config.get('poe_version', POE1))}]")

        # config の display_monitor で指定されたモニターの右端に縦長で配置
        from PySide6.QtWidgets import QApplication
        _config = self.config
        self._display_monitor_index = _config.get("display_monitor", 0)
        self._initial_positioned = False
        # Startup update dialogs can cause Qt to deliver showEvent while
        # __init__ is still running.  Initialize every flag read by
        # showEvent before the update gate can display a dialog.
        self._pending_initial_map_auto_open = False
        self.resize(420, 1200)  # 仮サイズ、showEvent で実際に配置

        # アプリアイコン設定
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "icon.ico")
        if not os.path.exists(icon_path):
            # PyInstaller _MEIPASS対応
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
            icon_path = os.path.join(base, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self._apply_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setStyleSheet(Styles.MAIN_WINDOW)
        
        # 設定読み込み
        self.config = ConfigManager.load_config()
        self.update_controller = UpdateController(self)
        self._update_progress_dialog = None
        if not self._run_startup_update_gate():
            QTimer.singleShot(0, QApplication.instance().quit)
            return
        self._connect_update_controller()
        if not self._ensure_poe_version_selected():
            from PySide6.QtWidgets import QApplication
            QTimer.singleShot(0, QApplication.instance().quit)
            return
        self.poe_version = self.config.get("poe_version", POE1)
        
        self.drag_position = None
        self.resize_edge = None  # None or combination of 'left','right','top','bottom'
        self.resize_start_geo = None
        self.resize_start_pos = None
        self.window_locked = self.config.get("window_locked", False)
        self.EDGE_MARGIN = 14
        
        # エリア訪問回数カウンター（街エリアはカウントしない）— zone_id基準
        self.zone_visit_counts = {}
        # PoE2 進行フラグ（ログ検知ベースの高度制御用）
        self.progress_flags = set()
        self._restore_progress_flags()
        self.interlude_ready = set()
        # 起動時の復元中はvisitカウントしない
        self._restoring = False
        # 起動時復元で自動表示されるマップは、メインウィンドウ配置完了後に開く
        # 訪問回数の手動オーバーライド（None=自動, 1 or 2=固定）— ゾーン移動でリセット
        self.visit_override = None
        # Lab中フラグ（志す者の広場→Lab内エリア→街帰還を追跡）
        self._in_lab = False
        self._lab_zone_id = None  # Lab入口の志す者の広場のzone_id
        
        # ガイド折りたたみ状態（初回はTrue、以降はconfig保持）
        self.guide_expanded = self.config.get("guide_expanded", True)
        # セクション個別折りたたみ状態（保存しない — 毎回展開）
        self.zone_header_expanded = True
        self.guide_text_expanded = True
        self.map_section_expanded = True
        # ガイドフォントサイズ
        self.guide_font_size = self.config.get("guide_font_size", 18)
        # タイマーサイズ
        configured_timer_size = self.config.get("timer_size", "large")
        self.timer_size = self._effective_timer_size(configured_timer_size)
        self.TIMER_SIZES = {
            "large":  {"main": 96, "ms": 32, "container_pad": 20},
            "medium": {"main": 64, "ms": 22, "container_pad": 14},
            "small":  {"main": 42, "ms": 16, "container_pad": 8},
        }
        # Part 2モード
        self.part2_mode = self.config.get("part2_mode", False)
        self.part2_level_threshold = self.config.get("part2_level_threshold", 39)
        self.part2_only_zones = self.config.get("part2_only_zones", [
            "冒涜された広間", "The Desecrated Chambers",
            "谷底への道", "The Descent",
            "腐った核", "The Rotting Core",
            "有毒な排水路", "The Toxic Conduits",
            "穀物倉庫", "The Grain Gate",
            "帝国の穀倉地帯", "The Imperial Fields",
            "ルナリスの中央広場", "The Lunaris Concourse",
            "ソラリスの中央広場", "The Solaris Concourse",
            "荒廃した広場", "The Ravaged Square",
            "運河", "The Canals",
            "餌場", "The Feeding Trough",
            "カルイの要塞", "The Karui Fortress",
            "シャヴロンの塔", "Shavronne's Tower",
            "ブラインキングの岩礁", "The Brine King's Reef",
            "マリガロの聖域", "Maligaro's Sanctum",
            "焼け野原", "The Ashen Fields",
            "土手道", "The Causeway",
            "ヴァールの街", "The Vaal City",
            "堕落の寺院 -第一層-", "The Temple of Decay Level 1",
            "サーンの城壁", "The Sarn Ramparts",
            "ドードリの汚水槽", "Doedre's Cesspool",
            "波止場", "The Quay",
            "港の橋", "The Harbour Bridge",
            "浴場", "The Bath House",
            "ヴァスティリ砂漠", "The Vastiri Desert",
            "オアシス", "The Oasis",
            "山麓", "The Foothills",
            "沸き立つ湖", "The Boiling Lake",
            "坑道", "The Tunnel",
            "採石場", "The Quarry",
            "精錬所", "The Refinery",
        ])
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.start_time = 0.0
        self.accumulated_time = 0.0
        self.is_running = False
        
        # ラップタイム用
        self.poe_version = self.config.get("poe_version", POE1)
        self.lap_labels = get_lap_labels(self.poe_version)
        self.lap_times = [None] * len(self.lap_labels)
        self.lap_record_order = []
        self.segment_recorder = SegmentRecorder()
        self.current_act = 1
        self.current_zone_act = 1  # 現在エリアから判定したAct（ジェム取得表示の自動追従用）
        self.gem_tracker_popup = None
        self._last_search_target_hwnd = None
        
        self.setup_ui()
        self.map_thumbnail.auto_open = self.config.get("auto_open_map", False)
        self.map_thumbnail.auto_position = self.config.get("auto_position_map", True)
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)
        self._apply_bg_opacity(self.config.get("window_opacity", 100))
        self._apply_text_opacity(self.config.get("text_opacity", 100))
        
        # レベルガイド状態
        self.player_level = 1
        self.current_zone = ""
        self._current_zone_id = None
        self._current_zone_name = ""
        self._current_area_note = ""
        self._current_poelab_type = None
        with measure("startup data load"):
            zone_master_data = load_zone_master_data()
            self.zone_data_by_version = zone_master_data["zone_data_by_version"]
            self.town_zones_by_version = zone_master_data["town_zones_by_version"]
            self.zone_data = self.zone_data_by_version.get(self.poe_version, {})
            self.guide_data = load_guide_data(self.poe_version)
        self.mini_navi_overlay = MiniNaviOverlay(self)
        self.poelab_url_resolved.connect(self._open_resolved_poelab_url)
        self.poelab_url_failed.connect(self._handle_poelab_url_error)
        
        # monster_levels.json 読み込み
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            base_dir = exe_dir
            if not os.path.exists(os.path.join(exe_dir, "monster_levels.json")):
                base_dir = getattr(sys, '_MEIPASS', exe_dir)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        monster_levels_path = os.path.join(base_dir, "monster_levels.json")
        self.monster_levels = {}
        if os.path.exists(monster_levels_path):
            try:
                with open(monster_levels_path, 'r', encoding='utf-8') as f:
                    self.monster_levels = json.load(f)
                print(f"Loaded monster_levels.json: {len(self.monster_levels)} entries")
            except Exception as e:
                print(f"Failed to load monster_levels.json: {e}")
        
        # ログ監視
        if fill_missing_client_log_paths(self.config):
            ConfigManager.save_config(self.config)

        client_log_paths = self.config.get("client_log_paths", {})
        current_log_path = client_log_paths.get(self.poe_version, "")
        self.log_watcher = LogWatcher(
            log_path=current_log_path,
            parent=self
        )
        self.log_watcher.set_poe_version(self.poe_version)
        self.log_watcher.zone_entered.connect(self.on_zone_entered)
        self.log_watcher.level_up.connect(self.on_level_up)
        self.log_watcher.kitava_defeated.connect(self.on_kitava_defeated)
        self.log_watcher.act10_cleared.connect(self.on_act10_cleared)
        self.log_watcher.act4_cleared.connect(self.on_poe2_act4_cleared)
        self.log_watcher.progress_flag_detected.connect(self.set_progress_flag)
        
        # ホットキー初期化
        self.hotkey_signal.connect(self.handle_hotkey)
        self.keyboard_listener = None
        self.register_hotkeys()
        
        # ログ監視開始（復元中はvisitカウントしない）
        if current_log_path:
            self._restoring = True
            self.log_watcher.start()
            self._restoring = False
        
        # タイマー状態復元
        self._restore_timer_state()
        
        # エリアメモ導入案内（全モード共通で一度だけ）
        self._show_area_note_migration_notice_once()

        # 初回起動チェック（ポップアップ + ガイドエリア案内）
        self._check_first_run()
        
        # 全ウィジェットのマウスイベントを横取りしてリサイズ処理
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        self._ef_resize_active = False
        self._ef_resize_edge = None
        self._ef_resize_start_geo = None
        self._ef_resize_start_pos = None
        self._main_window_initialized = True

    def _connect_update_controller(self):
        """Connect handlers used after the startup update gate."""
        self.update_controller.check_finished.connect(self._on_update_check_finished)
        self.update_controller.check_failed.connect(self._on_update_check_failed)
        self.update_controller.download_progress.connect(self._on_update_download_progress)
        self.update_controller.download_ready.connect(self._on_update_download_ready)
        self.update_controller.download_failed.connect(self._on_update_download_failed)
        self.update_controller.download_cancelled.connect(self._on_update_download_cancelled)

    def _run_startup_update_gate(self):
        """Finish the startup update decision before showing setup dialogs."""
        check_loop = QEventLoop()
        result = {"release": None, "error": None}

        def on_finished(release, _manual):
            result["release"] = release
            check_loop.quit()

        def on_failed(message, _manual):
            result["error"] = message
            check_loop.quit()

        self.update_controller.check_finished.connect(on_finished)
        self.update_controller.check_failed.connect(on_failed)
        QTimer.singleShot(0, lambda: self.update_controller.check(False))
        check_loop.exec()
        self.update_controller.check_finished.disconnect(on_finished)
        self.update_controller.check_failed.disconnect(on_failed)

        release = result["release"]
        if release is None:
            return True
        if self.config.get("notified_update_version") == release.version:
            return True

        self.config["notified_update_version"] = release.version
        ConfigManager.save_config(self.config)
        supported = getattr(sys, "frozen", False) and sys.platform == "win32"
        dialog = UpdateAvailableDialog(release, supported, self)
        if not dialog.exec():
            return True
        if not supported:
            QDesktopServices.openUrl(QUrl(release.page_url))
            return True

        progress = UpdateProgressDialog(release.version, self)
        progress.cancel_requested.connect(self.update_controller.cancel_download)
        download_loop = QEventLoop()
        download_result = {"archive": None, "error": None, "cancelled": False}

        def on_progress(done, total):
            progress.set_progress(done, total)

        def on_ready(archive, _release):
            download_result["archive"] = archive
            download_loop.quit()

        def on_download_failed(message):
            download_result["error"] = message
            download_loop.quit()

        def on_cancelled():
            download_result["cancelled"] = True
            download_loop.quit()

        self.update_controller.download_progress.connect(on_progress)
        self.update_controller.download_ready.connect(on_ready)
        self.update_controller.download_failed.connect(on_download_failed)
        self.update_controller.download_cancelled.connect(on_cancelled)
        progress.show()
        QTimer.singleShot(0, lambda: self.update_controller.download(release))
        download_loop.exec()
        progress.close()
        self.update_controller.download_progress.disconnect(on_progress)
        self.update_controller.download_ready.disconnect(on_ready)
        self.update_controller.download_failed.disconnect(on_download_failed)
        self.update_controller.download_cancelled.disconnect(on_cancelled)

        if download_result["cancelled"]:
            return True
        if download_result["error"]:
            QMessageBox.warning(
                self,
                "アップデート",
                f"更新をダウンロードできませんでした。\n{download_result['error']}",
            )
            return True

        answer = QMessageBox.question(
            self,
            "アップデートを適用",
            f"v{release.version} の検証が完了しました。\n"
            "ぽえなびを終了して更新しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return True
        try:
            self.update_controller.launch_updater(download_result["archive"])
        except Exception as exc:
            QMessageBox.critical(self, "アップデート", str(exc))
            return True
        return False
        
    def _ensure_poe_version_selected(self):
        mode = self.config.get("poe_version_mode", "ask")
        if mode in (POE1, POE2):
            self.config["poe_version"] = mode
            return self._ensure_guide_detail_level_selected_if_needed()

        dialog = PoeVersionSelectionDialog(self, self.config.get("poe_version", POE1))
        if dialog.exec():
            self.config["poe_version"] = dialog.selected_version
            ConfigManager.save_config(self.config)
            return self._ensure_guide_detail_level_selected_if_needed()
        return False

    def _ensure_guide_detail_level_selected_if_needed(self):
        """PoE2選択後、初回だけガイド表示レベルを選ばせる。"""
        if self.config.get("poe_version") != POE2:
            return True
        if self.config.get("guide_detail_level_selected"):
            return True

        dialog = GuideDetailLevelSelectionDialog(self, self.config.get("guide_detail_level", "beginner"))
        if dialog.exec():
            self.config["guide_detail_level"] = dialog.selected_level
            self.config["guide_detail_level_selected"] = True
            ConfigManager.save_config(self.config)
            return True
        return False

    def _check_for_updates(self, manual=False):
        """GitHub Releasesから最新バージョンを確認する。"""
        self.update_controller.check(manual)

    def _on_update_check_finished(self, release, manual):
        if release is None:
            if manual:
                QMessageBox.information(self, "アップデート", "最新バージョンです。")
            return
        if not manual and self.config.get("notified_update_version") == release.version:
            return
        self._show_update_available(release)

    def _on_update_check_failed(self, message, manual):
        if manual:
            QMessageBox.warning(
                self,
                "アップデート",
                f"更新を確認できませんでした。\n{message}",
            )

    def _show_update_available(self, release):
        self.config["notified_update_version"] = release.version
        ConfigManager.save_config(self.config)
        supported = getattr(sys, "frozen", False) and sys.platform == "win32"
        dialog = UpdateAvailableDialog(release, supported, self)
        if not dialog.exec():
            return
        if not supported:
            QDesktopServices.openUrl(QUrl(release.page_url))
            return
        self._start_update_download(release)

    def _start_update_download(self, release):
        cached = self.update_controller.ready_archive(release.version)
        if cached is not None:
            self._on_update_download_ready(cached, release)
            return
        self._update_progress_dialog = UpdateProgressDialog(release.version, self)
        self._update_progress_dialog.cancel_requested.connect(
            self.update_controller.cancel_download
        )
        self.update_controller.download(release)
        self._update_progress_dialog.show()

    def _on_update_download_progress(self, done, total):
        if self._update_progress_dialog:
            self._update_progress_dialog.set_progress(done, total)

    def _on_update_download_cancelled(self):
        if self._update_progress_dialog:
            self._update_progress_dialog.reject()
            self._update_progress_dialog = None

    def _on_update_download_failed(self, message):
        self._on_update_download_cancelled()
        QMessageBox.warning(
            self,
            "アップデート",
            f"更新をダウンロードできませんでした。\n{message}",
        )

    def _on_update_download_ready(self, archive, release):
        if self._update_progress_dialog:
            self._update_progress_dialog.accept()
            self._update_progress_dialog = None
        answer = QMessageBox.question(
            self,
            "アップデートを適用",
            f"v{release.version} の検証が完了しました。\n"
            "ぽえなびを終了して更新しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.update_controller.launch_updater(archive)
        except Exception as exc:
            QMessageBox.critical(self, "アップデート", str(exc))
            return
        QApplication.instance().quit()
    
    def _check_first_run(self):
        """現在のPoEバージョンに対応するログファイル設定案内"""
        client_log_paths = self.config.get("client_log_paths", {})
        log_path = client_log_paths.get(self.poe_version, "")
        is_first_run = not self.config.get("setup_completed", False)
        poe_label = get_poe_label(self.poe_version)

        if not log_path:
            # 初回または、選択中バージョンのログファイルが未設定なら案内を出す
            msg = QMessageBox(self)
            msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
            msg.setWindowTitle("⚙️ ログファイル設定")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(
                "ぽえなびをご利用いただきありがとうございます！\n\n"
                f"現在は {poe_label} モードです。対応するログファイル（Client.txt）を設定してください。\n\n"
                "1. 右クリックメニューの「設定」、または右側中央の ⚙️ ボタンから設定画面を開く\n"
                "2. 「基本設定」タブで、現在のモードに対応するログファイル欄を設定\n"
                f"   - {poe_label}ログファイル\n"
                "3. 通常のパス例（これはPoE1 Steam版の例です）：\n"
                "    C:\\Program Files (x86)\\Steam\\steamapps\n"
                "    \\common\\Path of Exile\\logs\\Client.txt\n\n"
                "⚠️ 対応するログファイルが未設定だと、エリア検知が動作しません。"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            # setup_completedフラグはログパス設定時に立てる

            self.guide_text_label.setText(
                '<div style="padding: 15px;">'
                '<span style="font-size: 20px;">⚙️</span>'
                f'<span style="font-size: 15px; color: #ffc832; font-weight: bold;"> {poe_label}ログファイル（Client.txt）が未設定です</span><br><br>'
                '<span style="font-size: 13px; color: #cccccc;">'
                '右クリック →「設定」→「基本設定」タブから<br>'
                f'{poe_label}ログファイル を設定してください</span><br><br>'
                '<span style="font-size: 12px; color: #999999;">'
                '通常のパス例（これはPoE1 Steam版の例です）：<br>'
                '<span style="color: #b0ffb0;">C:\\Program Files (x86)\\Steam\\steamapps<br>'
                '\\common\\Path of Exile\\logs\\Client.txt</span></span>'
                '</div>'
            )

    def _show_area_note_migration_notice_once(self):
        """公式ガイド編集からエリアメモへの移行案内を一度だけ表示する。"""
        flag = "area_note_migration_notice_shown"
        if self.config.get(flag, False):
            return

        msg = QMessageBox(self)
        msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
        msg.setWindowTitle("📝 エリアメモ機能について")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "今回のバージョンから、各エリアのガイドデータは\n"
            "編集できない仕様に変更しました。\n"
            "（PoENaviの自動アップデート機能を正しく動作させるためです）\n"
            "その代わり、各エリアにエリアメモを追加できる\n"
            "「エリアメモ」機能を実装しました。\n\n"
            "大変お手数ですが、以前のガイドを編集していた方は、\n"
            "旧PoENaviフォルダのJSONファイルから、\n"
            "必要な内容を各エリアのエリアメモへコピーしてください。\n\n"
            "今後は公式ガイドとエリアメモを分けて保存するため、\n"
            "次回以降のアップデートでエリアメモが失われることはありません。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

        self.config[flag] = True
        ConfigManager.save_config(self.config)

    def _show_route_selection_dialog(self):
        """ルート選択ダイアログを表示して設定を保存"""
        dialog = RouteSelectionDialog(self, self.config)
        if dialog.exec():
            routes = dialog.get_routes()
            self.config.update(routes)
            self.config["poe1_route_selected"] = True
            ConfigManager.save_config(self.config)

    def eventFilter(self, obj, event):
        """本体ウィンドウ内のマウスイベントだけで端のリサイズを処理する。"""
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            # グローバル座標 → ウィンドウ座標
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                if self.window_locked or not self._is_main_window_widget(obj):
                    return False
                gpos = event.globalPosition().toPoint()
                edges = self._global_detect_edge(gpos)
                if edges:
                    self._ef_resize_active = True
                    self._ef_resize_edge = edges
                    self._ef_resize_start_geo = self.geometry()
                    self._ef_resize_start_pos = gpos
                    return True  # イベント消費
            
            elif event.type() == QEvent.Type.MouseMove and self._ef_resize_active:
                gpos = event.globalPosition().toPoint()
                geo = self._ef_resize_start_geo
                dx = gpos.x() - self._ef_resize_start_pos.x()
                dy = gpos.y() - self._ef_resize_start_pos.y()
                x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
                min_w, min_h = 300, getattr(self, 'MIN_HEIGHT', 400)
                
                if 'right' in self._ef_resize_edge:
                    w = max(min_w, geo.width() + dx)
                if 'bottom' in self._ef_resize_edge:
                    h = max(min_h, geo.height() + dy)
                if 'left' in self._ef_resize_edge:
                    new_w = max(min_w, geo.width() - dx)
                    x = geo.x() + geo.width() - new_w
                    w = new_w
                if 'top' in self._ef_resize_edge:
                    new_h = max(min_h, geo.height() - dy)
                    y = geo.y() + geo.height() - new_h
                    h = new_h
                
                self.setGeometry(x, y, w, h)
                return True
            
            elif event.type() == QEvent.Type.MouseButtonRelease and self._ef_resize_active:
                self._ef_resize_active = False
                self._ef_resize_edge = None
                return True
        
        return super().eventFilter(obj, event)

    def _is_main_window_widget(self, obj):
        """イベント元が本体または本体配下のウィジェットか判定する。"""
        widget = obj if isinstance(obj, QWidget) else None
        while widget is not None:
            if widget is self:
                return True
            widget = widget.parentWidget()
        return False
    
    def _global_detect_edge(self, gpos):
        """グローバル座標からリサイズ方向を検出"""
        geo = self.frameGeometry()
        if not geo.contains(gpos):
            return None
        m = self.EDGE_MARGIN
        edges = []
        if abs(gpos.x() - geo.left()) <= m:
            edges.append('left')
        elif abs(gpos.x() - geo.right()) <= m:
            edges.append('right')
        if abs(gpos.y() - geo.top()) <= m:
            edges.append('top')
        elif abs(gpos.y() - geo.bottom()) <= m:
            edges.append('bottom')
        return edges if edges else None

    def load_custom_font(self):
        # フォント読み込み
        import os
        from PySide6.QtGui import QFontDatabase
        
        font_path = os.path.join("assets", "fonts", "LcdSolid-VPzB.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    return families[0]
        return None

    def _apply_bg_opacity(self, opacity_pct: int):
        """背景の透過率を適用（テキストは変えず背景のアルファ値のみ変更）"""
        alpha = int(opacity_pct / 100.0 * 255)
        # メイン背景
        self.centralWidget().setStyleSheet(
            f"#centralWidget {{ background-color: rgba(0, 0, 0, {alpha}); border-radius: 10px; }}"
        )
        # ガイドテキストフレーム
        guide_alpha = int(alpha * 0.63)  # 元: 160/255 ≈ 63%の比率を維持
        if hasattr(self, 'guide_text_frame'):
            self.guide_text_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(0, 0, 0, {guide_alpha});
                    border: 1px solid rgba(176, 255, 123, 0.2);
                    border-radius: 6px;
                }}
            """)
        # ガイドコンテナ
        container_alpha = int(alpha * 0.55)  # 元: 140/255
        if hasattr(self, 'guide_container'):
            self.guide_container.setStyleSheet(
                f"#guideContainer {{ background-color: rgba(20, 30, 20, {container_alpha}); border-radius: 6px; }}"
            )

    def _apply_text_opacity(self, opacity_pct: int):
        """ガイドテキストエリア全体の透過率を適用（QGraphicsOpacityEffect）"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        opacity = opacity_pct / 100.0
        for attr in ('guide_container', 'timer_container', 'timer_toggle_btn', 'guide_toggle_btn'):
            w = getattr(self, attr, None)
            if w:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(opacity)
                w.setGraphicsEffect(effect)

    def _effective_timer_size(self, timer_size=None):
        """表示に使う実サイズを返す（off時は直前サイズを保持）"""
        timer_size = timer_size or self.config.get("timer_size", "large")
        if timer_size == "off":
            return self.config.get("timer_size_before_off", "medium")
        return timer_size

    def _set_timer_expanded(self, expanded: bool):
        """タイマー本体と操作ボタンの表示状態をまとめて切り替える"""
        self.timer_expanded = expanded
        self.timer_content.setVisible(expanded)
        self.start_btn.setVisible(expanded)
        self.stop_btn.setVisible(expanded)
        self.reset_btn.setVisible(expanded)
        self.timer_toggle_btn.setText("▼ タイマー" if expanded else "▶ タイマー")

    def _apply_timer_size(self):
        """タイマーの表示サイズを適用する"""
        sizes = self.TIMER_SIZES.get(self.timer_size, self.TIMER_SIZES["large"])
        main_px = sizes["main"]
        ms_px = sizes["ms"]
        pad = sizes["container_pad"]
        
        base_style = Styles.TIMER_LABEL
        # フォントサイズを差し替え
        base_style = re.sub(r"font-size:.*?;", f"font-size: {main_px}px;", base_style)
        if self._custom_font_family:
            base_style = re.sub(r"font-family:.*?;", f"font-family: '{self._custom_font_family}';", base_style)
        
        ms_style = Styles.TIMER_LABEL
        ms_style = re.sub(r"font-size:.*?;", f"font-size: {ms_px}px;", ms_style)
        if self._custom_font_family:
            ms_style = re.sub(r"font-family:.*?;", f"font-family: '{self._custom_font_family}';", ms_style)
        
        self.lbl_hours.setStyleSheet(base_style)
        self.lbl_c1.setStyleSheet(base_style)
        self.lbl_mins.setStyleSheet(base_style)
        self.lbl_c2.setStyleSheet(base_style)
        self.lbl_secs.setStyleSheet(base_style)
        self.lbl_ms.setStyleSheet(ms_style)
        
        # コンテナのパディング調整
        self.timer_container.layout().setContentsMargins(pad, pad, pad, pad // 2)

    def setup_ui(self):
        from PySide6.QtWidgets import QSizePolicy
        
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet(f"#centralWidget {{ background-color: {Styles.BACKGROUND_COLOR}; border-radius: 10px; }}")
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === タイトルバー（最小化・閉じる） ===
        title_bar = QHBoxLayout()
        # リサイズ用の端つかみ範囲（EDGE_MARGIN=14）は維持しつつ、
        # 最小化/閉じるボタンが上端・右端の判定に被らないよう少し内側へ逃がす。
        title_bar.setContentsMargins(5, 16, 16, 0)
        
        # クリックスルー状態表示
        self.click_through = False
        self.click_through_label = QLabel("")
        self._update_click_through_label()
        title_bar.addWidget(self.click_through_label)
        title_bar.addStretch()
        
        btn_style = f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 14px; font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.15); border-radius: 3px; }}
        """
        close_btn_style = f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 14px; font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ background: rgba(255,60,60,0.8); border-radius: 3px; color: #ffffff; }}
        """
        
        minimize_btn = QPushButton("─")
        minimize_btn.setFixedSize(30, 22)
        minimize_btn.setStyleSheet(btn_style)
        minimize_btn.setToolTip("最小化（みになび表示中は本体だけ隠します）")
        minimize_btn.clicked.connect(self.minimize_main_window)
        title_bar.addWidget(minimize_btn)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 22)
        close_btn.setStyleSheet(close_btn_style)
        close_btn.setToolTip("閉じる")
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(close_btn)
        
        layout.addLayout(title_bar)
        
        # === タイマー折りたたみトグル ===
        self.timer_expanded = self.config.get("timer_expanded", True)
        if self.config.get("timer_size") == "off":
            self.timer_expanded = False
        
        self.timer_toggle_btn = QPushButton("▼ タイマー" if self.timer_expanded else "▶ タイマー")
        self.timer_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 12px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.timer_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.timer_toggle_btn.clicked.connect(self.toggle_timer)
        self.timer_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(self.timer_toggle_btn)
        
        # === タイマー部分（固定高さコンテナ） ===
        self.timer_container = QWidget()
        timer_container_layout = QVBoxLayout(self.timer_container)
        timer_container_layout.setAlignment(Qt.AlignCenter)
        timer_container_layout.setContentsMargins(20, 20, 20, 10)
        
        # タイマー内の折りたたみ対象部分
        self.timer_content = QWidget()
        timer_content_layout = QVBoxLayout(self.timer_content)
        timer_content_layout.setAlignment(Qt.AlignCenter)
        timer_content_layout.setContentsMargins(0, 0, 0, 0)
        timer_content_layout.setSpacing(0)
        
        # タイマー表示 (分割)
        # ラベル分割: Hours, Colon1, Minutes, Colon2, Seconds, Milliseconds
        # 幅固定フォントではない場合のガタツキ防止策として、各数字パーツを別ラベルにする
        
        timer_layout = QHBoxLayout()
        timer_layout.setSpacing(0)
        timer_layout.setAlignment(Qt.AlignCenter)
        
        # 部品作成ヘルパー
        def create_part(text, object_name):
            lbl = QLabel(text)
            lbl.setObjectName(object_name)
            lbl.setAlignment(Qt.AlignCenter)
            return lbl
            
        self.lbl_hours = create_part("00", "time_part")
        self.lbl_c1    = create_part(":",  "colon_part")
        self.lbl_mins  = create_part("00", "time_part")
        self.lbl_c2    = create_part(":",  "colon_part")
        self.lbl_secs  = create_part("00", "time_part")
        self.lbl_ms    = create_part(".00", "ms_part") # ドット込み
        
        # フォントサイズ調整用
        # ms_partだけ小さくするスタイルは別途適用
        
        timer_layout.addWidget(self.lbl_hours)
        timer_layout.addWidget(self.lbl_c1)
        timer_layout.addWidget(self.lbl_mins)
        timer_layout.addWidget(self.lbl_c2)
        timer_layout.addWidget(self.lbl_secs)
        timer_layout.addWidget(self.lbl_ms) # Millisecondsは左詰め気味の方が良いかもしれないが一旦Center
        
        # 既存の layout.addWidget(self.timer_label) を置き換え
        timer_content_layout.addLayout(timer_layout)

        self.segment_summary_label = QLabel()
        self.segment_summary_label.setAlignment(Qt.AlignCenter)
        self.segment_summary_label.setWordWrap(True)
        self.segment_summary_label.setStyleSheet(
            f"color: {Styles.TEXT_COLOR}; font-size: 10px; padding: 2px 0;"
        )

        # フォント読み込みと適用
        self._custom_font_family = self.load_custom_font()
        print(f"Loaded font family: {self._custom_font_family}")
        
        # タイマーサイズ適用
        self._apply_timer_size()
        
        # === ラップタイム折りたたみトグル ===
        self.lap_expanded = self.config.get("lap_expanded", True)
        
        self.lap_toggle_btn = QPushButton("▼ ラップタイム" if self.lap_expanded else "▶ ラップタイム")
        self.lap_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.lap_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.lap_toggle_btn.clicked.connect(self.toggle_lap)
        self.lap_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        timer_content_layout.addSpacing(10)
        
        # ラップタイム行：トグルボタン + 自動/手動ボタン
        lap_header_layout = QHBoxLayout()
        lap_header_layout.setContentsMargins(0, 0, 0, 0)
        lap_header_layout.setSpacing(8)
        lap_header_layout.addWidget(self.lap_toggle_btn)
        
        self.auto_lap = self.config.get("auto_lap", True)
        self.auto_lap_btn = QPushButton("自動" if self.auto_lap else "手動")
        self.auto_lap_btn.setStyleSheet(self._auto_lap_btn_style())
        self.auto_lap_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.auto_lap_btn.clicked.connect(self.toggle_auto_lap)
        self.auto_lap_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lap_header_layout.addWidget(self.auto_lap_btn)
        lap_header_layout.addStretch()
        timer_content_layout.addLayout(lap_header_layout)
        
        # ラップタイムリスト（折りたたみ対象）
        self.lap_content = QWidget()
        self.lap_content_layout = QVBoxLayout(self.lap_content)
        self.lap_content_layout.setContentsMargins(0, 0, 0, 0)
        self.lap_content_layout.setSpacing(0)
        self.lap_label_widgets = []
        self._rebuild_lap_ui()
        
        timer_content_layout.addWidget(self.lap_content)
        self.lap_content.setVisible(self.lap_expanded)
        
        self.update_lap_display()
        
        # timer_contentをtimer_containerに追加
        timer_container_layout.addWidget(self.timer_content)
        self.timer_content.setVisible(self.timer_expanded)
        
        # 操作ボタン（レベルガイドより上に配置）
        timer_container_layout.addSpacing(10)

        # 操作ボタン
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setAlignment(Qt.AlignCenter)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet(Styles.BUTTON)
        self.start_btn.clicked.connect(self.start_timer)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(Styles.BUTTON)
        self.stop_btn.clicked.connect(self.stop_timer)
        button_layout.addWidget(self.stop_btn)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setStyleSheet(Styles.BUTTON)
        self.reset_btn.clicked.connect(self.reset_timer)
        button_layout.addWidget(self.reset_btn)
        
        # タイマー折りたたみ時はボタンも隠す
        if not self.timer_expanded:
            self.start_btn.setVisible(False)
            self.stop_btn.setVisible(False)
            self.reset_btn.setVisible(False)
        
        button_layout.addStretch()
        
        # Act 1-5 / Act 6-10 切替ボタン（ボタン行に配置）
        self.part2_btn = QPushButton("Act 6-10" if self.part2_mode else "Act 1-5")
        self.part2_btn.setStyleSheet(self._part2_btn_style())
        self.part2_btn.setFixedHeight(22)
        self.part2_btn.clicked.connect(self.toggle_part2)
        self.part2_btn.setVisible(self.poe_version == POE1)
        button_layout.addWidget(self.part2_btn)
        
        # 訪問回数 手動切替ボタン（ボタン行に配置）
        self.visit_btn = QPushButton("自動")
        self.visit_btn.setStyleSheet(self._visit_btn_style())
        self.visit_btn.setFixedHeight(22)
        self.visit_btn.clicked.connect(self.toggle_visit_override)
        button_layout.addWidget(self.visit_btn)
        
        self.memo_btn = QPushButton("📝")
        self.memo_btn.setStyleSheet(Styles.BUTTON)
        self.memo_btn.setFixedSize(35, 35)
        self.memo_btn.setToolTip("共通メモ")
        self.memo_btn.clicked.connect(self.open_memo)
        button_layout.addWidget(self.memo_btn)

        self.vendor_search_btn = QPushButton("🔍")
        self.vendor_search_btn.setStyleSheet(Styles.BUTTON)
        self.vendor_search_btn.setFixedSize(35, 35)
        self.vendor_search_btn.setToolTip("店売り・スタッシュ検索プリセット")
        self.vendor_search_btn.clicked.connect(self.open_vendor_search_presets)
        button_layout.addWidget(self.vendor_search_btn)
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setStyleSheet(Styles.BUTTON)
        self.settings_btn.setFixedSize(35, 35)
        self.settings_btn.clicked.connect(self.open_settings)
        button_layout.addWidget(self.settings_btn)
        
        timer_container_layout.addLayout(button_layout)
        
        # タイマーコンテナを固定高さで追加
        self.timer_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.timer_container)
        
        # ── レベルガイド表示（ボタンの下）──
        # ガイド部分は左右にパディング
        self.guide_container = QWidget()
        self.guide_container.setObjectName("guideContainer")
        self.guide_container.setStyleSheet("""
            #guideContainer { background-color: rgba(20, 30, 20, 140); border-radius: 6px; }
        """)
        guide_container_layout = QVBoxLayout(self.guide_container)
        guide_container_layout.setContentsMargins(20, 5, 20, 0)
        guide_container_layout.setSpacing(5)
        
        # 折りたたみトグルボタン
        self.guide_toggle_btn = QPushButton("▼ ガイド" if self.guide_expanded else "▶ ガイド")
        self.guide_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 12px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.guide_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.guide_toggle_btn.clicked.connect(self.toggle_guide)
        self.guide_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        # トグルボタンはguide_containerの外（タイマーとガイドの間）に配置
        layout.addWidget(self.guide_toggle_btn)
        
        guide_frame = QFrame()
        guide_frame.setStyleSheet(f"""
            QFrame {{
                border: 1px solid rgba(176, 255, 123, 0.3);
                border-radius: 6px;
                padding: 5px;
            }}
        """)
        guide_layout = QVBoxLayout(guide_frame)
        guide_layout.setContentsMargins(10, 5, 10, 5)
        guide_layout.setSpacing(3)
        
        # ゾーン名 + レベル表示
        zone_info_layout = QHBoxLayout()
        self.zone_label = QLabel("📍 エリア: ---")
        self.zone_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        zone_info_layout.addWidget(self.zone_label)
        
        zone_info_layout.addStretch()
        
        self.level_label = QLabel("キャラLv. 1")
        self.level_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        zone_info_layout.addWidget(self.level_label)
        guide_layout.addLayout(zone_info_layout)
        
        # アドバイスメッセージ
        self.advice_label = QLabel("ログ監視待機中...")
        self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.advice_label.setWordWrap(True)
        guide_layout.addWidget(self.advice_label)
        
        self.guide_info_frame = guide_frame
        
        # ゾーンヘッダー折りたたみトグル
        self.zone_header_toggle_btn = QPushButton("▼ ゾーン情報")
        self.zone_header_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.zone_header_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.zone_header_toggle_btn.clicked.connect(self.toggle_zone_header)
        self.zone_header_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        guide_container_layout.addWidget(self.zone_header_toggle_btn)
        guide_container_layout.addWidget(self.guide_info_frame)
        
        # ── 攻略ガイド表示エリア ──
        # ガイドテキスト折りたたみトグル
        self.guide_text_toggle_btn = QPushButton("▼ ガイドテキスト")
        self.guide_text_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.guide_text_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.guide_text_toggle_btn.clicked.connect(self.toggle_guide_text)
        self.guide_text_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        guide_text_header_layout = QHBoxLayout()
        guide_text_header_layout.setContentsMargins(0, 0, 0, 0)
        guide_text_header_layout.setSpacing(6)
        guide_text_header_layout.addWidget(self.guide_text_toggle_btn)
        guide_text_header_layout.addStretch()

        self.area_note_edit_button = QPushButton("📝 エリアメモ")
        self.area_note_edit_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.area_note_edit_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.area_note_edit_button.setToolTip("現在のエリアのエリアメモを編集します")
        self.area_note_edit_button.setStyleSheet(f"""
            QPushButton {{
                background: rgba(20, 30, 20, 160);
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.75);
                border-radius: 5px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(73, 110, 50, 180); color: #ffffff; }}
            QPushButton:disabled {{ color: #666666; border-color: #555555; }}
        """)
        self.area_note_edit_button.clicked.connect(self.open_area_note_editor)
        self.area_note_edit_button.setEnabled(False)
        guide_text_header_layout.addWidget(self.area_note_edit_button)

        self.guide_detail_level_toggle_btn = QPushButton()
        self.guide_detail_level_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.guide_detail_level_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.guide_detail_level_toggle_btn.setToolTip("詳細版ガイド / 要点版ガイドを切り替えます")
        self.guide_detail_level_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(20, 30, 20, 160);
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.75);
                border-radius: 5px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(73, 110, 50, 180);
                color: #ffffff;
            }}
        """)
        self.mini_navi_toggle_btn = QPushButton()
        self.mini_navi_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.mini_navi_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.mini_navi_toggle_btn.setToolTip("みになびのON/OFFを切り替えます。ロック操作はみになび側の鍵ボタンで行えます。")
        self.mini_navi_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(20, 30, 20, 160);
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.75);
                border-radius: 5px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(73, 110, 50, 180);
                color: #ffffff;
            }}
        """)
        self.mini_navi_toggle_btn.clicked.connect(self.toggle_mini_navi_overlay)
        guide_text_header_layout.addWidget(self.mini_navi_toggle_btn)

        self.guide_detail_level_toggle_btn.clicked.connect(self.toggle_guide_detail_level)
        guide_text_header_layout.addWidget(self.guide_detail_level_toggle_btn)
        guide_container_layout.addLayout(guide_text_header_layout)
        self._refresh_mini_navi_toggle()
        self._refresh_guide_detail_level_toggle()
        
        # ── 攻略ガイド表示エリア（本体） ──
        guide_text_frame = QFrame()
        guide_text_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160);
                border: 1px solid rgba(176, 255, 123, 0.2);
                border-radius: 6px;
            }
        """)
        guide_text_layout = QVBoxLayout(guide_text_frame)
        guide_text_layout.setContentsMargins(10, 8, 10, 8)

        self.area_note_frame = QFrame()
        self.area_note_frame.setStyleSheet("""
            QFrame {
                background: rgba(55, 45, 15, 190);
                border: 1px solid rgba(255, 210, 80, 150);
                border-radius: 5px;
            }
        """)
        area_note_layout = QVBoxLayout(self.area_note_frame)
        area_note_layout.setContentsMargins(9, 6, 9, 6)
        area_note_layout.setSpacing(3)
        area_note_title = QLabel("📝 エリアメモ")
        area_note_title.setStyleSheet(
            "color: #ffd86b; font-size: 11px; font-weight: bold; border: none; background: transparent;"
        )
        area_note_layout.addWidget(area_note_title)
        self.area_note_label = QLabel()
        self.area_note_label.setTextFormat(Qt.RichText)
        self.area_note_label.setWordWrap(True)
        self.area_note_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.area_note_label.setStyleSheet(
            f"color: {Styles.TEXT_COLOR}; font-size: {self.guide_font_size}px; border: none; background: transparent;"
        )
        area_note_layout.addWidget(self.area_note_label)
        self.area_note_frame.hide()
        guide_text_layout.addWidget(self.area_note_frame)

        poelab_button_layout = QHBoxLayout()
        poelab_button_layout.setContentsMargins(0, 0, 0, 0)
        self.poelab_link_button = QPushButton("🏛️ 今日のPoELabを開く")
        self.poelab_link_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.poelab_link_button.setToolTip("当日のPoELab Daily Notesを標準ブラウザで開きます")
        self.poelab_link_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.poelab_link_button.setStyleSheet("""
            QPushButton {
                background: rgba(150, 30, 30, 210);
                color: #ffffff;
                border: 1px solid rgba(255, 115, 105, 230);
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(205, 45, 40, 235);
                border-color: #ffaaa2;
            }
            QPushButton:pressed { background: rgba(115, 20, 20, 235); }
            QPushButton:disabled { color: #777777; border-color: #555555; }
        """)
        self.poelab_link_button.clicked.connect(self.open_daily_poelab)
        self.poelab_link_button.hide()
        poelab_button_layout.addWidget(self.poelab_link_button)
        poelab_button_layout.addStretch()
        guide_text_layout.addLayout(poelab_button_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 16px;
                background: rgba(176,255,123,0.08);
                border-radius: 7px;
                margin: 0 2px;
            }
            QScrollBar::handle:vertical {
                min-height: 36px;
                background: rgba(176,255,123,0.55);
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover { background: rgba(176,255,123,0.85); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { width: 0; height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        
        self.guide_text_label = QLabel("エリアに入場すると攻略ガイドが表示されます")
        self.guide_text_label.setStyleSheet(f"color: #888888; font-size: {self.guide_font_size}px; background: transparent;")
        self.guide_text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.guide_text_label.setWordWrap(True)
        self.guide_text_label.setTextFormat(Qt.RichText)
        self.guide_text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.guide_text_label.setOpenExternalLinks(False)
        
        scroll.setWidget(self.guide_text_label)
        guide_text_layout.addWidget(scroll)
        
        self.guide_text_frame = guide_text_frame

        # ガイドテキストと下部セクション（マップ/ジェム取得）の高さをドラッグで調整
        self.guide_body_splitter = QSplitter(Qt.Vertical)
        self.guide_body_splitter.setChildrenCollapsible(False)
        self.guide_body_splitter.setHandleWidth(8)
        self.guide_body_splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                background: rgba(176, 255, 123, 0.12);
                border-top: 1px solid rgba(176, 255, 123, 0.28);
                border-bottom: 1px solid rgba(176, 255, 123, 0.28);
                margin: 1px 0;
            }}
            QSplitter::handle:vertical:hover {{
                background: rgba(176, 255, 123, 0.30);
            }}
        """)
        self.guide_body_splitter.addWidget(self.guide_text_frame)

        self.guide_lower_widget = QWidget()
        guide_lower_layout = QVBoxLayout(self.guide_lower_widget)
        guide_lower_layout.setContentsMargins(0, 0, 0, 0)
        guide_lower_layout.setSpacing(5)
        self.guide_body_splitter.addWidget(self.guide_lower_widget)
        self.guide_body_splitter.setStretchFactor(0, 3)
        self.guide_body_splitter.setStretchFactor(1, 1)
        self.guide_body_splitter.splitterMoved.connect(self._on_guide_body_splitter_moved)
        guide_container_layout.addWidget(self.guide_body_splitter, stretch=1)
        
        # ── マップサムネイル一覧 ──
        # マップ折りたたみトグル
        self.map_toggle_btn = QPushButton("▼ マップ")
        self.map_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.map_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.map_toggle_btn.clicked.connect(self.toggle_map_section)
        self.map_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.map_toggle_btn.setMinimumHeight(30)
        guide_lower_layout.addWidget(self.map_toggle_btn)
        
        self.map_thumbnail = MapThumbnailWidget()
        self.map_thumbnail.setVisible(False)
        guide_lower_layout.addWidget(self.map_thumbnail, stretch=0)
        
        # ── ジェム取得タイミング表示 ──
        # ジェムトラッカー折りたたみトグル
        self.gem_tracker_expanded = self.config.get("gem_tracker_expanded", True)
        self.gem_tracker_toggle_btn = QPushButton("▼ ジェム取得" if self.gem_tracker_expanded else "▶ ジェム取得")
        self.gem_tracker_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.gem_tracker_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.gem_tracker_toggle_btn.clicked.connect(self.toggle_gem_tracker)
        self.gem_tracker_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        guide_lower_layout.addWidget(self.gem_tracker_toggle_btn)
        
        # ジェムトラッカーコンテナ
        self.gem_tracker_frame = QFrame()
        self.gem_tracker_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160);
                border: 1px solid rgba(176, 255, 123, 0.2);
                border-radius: 6px;
            }
        """)
        gem_tracker_layout = QVBoxLayout(self.gem_tracker_frame)
        gem_tracker_layout.setContentsMargins(8, 4, 8, 4)
        gem_tracker_layout.setSpacing(4)
        
        # PoBインポートボタン
        pob_btn_layout = QHBoxLayout()
        pob_btn_layout.setSpacing(6)
        
        self.pob_import_btn = QPushButton("📥 PoBインポート")
        self.pob_import_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(68,136,255,0.2); color: #4488ff;
                border: 1px solid rgba(68,136,255,0.5); border-radius: 3px;
                padding: 3px 10px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(68,136,255,0.35); }}
        """)
        self.pob_import_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.pob_import_btn.clicked.connect(self._on_pob_import)
        pob_btn_layout.addWidget(self.pob_import_btn)
        
        # PoBクリアボタン
        self.pob_clear_btn = QPushButton("データクリア")
        self.pob_clear_btn.setMinimumHeight(22)
        self.pob_clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,102,102,0.10); color: #ff8888;
                border: 1px solid rgba(255,102,102,0.45); border-radius: 3px;
                padding: 3px 8px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(255,102,102,0.22); color: #ffaaaa; }}
        """)
        self.pob_clear_btn.setToolTip("PoBデータをクリア")
        self.pob_clear_btn.clicked.connect(self._on_pob_clear)
        pob_btn_layout.addWidget(self.pob_clear_btn)

        self.gem_popout_btn = QPushButton("↗ ポップアウト")
        self.gem_popout_btn.setMinimumHeight(22)
        self.gem_popout_btn.setToolTip("ジェム取得リストを別ウィンドウで開く")
        self.gem_popout_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(176,255,123,0.12); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.45); border-radius: 3px;
                padding: 3px 8px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(176,255,123,0.25); }}
        """)
        self.gem_popout_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.gem_popout_btn.clicked.connect(self.open_gem_tracker_popup)
        pob_btn_layout.addWidget(self.gem_popout_btn)
        
        pob_btn_layout.addStretch()
        gem_tracker_layout.addLayout(pob_btn_layout)
        
        # ジェムトラッカーウィジェット
        self.gem_tracker = GemTrackerWidget()
        self.gem_tracker.gem_checked.connect(self._on_gem_checked)
        self.gem_tracker.gem_search_requested.connect(self.search_gem_in_poe)
        gem_tracker_layout.addWidget(self.gem_tracker)
        
        # 保存済みPoBデータがあれば復元
        if self._has_pob_import_data():
            self._update_gem_tracker()
        
        self.gem_tracker_frame.setVisible(self.gem_tracker_expanded and self.poe_version == POE1)
        self.gem_tracker_toggle_btn.setVisible(self.poe_version == POE1)
        guide_lower_layout.addWidget(self.gem_tracker_frame, stretch=1)

        saved_splitter_sizes = self.config.get("guide_body_splitter_sizes")
        if (
            isinstance(saved_splitter_sizes, list)
            and len(saved_splitter_sizes) == 2
            and all(isinstance(v, int) and v > 0 for v in saved_splitter_sizes)
        ):
            QTimer.singleShot(0, lambda sizes=saved_splitter_sizes: self.guide_body_splitter.setSizes(sizes))
        
        layout.addWidget(self.guide_container, stretch=1)
        
        # 初期状態の反映
        self._apply_guide_visibility()

        # リサイズグリップ（右下）
        from PySide6.QtWidgets import QSizeGrip
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(20, 20)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background: transparent;
                border: none;
            }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.move(self.width() - 18, self.height() - 18)

    def _adjust_height_keep_width(self):
        """折りたたみ操作時に、現在の横幅を維持したまま高さだけ再調整する。"""
        current_width = self.width()
        self.adjustSize()
        if self.width() != current_width:
            self.resize(current_width, self.height())

    def _on_guide_body_splitter_moved(self, _pos: int, _index: int):
        """ガイドテキスト欄のドラッグ調整位置を保存する。"""
        if not hasattr(self, "guide_body_splitter"):
            return
        self.config["guide_body_splitter_sizes"] = self.guide_body_splitter.sizes()
        ConfigManager.save_config(self.config)

    def _part2_btn_style(self):
        if self.part2_mode:
            return f"""
                QPushButton {{
                    background: rgba(176,255,123,0.2); color: {Styles.TEXT_COLOR};
                    border: 1px solid {Styles.TEXT_COLOR}; border-radius: 3px;
                    padding: 2px 8px; font-size: 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(176,255,123,0.35); }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent; color: #888888;
                    border: 1px solid #555555; border-radius: 3px;
                    padding: 2px 8px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR}; }}
            """
    
    def _visit_btn_style(self):
        if self.visit_override is not None:
            return f"""
                QPushButton {{
                    background: rgba(255,200,50,0.25); color: #ffc832;
                    border: 1px solid #ffc832; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(255,200,50,0.4); }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent; color: #888888;
                    border: 1px solid #555555; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR}; }}
            """

    # === 自動ラップ機能 ===

    def _auto_lap_btn_style(self):
        if self.auto_lap:
            return f"""
                QPushButton {{
                    background: rgba(100,200,255,0.25); color: #64c8ff;
                    border: 1px solid #64c8ff; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(100,200,255,0.4); }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent; color: #888888;
                    border: 1px solid #555555; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR}; }}
            """

    def toggle_auto_lap(self):
        self.auto_lap = not self.auto_lap
        self.auto_lap_btn.setText("自動" if self.auto_lap else "手動")
        self.auto_lap_btn.setStyleSheet(self._auto_lap_btn_style())
        self.config["auto_lap"] = self.auto_lap
        ConfigManager.save_config(self.config)

    def _interlude_boss_zone_map(self):
        return {
            "ホルテンの豪邸": 5,
            "Holten Estate": 5,
            "キーマの貯水池": 6,
            "Qimah Reservoir": 6,
            "クアチクの地下避難所": 7,
            "The Cuachic Vault": 7,
        }

    def _interlude_start_zone_map(self):
        return {
            "避難所": 5,
            "The Refuge": 5,
            "カーリバザール": 6,
            "The Khari Bazaar": 6,
            "森の広場": 7,
            "The Glade": 7,
        }

    def _handle_interlude_lap_progress(self, zone_name: str):
        if self.poe_version != POE2 or not self.is_running:
            return
        boss_lap = self._interlude_boss_zone_map().get(zone_name)
        if boss_lap:
            self.interlude_ready.add(boss_lap)
            return
        start_lap = self._interlude_start_zone_map().get(zone_name)
        if not start_lap:
            return
        completed = sorted(lap for lap in self.interlude_ready if lap != start_lap and self.lap_times[lap - 1] is None)
        for lap_num in completed:
            print(f"[AUTO-LAP] {self.lap_labels[lap_num - 1]}完了 — {zone_name}到達")
            self.record_lap_at(lap_num)
            self.interlude_ready.discard(lap_num)

    def _try_auto_lap(self, zone_name: str):
        """エリア入場時に自動ラップを試行"""
        if not self.auto_lap or not self.is_running:
            return
        lap_num = get_auto_lap_triggers(self.poe_version).get(zone_name)
        if lap_num is None:
            return
        # Act1トリガー(南の森)はAct6にも同名あるのでpart2_modeで判別
        if lap_num == 1 and self.part2_mode:
            return

        # PoE2の幕間1-3は自由順で記録、クリアは幕間完了後のみ
        if self.poe_version == POE2 and 5 <= lap_num <= 7:
            print(f"[AUTO-LAP] {self.lap_labels[lap_num - 1]}完了 — {zone_name}")
            self.record_lap_at(lap_num)
            return
        if self.poe_version == POE2 and lap_num == 8:
            pending_interludes = sorted(lap for lap in self.interlude_ready if 5 <= lap <= 7 and self.lap_times[lap - 1] is None)
            for pending_lap in pending_interludes:
                print(f"[AUTO-LAP] {self.lap_labels[pending_lap - 1]}完了 — キャンペーンクリア到達")
                self.record_lap_at(pending_lap)
                self.interlude_ready.discard(pending_lap)
            if any(self.lap_times[i] is None for i in range(4, 7)):
                return
            print(f"[AUTO-LAP] {self.lap_labels[lap_num - 1]}完了 — {zone_name}")
            self.record_lap_at(lap_num)
            if zone_name in ("ジッグラトの避難所", "The Ziggurat Refuge"):
                clear_html = get_clear_message(POE2, "final")
                if clear_html:
                    self.guide_text_label.setText(clear_html)
                    self.guide_text_label.setStyleSheet(
                        f"color: #e0e0e0; font-size: {self.guide_font_size}px; background: transparent;"
                    )
                    self.map_thumbnail.load_maps("", part2=False)
            return

        # 現在のActと一致する場合のみ記録（重複・順序ずれ防止）
        if lap_num == self.current_act:
            print(f"[AUTO-LAP] Act{lap_num}完了 — {zone_name}")
            self.record_lap()

    def _auto_lap_kitava(self, lap_num: int):
        """キタヴァ撃破による自動ラップ"""
        if not self.auto_lap or not self.is_running:
            return
        if lap_num == self.current_act:
            print(f"[AUTO-LAP] Act{lap_num}完了 — キタヴァ撃破")
            self.record_lap()

    def toggle_visit_override(self):
        """訪問回数の表示を一時的に切り替え（自動→1回目→2回目→自動）"""
        if self.visit_override is None:
            self.visit_override = 1
        elif self.visit_override == 1:
            self.visit_override = 2
        else:
            self.visit_override = None
        self._update_visit_btn()
        # 現在のゾーンのガイドを再表示
        if self.current_zone:
            zone_id = self._current_zone_id()
            visit_num = self.visit_override if self.visit_override else self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def _update_visit_btn(self):
        if self.visit_override is None:
            self.visit_btn.setText("自動")
        elif self.visit_override == 1:
            self.visit_btn.setText("1回目")
        else:
            self.visit_btn.setText("2回目")
        self.visit_btn.setStyleSheet(self._visit_btn_style())

    def _current_zone_id(self):
        """現在のゾーンのzone_idを返す（_get_zone_idに委譲）"""
        if not self.current_zone:
            return None
        return self._get_zone_id(self.current_zone)

    def toggle_part2(self):
        """Part 1/2を手動トグル"""
        self._set_part2(not self.part2_mode)
    
    def _set_part2(self, enabled: bool, update_guide: bool = True):
        """Part 2モードの切り替え"""
        if self.part2_mode == enabled:
            return
        self.part2_mode = enabled
        self.config["part2_mode"] = enabled
        ConfigManager.save_config(self.config)
        self.part2_btn.setText("Act 6-10" if enabled else "Act 1-5")
        self.part2_btn.setStyleSheet(self._part2_btn_style())
        # 現在のゾーンを再評価（カウントアップせずガイド表示だけ更新）
        if update_guide and self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            act_name, zone_level = get_zone_info(self.zone_data, self.current_zone, part2=self.part2_mode)
            self._update_guide_and_map(self.current_zone, zone_id, 1)
    
    def toggle_timer(self):
        """タイマー+ラップ表示の折りたたみ/展開"""
        new_expanded = not self.timer_expanded
        self._set_timer_expanded(new_expanded)
        self.config["timer_expanded"] = self.timer_expanded
        # 設定で「オフ」を選んだ後に手動展開した場合は、直前のサイズへ戻す
        if new_expanded and self.config.get("timer_size") == "off":
            restored_size = self.config.get("timer_size_before_off", "medium")
            self.config["timer_size"] = restored_size
            self.timer_size = restored_size
            self._apply_timer_size()
        ConfigManager.save_config(self.config)
        self._adjust_height_keep_width()
    
    def toggle_lap(self):
        """ラップタイム表示の折りたたみ/展開"""
        self.lap_expanded = not self.lap_expanded
        self.lap_content.setVisible(self.lap_expanded)
        self.lap_toggle_btn.setText("▼ ラップタイム" if self.lap_expanded else "▶ ラップタイム")
        self.config["lap_expanded"] = self.lap_expanded
        ConfigManager.save_config(self.config)
        self._adjust_height_keep_width()
    
    def toggle_gem_tracker(self):
        """ジェム取得リストの折りたたみ/展開"""
        if self.poe_version != POE1:
            return
        self.gem_tracker_expanded = not self.gem_tracker_expanded
        self.gem_tracker_frame.setVisible(self.gem_tracker_expanded)
        self.gem_tracker_toggle_btn.setText("▼ ジェム取得" if self.gem_tracker_expanded else "▶ ジェム取得")
        self.config["gem_tracker_expanded"] = self.gem_tracker_expanded
        ConfigManager.save_config(self.config)
        self._adjust_height_keep_width()

    def _load_pob_import_state(self):
        return ConfigManager.load_pob_import_data()

    def _current_pob_data(self):
        return self._load_pob_import_state().get("pob_data")

    def _has_pob_import_data(self):
        return bool(self._current_pob_data())

    def _on_pob_import(self):
        """PoBインポートボタンのクリックハンドラ"""
        dialog = PoBImportDialog(self)
        if dialog.exec() == QDialog.Accepted:
            pob_code = dialog.get_pob_code()
            if not pob_code:
                return
            try:
                skill_sets = get_pob_skill_sets(pob_code)
                selected_skill_set_ids = []
                if skill_sets:
                    skill_set_dialog = PoBSkillSetSelectionDialog(skill_sets, self)
                    if skill_set_dialog.exec() != QDialog.Accepted:
                        return
                    selected_skill_set_ids = skill_set_dialog.selected_skill_set_ids()

                result = import_pob(pob_code, selected_skill_set_ids=selected_skill_set_ids)
                if not result or not result.get("gem_groups"):
                    QMessageBox.warning(self, "インポートエラー", "選択されたSkill setからジェム情報を取得できませんでした。")
                    return

                # PoBインポート結果は設定ではなく専用JSONへ保存
                ConfigManager.save_pob_import_data({
                    "pob_data": result,
                    "pob_code": pob_code,
                    "selected_skill_set_ids": selected_skill_set_ids,
                })
                # 旧バージョンでconfig.jsonに入っていた場合は掃除する
                self.config.pop("pob_data", None)
                self.config.pop("pob_code", None)
                ConfigManager.save_config(self.config)

                # ジェム取得リストを更新
                self._update_gem_tracker()
                selected_titles = [
                    skill_set.get("title", "")
                    for skill_set in result.get("skill_sets", [])
                    if str(skill_set.get("id", "")) in set(selected_skill_set_ids)
                ]
                skill_set_summary = "\n".join(f"- {title}" for title in selected_titles[:8])
                if len(selected_titles) > 8:
                    skill_set_summary += f"\n- 他 {len(selected_titles) - 8}件"
                QMessageBox.information(self, "インポート成功",
                    f"クラス: {result.get('class', '?')}\n"
                    f"昇華: {result.get('ascendancy', '?')}\n"
                    f"Skill set: {len(selected_titles) if selected_titles else '全'}個\n"
                    f"ジェムグループ: {len(result.get('gem_groups', []))}個"
                    + (f"\n\n{skill_set_summary}" if skill_set_summary else ""))
            except Exception as e:
                QMessageBox.warning(self, "インポートエラー", f"PoBコードの解析に失敗しました:\n{e}")

    def _update_gem_tracker(self):
        """ジェム取得リストを現在のActに基づいて更新"""
        pob_data = self._current_pob_data()
        if not pob_data:
            return

        use_library = ConfigManager.effective_poe1_route_act3(self.config) == "library_detour"
        checked_gems = self._load_pob_import_state().get("gem_tracker_checked", [])

        # PoBデータからジェム名リストを抽出
        gem_names = []
        for group in pob_data.get("gem_groups", []):
            for gem in group.get("gems", []):
                name = gem.get("name", "").lower()
                if name and name not in gem_names:
                    gem_names.append(name)

        plan = resolve_gem_acquisition(
            gem_names=gem_names,
            char_class=pob_data.get("class", "").lower(),
            library_route=use_library,
        )

        self._apply_gem_tracker_data(self.gem_tracker, plan, pob_data, use_library, checked_gems)
        if self.gem_tracker_popup is not None:
            self._apply_gem_tracker_data(self.gem_tracker_popup.gem_tracker, plan, pob_data, use_library, checked_gems)

    def _apply_gem_tracker_data(self, widget: GemTrackerWidget, plan: list, pob_data: dict, use_library: bool, checked_gems: list):
        """GemTrackerWidgetへ現在のPoB/チェック/Act状態を反映する。"""
        widget.set_library_route(use_library)
        widget._checked_gems = set(checked_gems)
        widget.set_acquisition_plan(
            plan=plan,
            char_class=pob_data.get("class", ""),
            ascendancy=pob_data.get("ascendancy", ""),
        )
        widget.set_current_act(getattr(self, "current_zone_act", self.current_act))

    def _sync_gem_tracker_checked_state(self):
        """本体/ポップアウト間でチェック状態を同期する。"""
        checked = set(self._load_pob_import_state().get("gem_tracker_checked", []))
        if hasattr(self, "gem_tracker"):
            self.gem_tracker.set_checked_gems(checked)
        if self.gem_tracker_popup is not None:
            self.gem_tracker_popup.gem_tracker.set_checked_gems(checked)

    def open_gem_tracker_popup(self):
        """ジェム取得リストを別ウィンドウで開く。"""
        if self.gem_tracker_popup is None:
            self.gem_tracker_popup = GemTrackerPopupDialog(self)
            self.gem_tracker_popup.gem_tracker.gem_checked.connect(self._on_gem_checked)
            self.gem_tracker_popup.gem_tracker.gem_search_requested.connect(self.search_gem_in_poe)
            self.gem_tracker_popup.destroyed.connect(lambda _obj=None: setattr(self, "gem_tracker_popup", None))
            if self._has_pob_import_data():
                self._update_gem_tracker()
        self.gem_tracker_popup.show()
        self.gem_tracker_popup.raise_()
        self.gem_tracker_popup.activateWindow()

    def _on_pob_clear(self):
        """PoBデータをクリア"""
        ConfigManager.clear_pob_import_data()
        self.config.pop("pob_data", None)
        self.config.pop("pob_code", None)
        self.config.pop("gem_tracker_checked", None)
        ConfigManager.save_config(self.config)
        self.gem_tracker.clear()
        if self.gem_tracker_popup is not None:
            self.gem_tracker_popup.gem_tracker.clear()

    def _on_gem_checked(self, gem_name: str, checked: bool):
        """ジェムチェックボックスの状態変更ハンドラ"""
        pob_state = self._load_pob_import_state()
        checked_gems = list(pob_state.get("gem_tracker_checked", []))
        if checked and gem_name not in checked_gems:
            checked_gems.append(gem_name)
        elif not checked and gem_name in checked_gems:
            checked_gems.remove(gem_name)
        pob_state["gem_tracker_checked"] = checked_gems
        ConfigManager.save_pob_import_data(pob_state)
        self.config.pop("gem_tracker_checked", None)
        ConfigManager.save_config(self.config)
        self._sync_gem_tracker_checked_state()

    def toggle_guide(self):
        """ガイドエリアの折りたたみ/展開をトグル"""
        self.guide_expanded = not self.guide_expanded
        self._apply_guide_visibility()
        self._refresh_mini_navi_toggle()
        # config保存
        self.config["guide_expanded"] = self.guide_expanded
        ConfigManager.save_config(self.config)
        self._adjust_height_keep_width()
    
    def toggle_zone_header(self):
        """ゾーンヘッダーの折りたたみ/展開"""
        self.zone_header_expanded = not self.zone_header_expanded
        self.guide_info_frame.setVisible(self.zone_header_expanded)
        self.zone_header_toggle_btn.setText("▼ ゾーン情報" if self.zone_header_expanded else "▶ ゾーン情報")
        self._adjust_height_keep_width()
    
    def toggle_guide_text(self):
        """ガイドテキストの折りたたみ/展開"""
        self.guide_text_expanded = not self.guide_text_expanded
        self.guide_text_frame.setVisible(self.guide_text_expanded)
        self.guide_text_toggle_btn.setText("▼ ガイドテキスト" if self.guide_text_expanded else "▶ ガイドテキスト")
        self._adjust_height_keep_width()

    def _update_poelab_link_visibility(self, zone_id: str | None):
        """本体ガイド欄のPoELabボタンを対象3エリアだけに表示する。"""
        self._current_poelab_type = self.POELAB_ZONE_TYPES.get(zone_id)
        self.poelab_link_button.setVisible(self._current_poelab_type is not None)
        if self._current_poelab_type is None:
            self._reset_poelab_link_button()

    def _update_area_note(self, zone_name: str, zone_id: str | None):
        self._current_zone_id = zone_id
        self._current_zone_name = zone_name
        self.area_note_edit_button.setEnabled(bool(zone_id))
        if not zone_id:
            self._current_area_note = ""
            self.area_note_label.clear()
            self.area_note_frame.hide()
            return
        try:
            content = get_area_note(self.poe_version, zone_id)
        except ValueError as exc:
            self._current_area_note = ""
            self.area_note_label.clear()
            self.area_note_frame.hide()
            self.area_note_edit_button.setEnabled(False)
            QMessageBox.warning(self, "エリアメモ読込エラー", str(exc))
            return
        self._current_area_note = content
        self.area_note_label.setText(content.replace("\n", "<br>"))
        self.area_note_frame.setVisible(bool(content.strip()))

    def open_area_note_editor(self):
        zone_id = self._current_zone_id
        if not zone_id:
            return
        dialog = AreaNoteDialog(self, self._current_zone_name or zone_id, self._current_area_note)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            set_area_note(self.poe_version, zone_id, dialog.content())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "エリアメモ保存エラー", str(exc))
            return
        self._update_area_note(self._current_zone_name, zone_id)

    def open_daily_poelab(self):
        """当日のDaily Notes URLだけを取得し、標準ブラウザで開く。"""
        lab_type = self._current_poelab_type
        if not lab_type or not self.poelab_link_button.isEnabled():
            return
        self.poelab_link_button.setEnabled(False)
        self.poelab_link_button.setText("🏛️ PoELabリンクを取得中…")

        def resolve():
            try:
                self.poelab_url_resolved.emit(find_daily_notes_url(lab_type))
            except Exception as exc:
                self.poelab_url_failed.emit(str(exc))

        threading.Thread(target=resolve, daemon=True).start()

    def _open_resolved_poelab_url(self, url: str):
        QDesktopServices.openUrl(QUrl(url))
        self._reset_poelab_link_button()

    def _handle_poelab_url_error(self, _message: str):
        # サイト側の構造変更や一時的な通信失敗時も、PoELab自体には到達できるようにする。
        QDesktopServices.openUrl(QUrl(POELAB_HOME))
        self._reset_poelab_link_button()

    def _reset_poelab_link_button(self):
        self.poelab_link_button.setEnabled(True)
        self.poelab_link_button.setText("🏛️ 今日のPoELabを開く")
    
    def _is_mini_navi_available(self):
        """みになびは現状PoE1専用。PoE2では未実装なので入口を出さない。"""
        return self.poe_version == POE1

    def _mini_navi_toggle_text(self):
        overlay_config = self.config.get("mini_guide_overlay", {})
        enabled = bool(overlay_config.get("enabled", False))
        return "みになび ON" if enabled else "みになび OFF"

    def _refresh_mini_navi_toggle(self):
        if not hasattr(self, "mini_navi_toggle_btn"):
            return
        self.mini_navi_toggle_btn.setText(self._mini_navi_toggle_text())
        self.mini_navi_toggle_btn.setVisible(self._is_mini_navi_available() and self.guide_expanded)

    def toggle_mini_navi_overlay(self):
        if not self._is_mini_navi_available():
            if hasattr(self, "mini_navi_overlay"):
                self.mini_navi_overlay.hide()
            self._refresh_mini_navi_toggle()
            return
        overlay_config = self.config.setdefault("mini_guide_overlay", {})
        overlay_config["enabled"] = not bool(overlay_config.get("enabled", False))
        ConfigManager.save_config(self.config)
        if hasattr(self, "mini_navi_overlay"):
            self.mini_navi_overlay.apply_settings(refresh_window_flags=True)
        self._refresh_mini_navi_toggle()
        if self.current_zone:
            if self._is_town_zone(self.current_zone):
                self.mini_navi_overlay.show_last_content_or_waiting()
                return
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def _guide_detail_level_toggle_text(self):
        """現在のガイド表示レベルからトグルボタン文言を返す。"""
        if self.config.get("guide_detail_level", "beginner") == "intermediate":
            return "要点版ガイド"
        return "詳細版ガイド"

    def _refresh_guide_detail_level_toggle(self):
        """PoE2専用のガイド表示レベルトグル状態を反映する。"""
        if not hasattr(self, "guide_detail_level_toggle_btn"):
            return
        self.guide_detail_level_toggle_btn.setText(self._guide_detail_level_toggle_text())
        self.guide_detail_level_toggle_btn.setVisible(
            self.poe_version == POE2 and self.guide_expanded
        )

    def toggle_guide_detail_level(self):
        """詳細版ガイド / 要点版ガイドを即時切り替えする。"""
        current = self.config.get("guide_detail_level", "beginner")
        self.config["guide_detail_level"] = "intermediate" if current != "intermediate" else "beginner"
        self.config["guide_detail_level_selected"] = True
        ConfigManager.save_config(self.config)
        self._refresh_guide_detail_level_toggle()

        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    
    def toggle_map_section(self):
        """マップセクションの折りたたみ/展開"""
        self.map_section_expanded = not self.map_section_expanded
        if self.map_section_expanded:
            self.map_thumbnail.setVisible(len(self.map_thumbnail.current_paths) > 0)
        else:
            self.map_thumbnail.setVisible(False)
        self.map_toggle_btn.setText("▼ マップ" if self.map_section_expanded else "▶ マップ")
        self._adjust_height_keep_width()
    
    def _apply_guide_visibility(self):
        """ガイドの表示/非表示を適用"""
        if self.guide_expanded:
            # 全体展開時は各セクションの個別状態に従う
            self.guide_info_frame.setVisible(self.zone_header_expanded)
            self.guide_text_frame.setVisible(self.guide_text_expanded)
            has_maps = len(self.map_thumbnail.current_paths) > 0
            self.map_thumbnail.setVisible(self.map_section_expanded and has_maps)
            # サブトグルボタンも表示
            self.zone_header_toggle_btn.setVisible(True)
            self.guide_text_toggle_btn.setVisible(True)
            self._refresh_guide_detail_level_toggle()
            self.map_toggle_btn.setVisible(True)
        else:
            # 全体折りたたみ時は3セクションすべて非表示
            self.guide_info_frame.setVisible(False)
            self.guide_text_frame.setVisible(False)
            self.map_thumbnail.setVisible(False)
            # サブトグルボタンも非表示
            self.zone_header_toggle_btn.setVisible(False)
            self.guide_text_toggle_btn.setVisible(False)
            if hasattr(self, "guide_detail_level_toggle_btn"):
                self.guide_detail_level_toggle_btn.setVisible(False)
            self.map_toggle_btn.setVisible(False)
        # 背景も連動
        if self.guide_expanded:
            self.guide_container.setStyleSheet("""
                #guideContainer { background-color: rgba(20, 30, 20, 140); border-radius: 6px; }
            """)
        else:
            self.guide_container.setStyleSheet("""
                #guideContainer { background-color: transparent; }
            """)
        self.guide_toggle_btn.setText("▼ ガイド" if self.guide_expanded else "▶ ガイド")
    
    def start_timer(self):
        if not self.is_running:
            self.start_time = time.time()
            self.timer.start(10)
            self.is_running = True
            if self.current_zone:
                self.segment_recorder.record_entry(
                    self._get_zone_id(self.current_zone) or self.current_zone,
                    self.current_zone,
                    self.get_elapsed_time(),
                )
                self._update_segment_summary()
            
    def stop_timer(self):
        if self.is_running:
            self.timer.stop()
            self.accumulated_time += time.time() - self.start_time
            self.is_running = False
            self._save_timer_state()
            
    def reset_timer(self):
        # 確認ダイアログ（設定ON かつ タイマーが動いているか記録がある場合）
        if self.config.get("confirm_reset", True):
            has_data = self.accumulated_time > 0 or self.is_running or any(t is not None for t in self.lap_times)
            if has_data:
                msg = QMessageBox(self)
                msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
                msg.setWindowTitle("リセット確認")
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setText("タイマーとラップをリセットしますか？")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setDefaultButton(QMessageBox.StandardButton.No)
                if msg.exec() != QMessageBox.StandardButton.Yes:
                    return
        
        # ラップ記録があれば保存
        if any(t is not None for t in self.lap_times):
            total = self.get_elapsed_time()
            LapRecorder.save_run(self.lap_times, total, segments=self.segment_recorder.segments)
        
        self.stop_timer()
        self.accumulated_time = 0.0
        self.update_text(0.0)
        self.reset_laps()
        self._clear_saved_timer()
    
    def reset_laps(self):
        """全ラップをリセット"""
        self.lap_labels = get_lap_labels(self.poe_version)
        self.lap_times = [None] * len(self.lap_labels)
        self.segment_recorder.reset()
        self.current_act = 1
        self.update_lap_display()
        # Part 1に戻す
        self._set_part2(False)
        # 訪問回数リセット
        self.zone_visit_counts = {}
        self.visit_override = None
        self._update_visit_btn()
        # マップクリア
        self.map_thumbnail.clear()
    
    def get_elapsed_time(self):
        """現在の経過時間を取得"""
        if self.is_running:
            return self.accumulated_time + (time.time() - self.start_time)
        return self.accumulated_time
    
    def _timer_state_key(self):
        # 旧config.json保存形式の移行用キー。新規保存はtimer_poe*.jsonへ行う。
        return f"saved_timer::{get_timer_filename(self.poe_version)}"

    def _timer_state_path(self):
        return ConfigManager.get_user_data_dir() / get_timer_filename(self.poe_version)

    def _timer_state_payload(self):
        return {
            "accumulated_time": self.accumulated_time,
            "lap_times": self.lap_times,
            "lap_record_order": self.lap_record_order,
            "current_act": self.current_act,
            "segments": getattr(self, "segment_recorder", SegmentRecorder()).segments,
        }

    def _save_timer_state_payload(self, payload):
        path = self._timer_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def _load_timer_state_payload(self):
        path = self._timer_state_path()
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"[WARN] タイマー状態の読み込みに失敗しました [{self.poe_version}]: {e}")
            return None

    def _migrate_legacy_timer_state_from_config(self):
        key = self._timer_state_key()
        saved = self.config.get(key)
        if not isinstance(saved, dict):
            return None

        # timer_poe*.json がまだ無い場合だけ旧config内タイマーを移行する。
        if not self._timer_state_path().exists():
            self._save_timer_state_payload(saved)

        # 以後config.jsonにタイマー状態を残さない。
        del self.config[key]
        ConfigManager.save_config(self.config)
        return saved

    def _save_timer_state(self):
        """タイマー状態をPoEバージョン別のtimer_poe*.jsonへ保存"""
        self._save_timer_state_payload(self._timer_state_payload())
        print(f"[INFO] タイマー状態を保存しました [{self.poe_version}] (経過: {self.accumulated_time:.1f}秒, Act{self.current_act})")
    
    def _clear_saved_timer(self):
        """現在のPoEバージョンの保存済みタイマー状態をクリア"""
        path = self._timer_state_path()
        if path.exists():
            try:
                path.unlink()
            except Exception as e:
                print(f"[WARN] タイマー状態の削除に失敗しました [{self.poe_version}]: {e}")
        key = self._timer_state_key()
        if key in self.config:
            del self.config[key]
            ConfigManager.save_config(self.config)
    
    def _restore_timer_state(self):
        """起動時に現在のPoEバージョンの保存済みタイマー状態を復元"""
        saved = self._load_timer_state_payload() or self._migrate_legacy_timer_state_from_config()
        if not saved:
            return
        self.accumulated_time = saved.get("accumulated_time", 0.0)
        self.lap_labels = get_lap_labels(self.poe_version)
        self.lap_times = saved.get("lap_times", [None] * len(self.lap_labels))
        while len(self.lap_times) < len(self.lap_labels):
            self.lap_times.append(None)
        self.lap_record_order = [lap for lap in saved.get("lap_record_order", []) if 1 <= lap <= len(self.lap_labels)]
        self.current_act = saved.get("current_act", 1)
        self.segment_recorder = SegmentRecorder(saved.get("segments", []))
        if self.accumulated_time > 0:
            self.update_text(self.accumulated_time)
            self.update_lap_display()
            if self.poe_version == POE1 and self.current_act > 5:
                self._set_part2(True)
            print(f"[INFO] タイマー状態を復元しました [{self.poe_version}] (経過: {self.accumulated_time:.1f}秒, Act{self.current_act})")
    
    def _rebuild_lap_ui(self):
        while self.lap_content_layout.count():
            item = self.lap_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        self.lap_label_widgets = []
        for label in self.lap_labels:
            lap_layout = QHBoxLayout()
            lap_layout.setSpacing(5)

            act_label = QLabel(label)
            act_label.setFixedWidth(90)
            time_label = QLabel("--:--.--")
            time_label.setFixedWidth(100)
            split_label = QLabel("(--:--.--)")
            split_label.setFixedWidth(100)

            lap_layout.addWidget(act_label)
            lap_layout.addWidget(time_label)
            lap_layout.addWidget(split_label)
            lap_layout.addStretch()

            self.lap_content_layout.addLayout(lap_layout)
            self.lap_label_widgets.append((act_label, time_label, split_label))

        if hasattr(self, "segment_summary_label"):
            self.lap_content_layout.addWidget(self.segment_summary_label)

    def _refresh_current_lap_index(self):
        for idx, lap in enumerate(self.lap_times, start=1):
            if lap is None:
                self.current_act = idx
                return
        self.current_act = len(self.lap_times)

    def record_lap(self):
        """現在のAct/幕間のラップを記録"""
        if self.current_act > len(self.lap_times):
            return
        
        elapsed = self.get_elapsed_time()
        self.lap_times[self.current_act - 1] = elapsed
        if self.current_act not in self.lap_record_order:
            self.lap_record_order.append(self.current_act)
        
        if self.current_act < len(self.lap_times):
            self.current_act += 1
        else:
            LapRecorder.save_run(self.lap_times, elapsed, segments=self.segment_recorder.segments)
        
        self.update_lap_display()
        # ジェムトラッカーをAct変更に連動
        if self._has_pob_import_data():
            self._update_gem_tracker()

    def record_lap_at(self, lap_num: int):
        """指定ラップ枠を直接記録（PoE2幕間など自由順用）"""
        if lap_num < 1 or lap_num > len(self.lap_times):
            return
        if self.lap_times[lap_num - 1] is not None:
            return
        elapsed = self.get_elapsed_time()
        self.lap_times[lap_num - 1] = elapsed
        if lap_num not in self.lap_record_order:
            self.lap_record_order.append(lap_num)
        if all(lap is not None for lap in self.lap_times):
            LapRecorder.save_run(self.lap_times, elapsed, segments=self.segment_recorder.segments)
        else:
            self._refresh_current_lap_index()
        self.update_lap_display()
        if self._has_pob_import_data():
            self._update_gem_tracker()
    
    def undo_lap(self):
        """直前のラップを取り消し"""
        if self.current_act > 1 and self.lap_times[self.current_act - 2] is not None:
            lap_num = self.current_act - 1
            self.lap_times[self.current_act - 2] = None
            if lap_num in self.lap_record_order:
                self.lap_record_order.remove(lap_num)
            self.current_act -= 1
            self.update_lap_display()
        elif self.current_act == 1 and self.lap_times[0] is not None:
            self.lap_times[0] = None
            if 1 in self.lap_record_order:
                self.lap_record_order.remove(1)
            self.update_lap_display()
    
    def format_lap_time(self, seconds):
        """ラップタイムをフォーマット"""
        if seconds is None:
            return "--:--.--"
        
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        cs = int((seconds * 100) % 100)
        
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}.{cs:02d}"
        else:
            return f"{mins:02d}:{secs:02d}.{cs:02d}"

    def _update_segment_summary(self):
        """直近区間と遅い区間をコンパクトに表示する。"""
        if not hasattr(self, "segment_summary_label"):
            return

        summary = self.segment_recorder.summary()
        latest = summary["latest"]
        if not latest:
            self.segment_summary_label.setText("区間: エリア移動を待機中")
            return

        latest_name = latest.get("zone_name") or latest.get("zone_id", "不明")
        latest_text = f"直近: {latest_name} {self.format_lap_time(latest.get('duration', 0.0))}"
        slowest_text = " / ".join(
            f"{segment.get('zone_name') or segment.get('zone_id', '不明')} {self.format_lap_time(segment.get('duration', 0.0))}"
            for segment in summary["slowest"]
        )
        self.segment_summary_label.setText(
            f"{latest_text}\n遅い区間: {slowest_text}"
        )

    def update_lap_display(self):
        """ラップタイム表示を更新"""
        self._update_segment_summary()
        for i, (act_lbl, time_lbl, split_lbl) in enumerate(self.lap_label_widgets):
            act_name = self.lap_labels[i]
            lap_time = self.lap_times[i] if i < len(self.lap_times) else None

            if lap_time is not None:
                lap_num = i + 1
                prev_time = None
                if lap_num in self.lap_record_order:
                    order_idx = self.lap_record_order.index(lap_num)
                    if order_idx > 0:
                        prev_lap_num = self.lap_record_order[order_idx - 1]
                        prev_time = self.lap_times[prev_lap_num - 1]
                split_time = lap_time if prev_time is None else lap_time - prev_time
            else:
                split_time = None

            display_name = act_name

            if lap_time is not None:
                act_lbl.setText(display_name)
                time_lbl.setText(self.format_lap_time(lap_time))
                split_lbl.setText(f"({self.format_lap_time(split_time)})")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
            elif (i + 1) == self.current_act:
                act_lbl.setText(f"⇒ {display_name}")
                time_lbl.setText("進行中...")
                split_lbl.setText("")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
            else:
                act_lbl.setText(display_name)
                time_lbl.setText("--:--.--")
                split_lbl.setText("")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_PENDING)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_PENDING)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_PENDING)

    def update_display(self):
        current_time = time.time()
        elapsed = self.accumulated_time + (current_time - self.start_time)
        self.update_text(elapsed)

    def update_text(self, elapsed_seconds):
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        centiseconds = int((elapsed_seconds * 100) % 100)
        
        hours = int(minutes // 60)
        minutes = minutes % 60
        
        # 各パーツを更新
        self.lbl_hours.setText(f"{hours:02d}")
        self.lbl_mins.setText(f"{minutes:02d}")
        self.lbl_secs.setText(f"{seconds:02d}")
        self.lbl_ms.setText(f".{centiseconds:02d}")
        
        # Colonは固定なので更新不要

    # --- ホットキー処理 ---
    def register_hotkeys(self):
        """pynputを使用してグローバルホットキーを登録"""
        try:
            # 既存のリスナーを停止
            if self.keyboard_listener:
                self.keyboard_listener.stop()
                self.keyboard_listener = None
            
            hotkeys = self.config.get("hotkeys", {})
            
            self.hotkey_map = {}
            for action, default in [("start_stop", "F1"), ("reset", "F2"), ("lap", "F3"),
                                     ("undo_lap", "F4"), ("click_through", DEFAULT_CLICK_THROUGH_HOTKEY), ("logout", "F5"),
                                     ("hideout", "F11"), ("monastery", "F12"),
                                     ("search_string_test", "none")]:
                key = hotkeys.get(action, default)
                if key and key != "none":
                    self.hotkey_map[key.lower()] = action
            
            print(f"Registering hotkeys: {self.hotkey_map}")
            
            def on_press(key):
                try:
                    # キー名を取得
                    if hasattr(key, 'name'):
                        key_name = key.name.lower()
                    elif hasattr(key, 'char') and key.char:
                        key_name = key.char.lower()
                    else:
                        return
                    
                    # ホットキーマップをチェック
                    if key_name in self.hotkey_map:
                        command = self.hotkey_map[key_name]
                        print(f"[HOTKEY DEBUG] key={key_name} command={command} search_in_progress={getattr(self, '_search_paste_in_progress', False)}")
                        self.hotkey_signal.emit(command)
                except Exception as e:
                    print(f"Hotkey error: {e}")
            
            self.keyboard_listener = pynput_keyboard.Listener(on_press=on_press)
            self.keyboard_listener.start()
            
        except Exception as e:
            print(f"Failed to register hotkeys: {e}")

    def handle_hotkey(self, command):
        print(f"[HOTKEY DEBUG] handle command={command} search_in_progress={getattr(self, '_search_paste_in_progress', False)}")
        if command == "start_stop":
            if self.is_running:
                self.stop_timer()
            else:
                self.start_timer()
        elif command == "reset":
            self.reset_timer()
        elif command == "lap":
            self.record_lap()
        elif command == "undo_lap":
            self.undo_lap()
        elif command == "click_through":
            self.toggle_click_through()
        elif command == "logout":
            self.execute_logout()
        elif command == "hideout":
            self.execute_chat_command("/hideout")
        elif command == "monastery":
            self.execute_chat_command("/monastery")
        elif command == "search_string_test":
            self.open_search_string_paste_test()

    def open_search_string_paste_test(self):
        """ベンダー検索プリセット→元ウィンドウ復帰→検索欄貼り付け。"""
        previous_target_hwnd = None

        def close_existing_dialog(dialog):
            if dialog is None:
                return None
            try:
                target = getattr(dialog, "target_hwnd", None)
                dialog.hide()
                dialog.close()
                return target
            except RuntimeError:
                # QtのC++側オブジェクトが既に削除済みの場合がある。
                return None

        # 参照が外れた古いメニューも含め、残っている検索メニューを全て閉じる。
        # F4連打時に複数表示されるのを防ぐため、親参照だけに頼らない。
        app = QApplication.instance()
        if app is not None:
            for widget in list(app.topLevelWidgets()):
                if isinstance(widget, SearchStringPasteTestDialog):
                    previous_target_hwnd = previous_target_hwnd or close_existing_dialog(widget)

        existing_dialog = getattr(self, "_search_string_test_dialog", None)
        previous_target_hwnd = previous_target_hwnd or close_existing_dialog(existing_dialog)
        self._search_string_test_dialog = None

        # 既存メニュー表示中にもう一度ホットキーを押した場合、前面ウィンドウは旧メニューや
        # みになび/鍵ボタンになりやすい。自プロセスのウィンドウは復帰先にしない。
        target_hwnd = previous_target_hwnd or self._external_foreground_window()
        if target_hwnd and int(target_hwnd) in self._own_top_level_hwnds():
            target_hwnd = get_next_visible_window_after(target_hwnd, skip_current_process=True)
        if target_hwnd:
            self._last_search_target_hwnd = target_hwnd
        choices = self._load_vendor_search_presets(enabled_only=True)
        self._debug_search(f"open menu target={target_hwnd} title={self._window_title(target_hwnd)!r} choices={choices!r}")
        if not choices:
            QMessageBox.information(self, "ベンダー検索", "有効なベンダー検索プリセットがありません。")
            return

        # 設定画面などのモーダルダイアログが開いている場合、メインウィンドウを親にした
        # ツールウィンドウは表示されても操作できない。現在のモーダルを親にして前面操作可能にする。
        app = QApplication.instance()
        popup_parent = app.activeModalWidget() if app is not None else None
        if popup_parent is None or popup_parent is self:
            popup_parent = self

        self._search_string_test_dialog = SearchStringPasteTestDialog(target_hwnd, choices, popup_parent, owner=self)
        self._search_string_test_dialog.show()
        self._search_string_test_dialog.raise_()
        self._search_string_test_dialog.activateWindow()

    def _debug_search(self, message: str):
        print(f"[SEARCH DEBUG] {message}")

    def _set_clipboard_text_debug(self, reason: str, text: str):
        preview = text if len(text) <= 160 else text[:157] + "..."
        print(f"[CLIPBOARD DEBUG] setText reason={reason} text={preview!r}")
        if "monastery" in text.lower():
            import traceback
            print("[CLIPBOARD DEBUG] !!! monastery text is being set; stack follows")
            print("".join(traceback.format_stack(limit=12)).rstrip())
        QApplication.clipboard().setText(text)

    def _window_title(self, hwnd):
        if not hwnd or sys.platform != "win32":
            return ""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            length = user32.GetWindowTextLengthW(wintypes.HWND(int(hwnd)))
            if length <= 0:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(wintypes.HWND(int(hwnd)), buffer, length + 1)
            return buffer.value
        except Exception as exc:
            return f"<title error: {exc}>"

    def _clipboard_text_preview(self):
        try:
            text = QApplication.clipboard().text()
            if len(text) > 120:
                return text[:117] + "..."
            return text
        except Exception as exc:
            return f"<clipboard error: {exc}>"

    def _own_top_level_hwnds(self) -> set[int]:
        app = QApplication.instance()
        own_hwnds = set()
        if app is not None:
            for widget in app.topLevelWidgets():
                try:
                    own_hwnds.add(int(widget.winId()))
                except RuntimeError:
                    pass
        return own_hwnds

    def _external_foreground_window(self):
        foreground = get_foreground_window()
        if foreground and int(foreground) in self._own_top_level_hwnds():
            return get_next_visible_window_after(foreground, skip_current_process=True)
        return foreground

    def _vendor_search_presets_path(self, poe_version: str | None = None):
        version = poe_version or getattr(self, "poe_version", POE2)
        if version == POE1:
            return str(ConfigManager.get_user_data_path("vendor_search_presets_poe1.json"))
        # PoE2は旧 vendor_search_presets.json から新ファイルへ一度だけ移行し、以後は新名で入出力する。
        return str(ConfigManager.migrate_renamed_user_file(
            "vendor_search_presets.json",
            "vendor_search_presets_poe2.json",
        ))

    def _load_vendor_search_presets(self, enabled_only=False):
        path = self._vendor_search_presets_path(self.poe_version)
        presets = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                presets = data.get("presets", [])
            except Exception as e:
                print(f"[VENDOR SEARCH] Failed to load presets: {e}")
        if not presets:
            presets = VendorSearchPresetDialog.POE1_DEFAULT_PRESETS if self.poe_version == POE1 else VendorSearchPresetDialog.DEFAULT_PRESETS
        normalized = []
        for preset in presets:
            name = str(preset.get("name", "")).strip()
            query = str(preset.get("query", "")).strip()
            enabled = bool(preset.get("enabled", True))
            if not query:
                continue
            if enabled_only and not enabled:
                continue
            normalized.append({"name": name or query, "query": query, "enabled": enabled})
        return normalized

    def open_vendor_search_presets(self):
        """ベンダー検索プリセット編集ダイアログをトグル表示"""
        if hasattr(self, '_vendor_search_dialog') and self._vendor_search_dialog is not None:
            if self._vendor_search_dialog.isVisible():
                self._vendor_search_dialog.close()
                return
            self._vendor_search_dialog.show()
            self._vendor_search_dialog.raise_()
            return
        self._vendor_search_dialog = VendorSearchPresetDialog(
            self,
            presets_path=self._vendor_search_presets_path(self.poe_version),
            poe_version=self.poe_version,
        )
        self._vendor_search_dialog.show()

    # --- PoE検索欄貼り付け ---
    def paste_text_to_poe_search(self, text: str, target_hwnd=None):
        """対象ウィンドウへ戻して Ctrl+F → 検索文字列貼り付けを行う。"""
        if not text:
            return
        target_hwnd = target_hwnd or getattr(self, "_last_search_target_hwnd", None)
        if not target_hwnd:
            target_hwnd = self._external_foreground_window()
        elif int(target_hwnd) in self._own_top_level_hwnds():
            target_hwnd = get_next_visible_window_after(target_hwnd, skip_current_process=True)
        clipboard = QApplication.clipboard()
        self._set_clipboard_text_debug("paste_text_to_poe_search", text)
        QApplication.processEvents()
        time.sleep(0.05)

        if not target_hwnd:
            QMessageBox.warning(self, "検索文字列の貼り付け", "復帰先ウィンドウを取得できませんでした。文字列はクリップボードへコピー済みです。")
            return

        if not focus_window(target_hwnd, wait_seconds=0.45):
            QMessageBox.warning(
                self,
                "検索文字列の貼り付け",
                "元のウィンドウを前面化できませんでした。文字列はクリップボードへコピー済みです。",
            )
            return

        self._last_search_target_hwnd = target_hwnd
        QTimer.singleShot(450, lambda: self._paste_to_poe_search_field(text))

    def _paste_to_poe_search_field(self, text: str):
        try:
            controller = pynput_keyboard.Controller()
            ctrl = pynput_keyboard.Key.ctrl

            def tap(key):
                controller.press(key)
                controller.release(key)

            with controller.pressed(ctrl):
                tap('f')
            time.sleep(0.20)
            with controller.pressed(ctrl):
                tap('v')
            time.sleep(0.08)
            print(f"[POE SEARCH] pasted: {text}")
        except Exception as exc:
            print(f"[POE SEARCH] paste failed: {exc}")

    def search_gem_in_poe(self, gem_name: str):
        """ジェム取得リストのジェム名クリックからPoE検索欄へ貼り付ける。"""
        self.paste_text_to_poe_search(gem_name)

    # --- チャットコマンド ---
    def execute_chat_command(self, command: str):
        """PoEのチャットにコマンドを送信する。IMEの入力モードに左右されないよう貼り付けで送る。"""
        if not command:
            return
        print(f"[CHAT COMMAND] Requested: {command} search_in_progress={getattr(self, '_search_paste_in_progress', False)} clipboard_before={self._clipboard_text_preview()!r}")
        if getattr(self, "_search_paste_in_progress", False):
            print(f"[CHAT COMMAND] Ignored during search paste: {command}")
            return
        try:
            clipboard = QApplication.clipboard()
            original_mime = self._clone_clipboard_mime_data(clipboard.mimeData())
            self._set_clipboard_text_debug("execute_chat_command", command)

            controller = pynput_keyboard.Controller()

            def tap(key):
                controller.press(key)
                controller.release(key)

            tap(pynput_keyboard.Key.enter)
            time.sleep(0.05)
            with controller.pressed(pynput_keyboard.Key.ctrl):
                tap('v')
            time.sleep(0.05)
            tap(pynput_keyboard.Key.enter)

            # Ctrl+V処理が終わったあと、ユーザーのクリップボードをできるだけ元に戻す。
            QTimer.singleShot(500, lambda: clipboard.setMimeData(original_mime))
            print(f"[CHAT COMMAND] Sent: {command}")
        except Exception as e:
            print(f"[CHAT COMMAND] Failed: {e}")

    def _clone_clipboard_mime_data(self, source):
        """QClipboardの内容を復元用にコピーする。主要な形式を保持する。"""
        clone = QMimeData()
        if source is None:
            return clone
        for fmt in source.formats():
            clone.setData(fmt, source.data(fmt))
        if source.hasText():
            clone.setText(source.text())
        if source.hasHtml():
            clone.setHtml(source.html())
        if source.hasUrls():
            clone.setUrls(source.urls())
        if source.hasImage():
            clone.setImageData(source.imageData())
        if source.hasColor():
            clone.setColorData(source.colorData())
        return clone

    # --- ログアウト（TCP切断） ---
    def execute_logout(self):
        """TCP切断によるログアウト"""
        if not self.config.get("logout_enabled", True):
            return
        from src.utils.tcp_disconnect import disconnect_poe
        success, msg = disconnect_poe()
        if success:
            print(f"[LOGOUT] {msg}")
        else:
            print(f"[LOGOUT] Failed: {msg}")
            if "管理者権限" in msg:
                QMessageBox.warning(
                    self, "ログアウトマクロ",
                    "ログアウト機能を使用するためには、ぽえなびを「管理者として実行」する必要があります"
                )

    # --- クリックスルー ---
    def toggle_click_through(self):
        """クリックスルーのON/OFF切替"""
        self.click_through = not getattr(self, 'click_through', False)
        if sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if self.click_through:
                style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # フラグ変更を即座に反映
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        
        # 視覚的フィードバック
        self._update_click_through_label()
        hotkey = self.config.get('hotkeys', {}).get('click_through', DEFAULT_CLICK_THROUGH_HOTKEY)
        if self.click_through:
            print(f"[INFO] クリックスルー ON（{hotkey}で解除）")
        else:
            print(f"[INFO] クリックスルー OFF（{hotkey}でON）")

    def _update_click_through_label(self):
        """クリックスルー状態の案内表示を更新する。"""
        if not hasattr(self, "click_through_label"):
            return
        hotkey = self.config.get('hotkeys', {}).get('click_through', DEFAULT_CLICK_THROUGH_HOTKEY)
        if getattr(self, 'click_through', False):
            self.click_through_label.setText(f"🔓 クリックスルーON（{hotkey}で解除）")
            self.click_through_label.setStyleSheet("color: #ff9944; font-size: 14px; font-weight: bold;")
        else:
            self.click_through_label.setText(f"クリックスルーOFF（{hotkey}でON）")
            self.click_through_label.setStyleSheet("color: rgba(176, 255, 123, 0.45); font-size: 12px; font-weight: normal;")
        self.click_through_label.setVisible(True)

    # --- レベルガイド ---
    def _is_town_zone(self, zone_name: str) -> bool:
        """街エリアかどうか判定"""
        town_zones = self.town_zones_by_version.get(self.poe_version, [])
        return zone_name in town_zones
    
    def _get_zone_id(self, zone_name: str) -> str | None:
        """zone_dataからエリア名でIDを検索。part2_modeに応じてAct6-10/Act1-5を優先"""
        # Act10フラグが立っている場合、志す者の広場はAct10を優先
        if getattr(self, '_in_act10', False) and zone_name in ("志す者の広場", "Aspirants' Plaza"):
            for z in self.zone_data.get("Act 10", []):
                if z["zone"] == zone_name:
                    return z.get("id")
        
        if self.part2_mode:
            search_order = [k for k in self.zone_data if k in ("Act 6","Act 7","Act 8","Act 9","Act 10")]
            search_order += [k for k in self.zone_data if k not in search_order]
        else:
            search_order = [k for k in self.zone_data if k in ("Act 1","Act 2","Act 3","Act 4","Act 5")]
            search_order += [k for k in self.zone_data if k not in search_order]
        
        for act_name in search_order:
            for z in self.zone_data.get(act_name, []):
                if z["zone"] == zone_name or z.get("zone_en") == zone_name:
                    return z.get("id")
        return None
    
    def _format_zone_display_name(self, zone_name: str) -> str:
        """表示用のエリア名表記を整える"""
        return re.sub(r"^アクト\s*([0-9０-９]+)$", r"Act \1", zone_name)

    def _sync_gem_tracker_act_from_zone_act(self, act_name: str | None):
        """現在エリアのActにジェム取得リストを自動追従させる。"""
        if self.poe_version != POE1 or not act_name:
            return
        m = re.search(r"Act\s*(\d+)", act_name)
        if not m:
            return
        act = int(m.group(1))
        if not 1 <= act <= 10:
            return
        self.current_zone_act = act
        if hasattr(self, "gem_tracker"):
            self.gem_tracker.set_current_act(act)
        if self.gem_tracker_popup is not None:
            self.gem_tracker_popup.gem_tracker.set_current_act(act)

    def on_zone_entered(self, zone_name: str, actual_entry: bool = True):
        with measure("zone update"):
            return self._handle_zone_entered(zone_name, actual_entry)

    def _handle_zone_entered(self, zone_name: str, actual_entry: bool = True):
        """エリア入場検知

        actual_entry=False はレベルアップ等による現在エリア表示の再評価用。
        訪問回数・自動ラップ・マップ自動表示など、実際のエリア移動時だけの副作用を抑止する。
        """
        display_zone_name = self._format_zone_display_name(zone_name)
        print(
            f"[DEBUG] ENTER start: zone={zone_name}, actual_entry={actual_entry}, "
            f"poe={self.poe_version}, restoring={self._restoring}, "
            f"last_before={getattr(self, '_last_visit_key', None)}, "
            f"visited_town_before={getattr(self, '_visited_town', False)}"
        )
        self.current_zone = zone_name
        if actual_entry and self.is_running and not self._restoring:
            self.segment_recorder.record_entry(
                self._get_zone_id(zone_name) or zone_name,
                zone_name,
                self.get_elapsed_time(),
            )
            self._update_segment_summary()
        if actual_entry and self.poe_version == POE2 and zone_name in ("川岸", "The Riverbank") and not self._restoring:
            self.clear_progress_flags()
            self.player_level = 1
            self.level_label.setText("キャラLv. 1")

        # 自動ラップ判定（街エリアでも実行 — 橋の野営地/オリアスの船着場がトリガー）
        if actual_entry and not self._restoring:
            self._handle_interlude_lap_progress(zone_name)
            self._try_auto_lap(zone_name)

        # PoE2クリア後のジッグラトの避難所は通常ガイド更新を行わない
        if self.poe_version == POE2 and zone_name in ("ジッグラトの避難所", "The Ziggurat Refuge"):
            if actual_entry:
                self._visited_town = True
            self.zone_label.setText(f"🏠 {display_zone_name}")
            self.advice_label.setText("")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
            return

        # 街エリアの場合はゾーン名表示のみ更新、ガイド・マップは前のまま維持
        # （visit_overrideもリセットしない — 街を挟んでも手動切替を維持）
        if self._is_town_zone(zone_name):
            if actual_entry:
                self._visited_town = True  # 街通過フラグ（always_count_zones用）
            print(
                f"[DEBUG] TOWN: zone={zone_name}, actual_entry={actual_entry}, "
                f"set_visited_town={actual_entry}, last_kept={getattr(self, '_last_visit_key', None)}, "
                f"counts={self.zone_visit_counts}"
            )
            if actual_entry and self.poe_version == POE1:
                self._save_progress_flags()
            self.zone_label.setText(f"🏠 {display_zone_name}")
            if hasattr(self, "mini_navi_overlay") and self._is_mini_navi_available():
                self.mini_navi_overlay.show_last_content_or_waiting()
            # Labクリア後の街帰還 → 志す者の広場の2回目ガイドを表示
            if actual_entry and self._in_lab and self._lab_zone_id:
                self._in_lab = False
                self.advice_label.setText("🏛️ Labクリア — 次のガイドを表示中")
                self.advice_label.setStyleSheet("color: #ffc832; font-size: 12px;")
                # 志す者の広場のvisitカウントを増やす
                self.zone_visit_counts[self._lab_zone_id] = self.zone_visit_counts.get(self._lab_zone_id, 1) + 1
                visit_num = self.zone_visit_counts[self._lab_zone_id]
                lab_zone_name = zone_name  # 日本語/英語どちらでも対応
                self._update_guide_and_map(lab_zone_name, self._lab_zone_id, visit_num)
                self._lab_zone_id = None
            else:
                self.advice_label.setText("（街エリア — ガイドは前のエリアを表示中）")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
            return
        
        # 訪問回数オーバーライドをリセット（街以外のゾーン移動で自動に戻る）
        if actual_entry and self.visit_override is not None:
            self.visit_override = None
            self._update_visit_btn()
        
        # 荒廃した広場(Act10固有)入場 → Act10フラグON
        if actual_entry and zone_name in ("荒廃した広場", "The Ravaged Square") and not self._restoring:
            self._in_act10 = True
        
        # 黄昏の岸辺入場 → 新キャラ判定フラグON（Lv2検知でリセット確定）
        if actual_entry and zone_name in ("黄昏の岸辺", "The Twilight Strand") and not self._restoring:
            self._twilight_strand_entered = True
        
        # C: Part2固有エリアに入場 → 自動切替
        if actual_entry and not self.part2_mode and zone_name in self.part2_only_zones:
            self._set_part2(True)
        
        # zone_id検索
        zone_id = self._get_zone_id(zone_name)
        
        # Lab処理: 志す者の広場に入場 → Labフラグ設定
        _lab_zone_ids = {"act4_area3", "act8_area2", "act10_area8"}
        if actual_entry and zone_id in _lab_zone_ids and not self._restoring:
            self._in_lab = True
            self._lab_zone_id = zone_id
        elif actual_entry and self._in_lab and zone_id and zone_id not in _lab_zone_ids:
            # Lab中に既知の別エリアに入った → Labフラグ解除
            self._in_lab = False
            self._lab_zone_id = None
        elif actual_entry and self._in_lab and not zone_id:
            # Lab中に未知のエリア（Lab内部）→ ガイド更新スキップ
            self.zone_label.setText(f"📍 {display_zone_name}")
            self.advice_label.setText("🏛️ Lab — ガイドは前のエリアを表示中")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
            return
        
        # monster_levels.jsonからデータ取得
        monster_info = self.monster_levels.get(zone_id) if zone_id else None
        
        # monster_levels.jsonのexcludeチェック
        if monster_info and "exclude" in monster_info:
            exclude_type = monster_info["exclude"]
            if exclude_type == "town":
                # 街扱い — 既存の街処理と同じ
                self.zone_label.setText(f"🏠 {display_zone_name}")
                self.advice_label.setText("（街エリア — ガイドは前のエリアを表示中）")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
                return
            elif exclude_type == "boss":
                # ボスエリア — ペナルティ判定スキップ
                self.current_zone = zone_name
                act_name, _ = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
                act_prefix = f"{act_name} — " if act_name else ""
                self.zone_label.setText(f"📍 {act_prefix}{display_zone_name}")
                self.advice_label.setText("⚔️ ボスエリア")
                self.advice_label.setStyleSheet("color: #ff9944; font-size: 12px;")
                # ガイド・マップ更新は続行
                self._update_guide_and_map(zone_name, zone_id, 1, zone_changed=actual_entry)
                return
            elif exclude_type == "non_combat":
                # 非戦闘エリア — ペナルティ判定スキップ
                self.current_zone = zone_name
                act_name, _ = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
                act_prefix = f"{act_name} — " if act_name else ""
                self.zone_label.setText(f"📍 {act_prefix}{display_zone_name}")
                self.advice_label.setText("🏛️ 非戦闘エリア")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
                self._update_guide_and_map(zone_name, zone_id, 1, zone_changed=actual_entry)
                return
        
        # 訪問回数カウント（zone_id基準）
        visit_key = zone_id if zone_id else zone_name
        last_visit_key = getattr(self, '_last_visit_key', None)
        # 街を挟んでも常にカウントするエリア（ポータルで街に戻って再入場するパターン）
        always_count_zones = {"act5_area5", "act10_area3", "act8_area20", "act9_area2"}  # イノセンスの間, 荒廃した広場, 隠れた裏道, ヴァスティリ砂漠
        if self._restoring:
            # 復元時はカウントアップしないが、未記録なら1回目として記録（次回訪問で2回目になるように）
            self._last_visit_key = visit_key
            if visit_key not in self.zone_visit_counts:
                self.zone_visit_counts[visit_key] = 1
            visit_num = self.zone_visit_counts.get(visit_key, 1)
            if self.poe_version == POE1:
                self._save_progress_flags()
        elif not actual_entry:
            # レベルアップ等の表示再評価では、訪問回数や街通過フラグを変更しない
            visit_num = self.zone_visit_counts.get(visit_key, 1)
        else:
            # カウントアップ判定:
            # 1. 別ゾーンから来た場合 → カウントアップ（通常の訪問）
            # 2. 同一ゾーン連続の場合 → always_count_zones かつ街経由のみカウントアップ
            #    （ログ重複や街経由の回復戻りではカウントしない）
            should_count = False
            visited_town = getattr(self, '_visited_town', False)
            if visit_key != last_visit_key:
                # 別ゾーンからの入場 → カウントアップ
                should_count = True
            else:
                # 同一ゾーン再入場 → always_count_zones かつ街を経由した場合のみ
                if visit_key in always_count_zones and visited_town:
                    should_count = True
            print(
                f"[DEBUG] COUNT before: zone={zone_name}, zone_id={zone_id}, visit_key={visit_key}, "
                f"last_visit_key={last_visit_key}, visited_town={visited_town}, "
                f"should_count={should_count}, counts_before={self.zone_visit_counts}"
            )
            
            if should_count:
                self.zone_visit_counts[visit_key] = self.zone_visit_counts.get(visit_key, 0) + 1
            
            # 街通過フラグをリセット（街以外のゾーンに入ったらクリア）
            self._visited_town = False
            self._last_visit_key = visit_key
            visit_num = self.zone_visit_counts.get(visit_key, 1)
            print(
                f"[DEBUG] COUNT after: zone={zone_name}, visit_key={visit_key}, "
                f"last_after={self._last_visit_key}, visited_town_after={self._visited_town}, "
                f"visit_num={visit_num}, counts_after={self.zone_visit_counts}"
            )
            if self.poe_version == POE1:
                self._save_progress_flags()
        if actual_entry and self.poe_version == POE1:
            # Act1 海底通路 到達フラグ。海岸へ戻った後のガイド切替に使う。
            if zone_id == "act1_area4":
                self.set_progress_flag("act1_submergedpassage_enter")
            # Act1 水没した海底洞窟 到達フラグ。海底通路の復帰後ガイド切替に使う。
            if zone_id == "act1_area9":
                self.set_progress_flag("act1_floodeddepths_enter")
            # Act1 船の墓場の洞窟 到達フラグ。船の墓場の復帰後ガイド切替に使う。
            if zone_id == "act1_area13":
                self.set_progress_flag("act1_shipgraveyardcave_enter")
            # Act2 西の森 到達フラグ。川沿いの道の復帰後ガイド切替に使う。
            if zone_id == "act2_area8":
                self.set_progress_flag("act2_westernforest_enter")
            # Act2 編む者の巣穴/湿地 到達フラグ。西の森の復帰後ガイド切替に使う。
            if zone_id == "act2_area9":
                self.set_progress_flag("act2_weaverschambers_enter")
            if zone_id == "act2_area14":
                self.set_progress_flag("act2_wetlands_enter")
            # Act3 ソラリス/ルナリス第二層 到達フラグ。黒檀の兵舎の復帰後ガイド切替に使う。
            if zone_id == "act3_area10":
                self.set_progress_flag("act3_solaris_enter")
            if zone_id == "act3_area13":
                self.set_progress_flag("act3_lunaris_enter")
            # Act4 大闘技場/カオムの要塞 到達フラグ。水晶鉱脈の復帰後ガイド切替に使う。
            if zone_id == "act4_area8":
                self.set_progress_flag("act4_grandarena_enter")
            if zone_id == "act4_area10":
                self.set_progress_flag("act4_kaomstronghold_enter")
            # Act5 聖廟 到達フラグ。破壊された広場の復帰後ガイド切替に使う。
            if zone_id == "act5_area9":
                self.set_progress_flag("act5_reliquary_enter")
            # Act6 湿地 到達フラグ。Act6 川沿いの道の復帰後ガイド切替に使う。
            # 同名のAct2「湿地」と混同しないよう、zone_idでAct6のみ判定する。
            if zone_id == "act6_area11":
                self.set_progress_flag("act6_wetlands_enter")
            # Act7 地下聖堂 到達フラグ。Act7 十字路の復帰後ガイド切替に使う。
            # Act2の地下聖堂と混同しないよう、zone_idでAct7のみ判定する。
            if zone_id == "act7_area4":
                self.set_progress_flag("act7_crypt_enter")
            # Act7 マリガロの聖域 到達フラグ。Act6 囚人の門のAct7後ガイド切替に使う。
            if zone_id == "act7_area6":
                self.set_progress_flag("act7_maligarosanctum_enter")
            # Act7 恐怖の密林 到達フラグ。Act7 北の森の復帰後ガイド切替に使う。
            # 同名/類似名エリアと混同しないよう、zone_idでAct7のみ判定する。
            if zone_id == "act7_area12":
                self.set_progress_flag("act7_dreadthicket_enter")
            # Act8 ソラリス/ルナリス寺院 第二層 到達フラグ。
            # Act3にも同名エリアがあるため、zone_idでAct8のみ判定する。
            if zone_id == "act8_area11":
                self.set_progress_flag("act8_solaristemple2_enter")
            if zone_id == "act8_area16":
                self.set_progress_flag("act8_lunaristemple2_enter")
            # Act8 血の水道橋 到達フラグ。通常ルートのルナリスの中央広場で
            # 帰還後ガイドを切り替えるために使う。
            if zone_id == "act8_area17":
                self.set_progress_flag("act8_bloodaqueduct_enter")
            # Act9 オアシス 到達フラグ。Act9 ヴァスティリ砂漠の復帰後ガイド切替に使う。
            if zone_id == "act9_area3":
                self.set_progress_flag("act9_oasis_enter")
            # Act10 奴隷管理区画/納骨堂/冒涜された広間 到達フラグ。Act10 荒廃した広場の復帰後ガイド切替に使う。
            # Act5の同名エリアと混同しないよう、zone_idでAct10のみ判定する。
            if zone_id == "act10_area4":
                self.set_progress_flag("act10_controlblocks_enter")
            if zone_id == "act10_area5":
                self.set_progress_flag("act10_ossuary_enter")
            if zone_id == "act10_area7":
                self.set_progress_flag("act10_desecratedchambers_enter")
        if actual_entry and visit_num == 1:
            if self.poe_version == POE2:
                if zone_name in ("裏切り者の通路", "Traitor's Passage"):
                    self.set_progress_flag("act2_traitor_clear")
                if zone_name in ("ジクアニの聖所", "Jiquani's Sanctum"):
                    self.set_progress_flag("act3_zicoatl_dead")
                if zone_name in ("吠える洞窟", "Howling Caves"):
                    self.set_progress_flag("interlude3_yeti_dead")
        print(f"[DEBUG] zone={zone_name}, id={zone_id}, visit_num={visit_num}, restoring={self._restoring}, counts={self.zone_visit_counts}")
        
        self.current_zone = zone_name
        # 自動ラップ判定は on_zone_entered() 冒頭で実行済み
        act_name, zone_level = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
        self._sync_gem_tracker_act_from_zone_act(act_name)
        
        # monster_levels.jsonからモンスターレベルを取得（優先）
        monster_lv = None
        if monster_info and monster_info.get("lv", 0) > 0 and "exclude" not in monster_info:
            monster_lv = monster_info["lv"]
        
        # 2回目以降はガイドデータ内の適正レベル上書きをチェック
        if visit_num >= 2 and zone_id:
            guide_level = get_zone_guide_level(self.guide_data, zone_id, visit=visit_num, config=self.config)
            if guide_level:
                zone_level = guide_level
                # ガイドデータにレベル上書きがある場合はそちらを優先
                monster_lv = guide_level
        
        # 表示用レベル決定: monster_levels優先、なければzone_data
        display_lv = monster_lv if monster_lv else zone_level
        is_town_zone = self._is_town_zone(zone_name)
        
        if is_town_zone:
            self.zone_label.setText(f"📍 {display_zone_name}")
            self.advice_label.setText("")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        elif act_name and display_lv:
            visit_label = ""
            lv_prefix = "MLv" if monster_lv else "Lv"
            self.zone_label.setText(f"📍 {act_name} — {display_zone_name} ({lv_prefix}.{display_lv}){visit_label}")
            msg, color = get_level_advice(self.player_level, display_lv)
            self.advice_label.setText(msg)
            self.advice_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        else:
            self.zone_label.setText(f"📍 {display_zone_name}")
            if act_name:
                self.advice_label.setText("（エリアレベルは攻略順で変動するため固定表示なし）")
            else:
                self.advice_label.setText("（適正レベル未登録エリア）")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        
        # 攻略ガイド・マップ更新
        self._update_guide_and_map(zone_name, zone_id, visit_num, zone_changed=actual_entry, exp_level=display_lv)
    
    def _mini_navi_exp_guide(self, enemy_level: int | None, zone_id: str | None = None) -> dict | None:
        if zone_id:
            monster_info = self.monster_levels.get(zone_id) if isinstance(getattr(self, "monster_levels", None), dict) else None
            if isinstance(monster_info, dict) and monster_info.get("exclude"):
                return None
        if not enemy_level:
            return None
        player_level = int(getattr(self, "player_level", 1) or 1)
        msg, _color = get_level_advice(player_level, int(enemy_level))
        if "🔴" in msg:
            status = "🔴 ペナ発生"
        elif "🟢" in msg:
            status = "🟢 最適"
        else:
            status = "🟡 ペナなし"
        return {"player_level": player_level, "enemy_level": int(enemy_level), "status": status}

    def _update_guide_and_map(self, zone_name: str, zone_id: str | None, visit_num: int, zone_changed: bool = False, exp_level: int | None = None):
        """攻略ガイドとマップ画像を更新"""
        self._update_area_note(zone_name, zone_id)
        self._update_poelab_link_visibility(zone_id)
        # 訪問回数オーバーライド適用
        effective_visit = self.visit_override if self.visit_override is not None else visit_num
        if exp_level is None:
            _act_name, fallback_zone_level = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
            exp_level = fallback_zone_level
            if effective_visit >= 2 and zone_id:
                guide_level = get_zone_guide_level(self.guide_data, zone_id, visit=effective_visit, config=self.config)
                if guide_level:
                    exp_level = guide_level
        if zone_id:
            guide = get_zone_guide(self.guide_data, zone_id, visit=effective_visit, config=self.config, active_flags=self.progress_flags)
        else:
            guide = None
        
        if guide:
            html = format_guide_html(
                guide,
                font_size=self.guide_font_size,
                show_direction=(self.poe_version == POE1),
                guide_detail_level=self.config.get("guide_detail_level", "beginner") if self.poe_version == POE2 else "beginner",
            )
            self.guide_text_label.setText(html)
            self.guide_text_label.setStyleSheet(f"color: #dddddd; font-size: {self.guide_font_size}px; background: transparent;")
            if hasattr(self, "mini_navi_overlay"):
                if self._is_mini_navi_available():
                    overlay_config = self.config.get("mini_guide_overlay", {})
                    display_mode = overlay_config.get("display_mode", "standard") if isinstance(overlay_config, dict) else "standard"
                    max_lines = None if display_mode == "compact" else overlay_config.get("max_lines", 4)
                    self.mini_navi_overlay.update_content(
                        get_mini_navi_content(guide, max_lines=max_lines),
                        self._mini_navi_exp_guide(exp_level, zone_id=zone_id),
                        zone_id=zone_id,
                        has_area_note=bool(self._current_area_note.strip()),
                    )
                else:
                    self.mini_navi_overlay.hide()
        else:
            self.guide_text_label.setText(f"「{zone_name}」のガイドデータはありません")
            self.guide_text_label.setStyleSheet(f"color: #666666; font-size: {self.guide_font_size}px; background: transparent;")
            if hasattr(self, "mini_navi_overlay"):
                self.mini_navi_overlay.hide()
        
        # マップ画像は日本語フォルダ名で検索（英語クライアント対応）
        map_zone_name = zone_name
        if zone_id:
            for act_zones in self.zone_data.values():
                for z in act_zones:
                    if z.get("id") == zone_id:
                        map_zone_name = z["zone"]  # 日本語名
                        break
        # ルート設定を取得してマップ画像にも反映
        map_route = ""
        if zone_id:
            if zone_id.startswith("act3_"):
                r = ConfigManager.effective_poe1_route_act3(self.config)
                if r != "standard": map_route = r
            elif zone_id.startswith("act8_"):
                r = ConfigManager.effective_poe1_route_act8(self.config)
                if r != "standard": map_route = r
        defer_initial_auto_open = bool(self._restoring and zone_changed and self.map_thumbnail.auto_open)
        self.map_thumbnail.load_maps(
            map_zone_name,
            part2=self.part2_mode,
            zone_changed=(zone_changed and not defer_initial_auto_open),
            route=map_route,
            poe_version=get_poe_label(self.poe_version),
        )
        if defer_initial_auto_open and self.map_thumbnail.current_paths:
            self._pending_initial_map_auto_open = True
    
    def on_kitava_defeated(self):
        """PoE1 Act5相当の特別ラップイベント"""
        if self.poe_version != POE1:
            return
        if not self.part2_mode:
            print("[INFO] キタヴァ討伐を検知 — Act 6-10に切替")
            self._set_part2(True, update_guide=False)
        lap_num = get_special_lap_event(self.poe_version, "kitava_act5")
        if lap_num:
            self._auto_lap_kitava(lap_num)
    
    def on_act10_cleared(self):
        """最終クリアイベント → act10_area11（渇望の祭壇）ガイド表示 + 自動ラップ"""
        lap_num = get_special_lap_event(self.poe_version, "final_clear")
        if lap_num:
            self._auto_lap_kitava(lap_num)
        print(f"[INFO] {get_poe_label(self.poe_version)} の最終クリアを検知 — 渇望の祭壇ガイド表示")
        zone_name = "渇望の祭壇"
        zone_id = "act10_area11"
        self.current_zone = zone_name
        self.zone_label.setText("📍 Act 10 — 渇望の祭壇")
        self.advice_label.setText("🎉 Act10クリア — クリア後ガイドを表示中")
        self.advice_label.setStyleSheet("color: #ffd700; font-size: 12px;")
        self._update_guide_and_map(zone_name, zone_id, 1, zone_changed=True)

    def on_poe2_act4_cleared(self):
        """PoE2 Act4クリアイベントによる自動ラップ"""
        lap_num = get_special_lap_event(self.poe_version, "act4_clear")
        if lap_num:
            self._auto_lap_kitava(lap_num)

    def _progress_flags_path(self):
        filename = get_progress_flags_filename(self.poe_version)
        if not filename:
            return None
        return str(ConfigManager.get_user_data_path(filename))

    def _save_progress_flags(self):
        path = self._progress_flags_path()
        if not path:
            return
        data = {"active_flags": sorted(self.progress_flags)}
        if self.poe_version == POE1:
            data.update({
                "zone_visit_counts": self.zone_visit_counts,
                "last_visit_key": getattr(self, "_last_visit_key", None),
                "visited_town": getattr(self, "_visited_town", False),
            })
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear_progress_flags(self):
        self.progress_flags = set()
        self.interlude_ready = set()
        if self.poe_version == POE1:
            self.zone_visit_counts = {}
            self._last_visit_key = None
            self._visited_town = False
        self._save_progress_flags()

    def _restore_progress_flags(self):
        self.progress_flags = set()
        if self.poe_version == POE1:
            self.zone_visit_counts = {}
            self._last_visit_key = None
            self._visited_town = False
        path = self._progress_flags_path()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.progress_flags = set(data.get('active_flags', []))
            if self.poe_version == POE1:
                counts = data.get('zone_visit_counts', {})
                self.zone_visit_counts = counts if isinstance(counts, dict) else {}
                self._last_visit_key = data.get('last_visit_key')
                self._visited_town = bool(data.get('visited_town', False))
        except Exception as e:
            print(f"[WARN] progress flags load failed [{self.poe_version}]: {e}")
            self.progress_flags = set()
            if self.poe_version == POE1:
                self.zone_visit_counts = {}
                self._last_visit_key = None
                self._visited_town = False

    def set_progress_flag(self, flag_name: str, enabled: bool = True):
        """進行フラグを更新し、必要ならガイド再評価する"""
        changed = False
        if enabled:
            if flag_name not in self.progress_flags:
                self.progress_flags.add(flag_name)
                changed = True
        else:
            if flag_name in self.progress_flags:
                self.progress_flags.discard(flag_name)
                changed = True
        if changed:
            self._save_progress_flags()
        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def on_level_up(self, char_name: str, level: int):
        """レベルアップ検知"""
        self.player_level = level
        self.level_label.setText(f"キャラLv. {level}")
        
        # 新キャラ判定: 黄昏の岸辺入場済み + Lv2 = ヒロック討伐 → visitカウントリセット
        if level == 2 and getattr(self, '_twilight_strand_entered', False):
            print("[INFO] 新キャラ確定（黄昏の岸辺 + Lv2）— visitカウント/進行フラグをリセット")
            self.clear_progress_flags()
            self._twilight_strand_entered = False
            self.visit_override = None
            self._update_visit_btn()
            self._in_act10 = False
            self._set_part2(False)  # Act 1-5に戻す
        
        # 現在のゾーン情報があれば再評価
        if self.current_zone:
            self.on_zone_entered(self.current_zone, actual_entry=False)
    
    def update_level_guide_display(self):
        """レベルガイド表示を更新"""
        if self.current_zone:
            self.on_zone_entered(self.current_zone, actual_entry=False)
    
    # --- ウィンドウ移動 & 下端リサイズ ---
    MIN_HEIGHT = 400
    
    def _detect_edge(self, pos):
        """マウス位置からリサイズ方向を検出"""
        m = self.EDGE_MARGIN
        edges = []
        if pos.x() <= m:
            edges.append('left')
        elif pos.x() >= self.width() - m:
            edges.append('right')
        if pos.y() <= m:
            edges.append('top')
        elif pos.y() >= self.height() - m:
            edges.append('bottom')
        return edges if edges else None

    def _edge_cursor(self, edges):
        if not edges:
            return Qt.ArrowCursor
        s = set(edges)
        if s == {'left'} or s == {'right'}:
            return Qt.SizeHorCursor
        if s == {'top'} or s == {'bottom'}:
            return Qt.SizeVerCursor
        if s == {'left', 'top'} or s == {'right', 'bottom'}:
            return Qt.SizeFDiagCursor
        if s == {'right', 'top'} or s == {'left', 'bottom'}:
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.window_locked:
                event.accept()
                return
            edges = self._detect_edge(event.position().toPoint())
            if edges:
                self.resize_edge = edges
                self.resize_start_geo = self.geometry()
                self.resize_start_pos = event.globalPosition().toPoint()
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.resize_edge and self.resize_start_geo:
            gpos = event.globalPosition().toPoint()
            dx = gpos.x() - self.resize_start_pos.x()
            dy = gpos.y() - self.resize_start_pos.y()
            geo = self.resize_start_geo
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            min_w = 300
            min_h = self.MIN_HEIGHT if hasattr(self, 'MIN_HEIGHT') else 400
            
            if 'right' in self.resize_edge:
                w = max(min_w, geo.width() + dx)
            if 'bottom' in self.resize_edge:
                h = max(min_h, geo.height() + dy)
            if 'left' in self.resize_edge:
                new_w = max(min_w, geo.width() - dx)
                x = geo.x() + geo.width() - new_w
                w = new_w
            if 'top' in self.resize_edge:
                new_h = max(min_h, geo.height() - dy)
                y = geo.y() + geo.height() - new_h
                h = new_h
            
            self.setGeometry(x, y, w, h)
            event.accept()
        elif event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
        else:
            if not self.window_locked:
                edges = self._detect_edge(event.position().toPoint())
                self.setCursor(QCursor(self._edge_cursor(edges)))

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        self.resize_edge = None
        self.resize_start_geo = None
        self.resize_start_pos = None
        self.setCursor(QCursor(Qt.ArrowCursor))

    # --- コンテキストメニュー ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        settings_action = menu.addAction("設定")
        settings_action.triggered.connect(self.open_settings)

        update_action = menu.addAction("アップデートを確認")
        update_action.triggered.connect(
            lambda: self._check_for_updates(manual=True)
        )
        
        menu.addSeparator()
        
        quit_action = menu.addAction("終了")
        quit_action.triggered.connect(self.close)
        
        menu.exec(event.globalPos())

    def open_memo(self):
        """メモダイアログをトグル表示"""
        if hasattr(self, '_memo_dialog') and self._memo_dialog is not None:
            if self._memo_dialog.isVisible():
                self._memo_dialog._save_and_close()
                return
            else:
                self._memo_dialog.show()
                self._memo_dialog.raise_()
                return
        # 初回: ダイアログ生成
        notes_filename = "notes_poe2.json" if self.poe_version == POE2 else "notes_poe1.json"
        notes_path = str(ConfigManager.get_user_data_path(notes_filename))
        self._memo_dialog = MemoDialog(self, notes_path=notes_path)
        self._memo_dialog.apply_opacity(
            self.config.get("window_opacity", 100),
            self.config.get("text_opacity", 100)
        )
        self._memo_dialog.show()
    
    def open_settings(self):
        dialog = SettingsDialog(self, self.config)
        if dialog.exec():
            # 設定保存
            previous_timer_size_setting = self.config.get("timer_size", "large")
            previous_always_on_top = self.config.get("always_on_top", True)
            new_settings = dialog.get_settings()
            self.config.update(new_settings)
            ConfigManager.save_config(self.config)
            if self.config.get("always_on_top", True) != previous_always_on_top:
                self._apply_window_flags()
            
            # ホットキー再登録
            self.register_hotkeys()
            self._update_click_through_label()
            
            # ログ監視の再設定
            active_version = self.config.get("poe_version", self.poe_version)
            client_log_paths = self.config.get("client_log_paths", {})
            log_path = client_log_paths.get(active_version, "")
            if log_path:
                self.log_watcher.set_log_path(log_path)
                self.log_watcher.start()
                # PoE1ルート未選択なら、初回セットアップ完了済みでもPoE1ログ設定時に表示する
                if active_version == POE1 and not self.config.get("poe1_route_selected", False):
                    self._show_route_selection_dialog()
                if not self.config.get("setup_completed"):
                    self.config["setup_completed"] = True
                    ConfigManager.save_config(self.config)
                # ログファイル未設定メッセージをクリア
                self.guide_text_label.setText("")
            
            # ゾーンデータ・ガイドデータ更新
            prev_version = self.poe_version
            self.poe_version = self.config.get("poe_version", POE1)
            self.lap_labels = get_lap_labels(self.poe_version)
            zone_master_data = load_zone_master_data()
            self.zone_data_by_version = zone_master_data["zone_data_by_version"]
            self.town_zones_by_version = zone_master_data["town_zones_by_version"]
            self.zone_data = self.zone_data_by_version.get(self.poe_version, {})
            self.log_watcher.set_poe_version(self.poe_version)
            self.setWindowTitle(f"ぽえなび [{get_poe_label(self.poe_version)}]")
            if prev_version != self.poe_version:
                self.lap_times = [None] * len(self.lap_labels)
                self.current_act = 1
                self.accumulated_time = 0.0
                self.update_text(0.0)
                self._rebuild_lap_ui()
                self._restore_timer_state()
                self._restore_progress_flags()
                self.update_lap_display()
                switched_log_path = self.config.get("client_log_paths", {}).get(self.poe_version, "")
                if switched_log_path:
                    self.log_watcher.set_log_path(switched_log_path)
                    self.log_watcher.start()
                if hasattr(self, '_memo_dialog') and self._memo_dialog is not None:
                    self._memo_dialog.close()
                    self._memo_dialog = None
                if hasattr(self, '_vendor_search_dialog') and self._vendor_search_dialog is not None:
                    self._vendor_search_dialog.close()
                    self._vendor_search_dialog = None
            
            # ガイドフォントサイズ更新
            self.guide_font_size = self.config.get("guide_font_size", 18)
            self.gem_tracker_toggle_btn.setVisible(self.poe_version == POE1)
            self.gem_tracker_frame.setVisible(self.poe_version == POE1 and self.gem_tracker_expanded)
            self.part2_btn.setVisible(self.poe_version == POE1)
            self._refresh_mini_navi_toggle()
            self._refresh_guide_detail_level_toggle()
            
            # タイマーサイズ更新
            new_timer_size_setting = self.config.get("timer_size", "large")
            if new_timer_size_setting == "off":
                if self.timer_size in self.TIMER_SIZES:
                    self.config["timer_size_before_off"] = self.timer_size
                self._set_timer_expanded(False)
                self.config["timer_expanded"] = False
                effective_timer_size = self._effective_timer_size(new_timer_size_setting)
            else:
                self.config["timer_size_before_off"] = new_timer_size_setting
                effective_timer_size = new_timer_size_setting
                if previous_timer_size_setting == "off":
                    self._set_timer_expanded(True)
                    self.config["timer_expanded"] = True
            if effective_timer_size != self.timer_size:
                self.timer_size = effective_timer_size
                self._apply_timer_size()
            ConfigManager.save_config(self.config)
            
            # ウィンドウロック更新
            self.window_locked = self.config.get("window_locked", False)
            # マップ自動表示更新
            self.map_thumbnail.auto_open = self.config.get("auto_open_map", False)
            self.map_thumbnail.auto_position = self.config.get("auto_position_map", True)
            # 透過率更新
            self._apply_bg_opacity(self.config.get("window_opacity", 100))
            self._apply_text_opacity(self.config.get("text_opacity", 100))
            if hasattr(self, "mini_navi_overlay"):
                self.mini_navi_overlay.apply_settings(refresh_window_flags=True)
            # メモダイアログにも透過率を反映
            if hasattr(self, '_memo_dialog') and self._memo_dialog is not None and self._memo_dialog.isVisible():
                self._memo_dialog.apply_opacity(
                    self.config.get("window_opacity", 100),
                    self.config.get("text_opacity", 100)
                )
            
            self.update_level_guide_display()
        
        # ガイドデータは常にリロード（ガイド編集Saveで即保存されるため、Cancelでも反映する）
        self.guide_data = load_guide_data(self.poe_version)
        # 現在表示中のガイドを再描画
        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def _main_window_flags(self):
        return _with_optional_always_on_top(Qt.FramelessWindowHint, self)

    def minimize_main_window(self):
        """みになび表示中は本体だけ隠し、それ以外は通常どおり最小化する。"""
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None and self._is_mini_navi_available() and overlay.isVisible():
            self.hide_for_mini_navi()
            return
        self.showMinimized()

    def hide_for_mini_navi(self):
        """ぽえなび本体だけを隠し、みになびの表示を維持する。"""
        self._hidden_for_mini_navi = True
        self.hide()
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None:
            overlay.show()
            overlay.raise_()
            overlay._sync_lock_button()

    def restore_from_mini_navi(self):
        """みになびだけの表示状態から、ぽえなび本体を復帰する。"""
        self._hidden_for_mini_navi = False
        self.showNormal()
        self.raise_()
        self.activateWindow()
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None:
            overlay._sync_lock_button()

    def _apply_window_flags(self):
        was_visible = self.isVisible()
        self.setWindowFlags(self._main_window_flags())
        if was_visible:
            self.show()
            
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_main_window_initialized", False):
            return
        if not getattr(self, "_initial_positioned", False):
            self._initial_positioned = True
            from PySide6.QtWidgets import QApplication
            
            snap_to_right = self.config.get("snap_to_right_edge", False)
            saved_geo = self.config.get("window_geometry")
            
            if snap_to_right:
                # モニター右端配置ON:
                # 保存済みの幅・高さ・Y位置を尊重し、Xだけ対象モニターの右端に合わせる。
                # Yは画面外にはみ出す場合のみ表示可能範囲内に補正する。
                if saved_geo:
                    screens = QApplication.screens()
                    idx = self._display_monitor_index
                    if screens and 0 <= idx < len(screens):
                        target_screen = screens[idx]
                    elif screens:
                        target_screen = screens[0]
                    else:
                        return
                    screen_geo = target_screen.availableGeometry()
                    w = saved_geo.get("width", 420)
                    h = saved_geo.get("height", 1200)
                    saved_y = saved_geo.get("y", screen_geo.top())
                    x = screen_geo.left() + screen_geo.width() - w
                    max_y = screen_geo.top() + screen_geo.height() - h
                    if max_y < screen_geo.top():
                        y = screen_geo.top()
                    else:
                        y = max(screen_geo.top(), min(saved_y, max_y))
                    self.setGeometry(x, y, w, h)
                else:
                    # 初回など保存済みジオメトリがない場合は従来どおり右端フル高さ
                    self._position_right_edge()
            elif saved_geo:
                # 保存済みジオメトリを復元
                x = saved_geo.get("x", 0)
                y = saved_geo.get("y", 0)
                w = saved_geo.get("width", 420)
                h = saved_geo.get("height", 1200)
                # 画面外チェック: 全スクリーンのunionに収まるか
                screens = QApplication.screens()
                if screens:
                    union = screens[0].availableGeometry()
                    for s in screens[1:]:
                        union = union.united(s.availableGeometry())
                    window_rect = QRect(x, y, w, h)
                    if union.intersects(window_rect):
                        self.setGeometry(x, y, w, h)
                    else:
                        # 画面外 → デフォルト（右端配置）
                        self._position_right_edge()
                else:
                    self.setGeometry(x, y, w, h)
            else:
                # デフォルト: 右端配置
                self._position_right_edge()

            if getattr(self, "_pending_initial_map_auto_open", False):
                self._pending_initial_map_auto_open = False
                QTimer.singleShot(50, self.map_thumbnail.open_first_map)
    
    def _position_right_edge(self):
        """デフォルトの右端配置"""
        from PySide6.QtWidgets import QApplication
        screens = QApplication.screens()
        if not screens:
            return
        target_screen = screens[0]
        geo = target_screen.availableGeometry()
        actual_w = self.frameGeometry().width()
        win_h = geo.height()
        self.resize(self.width(), win_h)
        x = geo.left() + geo.width() - actual_w
        y = geo.top()
        self.move(x, y)

    def closeEvent(self, event):
        # 起動時アップデートでは、保存済みジオメトリを復元する前の仮サイズ
        # (420x1200) のまま終了する。初期化・初期配置が完了した通常終了時だけ
        # 位置とサイズを保存し、ユーザー設定を仮サイズで上書きしない。
        if (
            getattr(self, "_main_window_initialized", False)
            and getattr(self, "_initial_positioned", False)
        ):
            # 他のウィンドウが終了直前に保存した設定（例: map_viewer_width/height）を
            # 古い self.config で上書きしないよう、最新configを読み直して必要キーだけ更新する。
            geo = self.geometry()
            config = ConfigManager.load_config()
            config["window_geometry"] = {
                "x": geo.x(),
                "y": geo.y(),
                "width": geo.width(),
                "height": geo.height(),
            }
            ConfigManager.save_config(config)
            self.config = config

        # みになびは本体と独立したトップレベルウィンドウなので、アプリ終了時は
        # 明示的に一緒に閉じる。
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None:
            overlay.close()

        keyboard_listener = getattr(self, "keyboard_listener", None)
        if keyboard_listener:
            keyboard_listener.stop()
        log_watcher = getattr(self, "log_watcher", None)
        if log_watcher is not None:
            log_watcher.stop()
        super().closeEvent(event)
