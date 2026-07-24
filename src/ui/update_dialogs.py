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
from src.utils.i18n import tr


class UpdateAvailableDialog(QDialog):
    def __init__(
        self,
        release: ReleaseInfo,
        auto_update_supported: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle(tr("update.title"))
        self.setMinimumSize(480, 360)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        layout = QVBoxLayout(self)
        title = QLabel(
            tr("update.available", version=release.version)
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        notes = QTextBrowser()
        notes.setMarkdown(release.notes)
        notes.setOpenExternalLinks(True)
        layout.addWidget(notes)

        buttons = QDialogButtonBox()
        update = buttons.addButton(
            tr("update.now")
            if auto_update_supported
            else tr("update.open_release"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        later = buttons.addButton(
            tr("update.later"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        update.clicked.connect(self.accept)
        later.clicked.connect(self.reject)
        layout.addWidget(buttons)


class UpdateProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("update.title"))
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.label = QLabel(tr("update.download", version=version))
        self.progress = QProgressBar()
        self.cancel_button = QPushButton(tr("update.cancel"))
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        layout.addWidget(self.cancel_button)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total if total > 0 else 0)
        self.progress.setValue(done)
        if total:
            text = (
                tr("update.progress_known", done=done / 1024 / 1024, total=total / 1024 / 1024)
            )
        else:
            text = tr("update.progress_unknown", done=done / 1024 / 1024)
        self.label.setText(text)
