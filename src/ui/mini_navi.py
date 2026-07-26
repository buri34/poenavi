import html
import os
import re
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from src.ui.window_flags import _with_optional_mini_always_on_top
from src.utils.config_manager import ConfigManager


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
        buttons = [self.restore_button]
        if show_lock_button:
            buttons.append(self.button)
        width = sum(button.width() for button in buttons) + 4 * (len(buttons) - 1)
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
    COMPACT_DEFAULT_WIDTH = 600
    COMPACT_DEFAULT_HEIGHT = 110

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
