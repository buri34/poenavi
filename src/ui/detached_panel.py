"""切り離しパネル用の独立ウィンドウ。"""

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QSizePolicy, QVBoxLayout, QWidget

from src.ui.styles import Styles
from src.utils.i18n import tr_ui


class DetachedPanelWindow(QWidget):
    """本体から外したパネルを表示する、移動・リサイズ可能な独立ウィンドウ。"""

    def __init__(self, panel_id, title, content, return_callback, state_callback):
        super().__init__(None)
        self.panel_id = panel_id
        self.content = content
        self._return_callback = return_callback
        self._state_callback = state_callback
        self._returning = False
        self._drag_offset = None
        self._resize_edges = frozenset()
        self._resize_start_position = None
        self._resize_start_geometry = None
        self._resize_margin = 8
        self._native_resize_active = False
        self.window_locked = False
        self._content_size_policy = content.sizePolicy()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {Styles.BACKGROUND_COLOR}; color: {Styles.TEXT_COLOR};")
        self.setMinimumSize(320, 180)
        self.resize(max(320, content.sizeHint().width()), max(180, content.sizeHint().height()))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = QWidget()
        self.header.setAttribute(Qt.WA_StyledBackground, True)
        self.header.setCursor(QCursor(Qt.OpenHandCursor))
        self.header.setStyleSheet(
            f"background-color: {Styles.BACKGROUND_COLOR}; border-bottom: 1px solid rgba(176, 255, 123, 0.35);"
        )
        self.header.installEventFilter(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 5, 8, 5)
        self.title_label = QLabel(title)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        return_button = QPushButton(tr_ui("↙ 本体へ戻す"))
        return_button.setStyleSheet(Styles.BUTTON)
        return_button.setCursor(QCursor(Qt.PointingHandCursor))
        return_button.clicked.connect(self.return_to_main)
        header_layout.addWidget(return_button)
        self.header.setFixedHeight(self.header.sizeHint().height())
        layout.addWidget(self.header)
        layout.addWidget(content, stretch=1)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(18, 18)
        self.resize_grip.setToolTip(tr_ui("ドラッグしてサイズ変更"))
        self.resize_grip.setStyleSheet("background: transparent;")
        self.resize_grip.show()
        self._install_resize_event_filters()

    def _install_resize_event_filters(self):
        """子ウィジェットで覆われた外周からもリサイズ操作を受け取る。"""
        for widget in (self, *self.findChildren(QWidget)):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def _resize_edges_at(self, global_position: QPoint) -> frozenset[str]:
        local = self.mapFromGlobal(global_position)
        margin = self._resize_margin
        edges = set()
        if local.x() <= margin:
            edges.add("left")
        elif local.x() >= self.width() - margin - 1:
            edges.add("right")
        if local.y() <= margin:
            edges.add("top")
        elif local.y() >= self.height() - margin - 1:
            edges.add("bottom")
        return frozenset(edges)

    @staticmethod
    def _cursor_for_edges(edges: frozenset[str]):
        if edges in (frozenset(("left", "top")), frozenset(("right", "bottom"))):
            return Qt.SizeFDiagCursor
        if edges in (frozenset(("right", "top")), frozenset(("left", "bottom"))):
            return Qt.SizeBDiagCursor
        if "left" in edges or "right" in edges:
            return Qt.SizeHorCursor
        if "top" in edges or "bottom" in edges:
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    @staticmethod
    def _qt_resize_edges(edges: frozenset[str]):
        qt_edges = Qt.Edges()
        if "left" in edges:
            qt_edges |= Qt.LeftEdge
        if "right" in edges:
            qt_edges |= Qt.RightEdge
        if "top" in edges:
            qt_edges |= Qt.TopEdge
        if "bottom" in edges:
            qt_edges |= Qt.BottomEdge
        return qt_edges

    def _start_native_resize(self, edges: frozenset[str]) -> bool:
        """Qt/OSのネイティブリサイズを開始し、描画中の同期setGeometryを避ける。"""
        handle = self.windowHandle()
        if handle is None:
            return False
        return bool(handle.startSystemResize(self._qt_resize_edges(edges)))

    def _resize_from_global_position(self, global_position: QPoint):
        if self._resize_start_position is None or self._resize_start_geometry is None:
            return
        delta = global_position - self._resize_start_position
        start = self._resize_start_geometry
        geometry = QRect(start)
        min_width = self.minimumWidth()
        min_height = self.minimumHeight()

        if "left" in self._resize_edges:
            geometry.setLeft(min(start.right() - min_width + 1, start.left() + delta.x()))
        elif "right" in self._resize_edges:
            geometry.setRight(max(start.left() + min_width - 1, start.right() + delta.x()))
        if "top" in self._resize_edges:
            geometry.setTop(min(start.bottom() - min_height + 1, start.top() + delta.y()))
        elif "bottom" in self._resize_edges:
            geometry.setBottom(max(start.top() + min_height - 1, start.bottom() + delta.y()))
        self.setGeometry(geometry)

    def apply_window_settings(self, config):
        """本体のウィンドウ設定を切り離しパネルにも反映する。"""
        self.window_locked = bool(config.get("window_locked", False))
        self.setWindowOpacity(max(0.05, min(1.0, config.get("window_opacity", 100) / 100)))
        text_opacity = max(0.0, min(1.0, config.get("text_opacity", 100) / 100))
        # content配下には本体側で既に透過効果が設定されているウィジェットがある。
        # 親contentにも効果を重ねると、切り離し・リサイズ時にQtの描画が再入して
        # QPainter警告が連続するため、独立ヘッダーだけへ適用する。
        if text_opacity < 1.0:
            effect = QGraphicsOpacityEffect(self.header)
            effect.setOpacity(text_opacity)
            self.header.setGraphicsEffect(effect)
        else:
            self.header.setGraphicsEffect(None)
        self.content.setGraphicsEffect(None)
        self.resize_grip.setVisible(not self.window_locked)
        flags = Qt.Tool | Qt.FramelessWindowHint
        if config.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def return_to_main(self):
        self._return_callback(self.panel_id)

    def restore_content_size_policy(self):
        self.content.setSizePolicy(self._content_size_policy)

    def _move_from_global_position(self, global_position: QPoint):
        if self._drag_offset is not None:
            self.move(global_position - self._drag_offset)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease):
            global_position = event.globalPosition().toPoint()
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                edges = self._resize_edges_at(global_position)
                if not self.window_locked and edges:
                    if self._start_native_resize(edges):
                        self._native_resize_active = True
                        return True
                    self._resize_edges = edges
                    self._resize_start_position = global_position
                    self._resize_start_geometry = QRect(self.geometry())
                    return True
            elif event.type() == QEvent.MouseMove:
                if not self.window_locked and self._resize_edges and event.buttons() & Qt.LeftButton:
                    self._resize_from_global_position(global_position)
                    return True
                if not self.window_locked:
                    self.setCursor(QCursor(self._cursor_for_edges(self._resize_edges_at(global_position))))
                else:
                    self.unsetCursor()
            elif event.type() == QEvent.MouseButtonRelease and self._resize_edges:
                self._resize_edges = frozenset()
                self._resize_start_position = None
                self._resize_start_geometry = None
                self._state_callback(self.panel_id, True)
                return True
            elif event.type() == QEvent.MouseButtonRelease and self._native_resize_active:
                self._native_resize_active = False
                self._state_callback(self.panel_id, True)
                return True

        if watched is self.header:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if self.window_locked:
                    return True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.header.setCursor(QCursor(Qt.ClosedHandCursor))
                return True
            if event.type() == QEvent.MouseMove and not self.window_locked and self._drag_offset is not None and event.buttons() & Qt.LeftButton:
                self._move_from_global_position(event.globalPosition().toPoint())
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_offset = None
                self.header.setCursor(QCursor(Qt.OpenHandCursor))
                self._state_callback(self.panel_id, True)
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        if not self._returning:
            self._state_callback(self.panel_id, True)
            self._return_callback(self.panel_id)
        event.accept()

    def moveEvent(self, event):
        self._state_callback(self.panel_id, False)
        super().moveEvent(event)

    def resizeEvent(self, event):
        if hasattr(self, "resize_grip"):
            self.resize_grip.move(self.width() - self.resize_grip.width(), self.height() - self.resize_grip.height())
        self._state_callback(self.panel_id, False)
        super().resizeEvent(event)
