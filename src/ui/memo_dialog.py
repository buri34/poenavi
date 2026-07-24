import json
import os

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import Styles
from src.ui.window_flags import _with_optional_always_on_top


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
