from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from src.ui.styles import Styles
from src.update.release_client import ReleaseInfo


class UpdateAvailableDialog(QDialog):
    def __init__(
        self,
        release: ReleaseInfo,
        auto_update_supported: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle("ぽえなび アップデート")
        self.setMinimumSize(480, 360)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        layout = QVBoxLayout(self)
        title = QLabel(
            f"新しいバージョン v{release.version} を利用できます。"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        notes = QTextBrowser()
        notes.setPlainText(release.notes)
        layout.addWidget(notes)

        buttons = QDialogButtonBox()
        update = buttons.addButton(
            "今すぐアップデート"
            if auto_update_supported
            else "リリースページを開く",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        later = buttons.addButton(
            "後で",
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        update.clicked.connect(self.accept)
        later.clicked.connect(self.reject)
        layout.addWidget(buttons)


class UpdateProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ぽえなび アップデート")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.label = QLabel(f"v{version} をダウンロードしています…")
        self.progress = QProgressBar()
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        layout.addWidget(self.cancel_button)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total if total > 0 else 0)
        self.progress.setValue(done)
        if total:
            text = (
                f"ダウンロード中: {done / 1024 / 1024:.1f} / "
                f"{total / 1024 / 1024:.1f} MB"
            )
        else:
            text = f"ダウンロード中: {done / 1024 / 1024:.1f} MB"
        self.label.setText(text)
