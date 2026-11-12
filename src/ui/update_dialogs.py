from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from src.ui.dialog_theme import POENAVI_DIALOG_THEME, POETORE_DIALOG_THEME
from src.ui.styles import Styles
from src.update.release_client import ReleaseInfo


def _update_message_theme(parent):
    """更新メッセージを呼び出した設定画面のテーマへ合わせる。"""
    widget = parent
    while widget is not None:
        if widget.property("dialogTheme") == POETORE_DIALOG_THEME.name:
            return POETORE_DIALOG_THEME
        if widget.property("dialogTheme") == POENAVI_DIALOG_THEME.name:
            return POENAVI_DIALOG_THEME
        widget = widget.parentWidget()
    return POENAVI_DIALOG_THEME


def build_update_message_box(
    parent,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButtons = QMessageBox.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.NoButton,
) -> QMessageBox:
    """親画面のQSSに影響されず読める更新メッセージを構築する。"""
    theme = _update_message_theme(parent)
    message = QMessageBox(parent)
    message.setWindowTitle(title)
    message.setIcon(icon)
    message.setText(text)
    message.setStandardButtons(buttons)
    if default_button != QMessageBox.NoButton:
        message.setDefaultButton(default_button)
    message.setStyleSheet(
        f"""
        QMessageBox {{
            background-color: {theme.background};
        }}
        QMessageBox QLabel {{
            background-color: transparent;
            color: {theme.text};
        }}
        QMessageBox QPushButton {{
            min-width: 72px;
            padding: 5px 12px;
            background-color: {theme.control};
            color: {theme.text};
            border: 1px solid {theme.border_strong};
            border-radius: 4px;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {theme.surface};
            border-color: {theme.accent};
        }}
        QMessageBox QPushButton:pressed {{
            background-color: {theme.background};
        }}
        """
    )
    return message


def show_update_message(*args, **kwargs) -> int:
    """可読性を固定した更新メッセージを表示する。"""
    return build_update_message_box(*args, **kwargs).exec()


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
