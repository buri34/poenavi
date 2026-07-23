"""切り離しパネル用の独立ウィンドウ。"""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizeGrip, QSizePolicy, QVBoxLayout, QWidget

from src.ui.styles import Styles


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
        return_button = QPushButton("↙ 本体へ戻す")
        return_button.setStyleSheet(Styles.BUTTON)
        return_button.setCursor(QCursor(Qt.PointingHandCursor))
        return_button.clicked.connect(self.return_to_main)
        header_layout.addWidget(return_button)
        self.header.setFixedHeight(self.header.sizeHint().height())
        layout.addWidget(self.header)
        layout.addWidget(content, stretch=1)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(18, 18)
        self.resize_grip.setToolTip("ドラッグしてサイズ変更")
        self.resize_grip.setStyleSheet("background: transparent;")
        self.resize_grip.show()

    def return_to_main(self):
        self._return_callback(self.panel_id)

    def restore_content_size_policy(self):
        self.content.setSizePolicy(self._content_size_policy)

    def _move_from_global_position(self, global_position: QPoint):
        if self._drag_offset is not None:
            self.move(global_position - self._drag_offset)

    def eventFilter(self, watched, event):
        if watched is self.header:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.header.setCursor(QCursor(Qt.ClosedHandCursor))
                return True
            if event.type() == QEvent.MouseMove and self._drag_offset is not None and event.buttons() & Qt.LeftButton:
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
