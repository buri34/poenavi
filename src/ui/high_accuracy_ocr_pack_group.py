"""Shared high-accuracy OCR pack status section for PoETore settings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QProgressBar, QPushButton, QVBoxLayout

from src.poetore.poe2.ndlocr_pack import PACK_VERSION


class HighAccuracyOcrPackGroup(QGroupBox):
    """Show and control the shared NDLOCR-Lite pack installation state."""

    def __init__(self, controller=None, parent=None, *, title="2. 高精度OCR"):
        super().__init__(title, parent)
        self._controller = controller
        self.setObjectName("highAccuracyOcrGroup")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)

        self.status_label = QLabel()
        self.status_label.setObjectName("highAccuracyOcrStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("highAccuracyOcrProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.retry_button = QPushButton("再試行")
        self.retry_button.setObjectName("highAccuracyOcrRetry")
        self.retry_button.clicked.connect(self._retry)
        layout.addWidget(self.retry_button, alignment=Qt.AlignLeft)

        if self._controller is not None:
            self._controller.status_changed.connect(self.update_status)
            self.update_status(self._controller.status)
        else:
            self.update_status(None)

    def _retry(self) -> None:
        if self._controller is not None:
            self._controller.retry()

    def update_status(self, status) -> None:
        state = getattr(status, "state", "unavailable")
        detail = getattr(status, "detail", "")
        done = int(getattr(status, "done", 0) or 0)
        total = int(getattr(status, "total", 0) or 0)
        self.progress_bar.setVisible(state == "downloading")
        self.retry_button.setVisible(state == "error")

        if state == "ready":
            self.status_label.setText(
                f"✓ 高精度OCRを利用できます\nNDLOCR-Lite {PACK_VERSION}"
            )
            self._set_label_state("success")
        elif state in {"checking", "idle"}:
            self.status_label.setText(
                "高精度OCRを準備しています\n"
                "初回のみ高精度OCRパックをダウンロードします"
            )
            self._set_label_state("")
        elif state == "downloading":
            percent = int(done * 100 / total) if total > 0 else 0
            self.progress_bar.setRange(0, 100 if total > 0 else 0)
            if total > 0:
                self.progress_bar.setValue(percent)
            self.status_label.setText(
                f"高精度OCRをダウンロードしています… {percent}%"
                if total > 0
                else "高精度OCRをダウンロードしています…"
            )
            self._set_label_state("")
        elif state == "installing":
            self.status_label.setText("高精度OCRをインストールしています…")
            self._set_label_state("")
        elif state == "error":
            message = (
                "高精度OCRを準備できませんでした\n"
                "通常の読み取り機能は引き続き利用できます"
            )
            if detail:
                message += f"\n{detail}"
            self.status_label.setText(message)
            self._set_label_state("warning")
        else:
            self.status_label.setText("高精度OCRの状態を確認できません")
            self._set_label_state("")

    def _set_label_state(self, state: str) -> None:
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
