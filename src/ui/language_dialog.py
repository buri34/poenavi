"""First-run language selection dialog.

This dialog intentionally keeps its visible copy bilingual because it appears
before PoENavi has an active locale.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from src.utils.i18n import EN, JA


class LanguageSelectionDialog(QDialog):
    def __init__(self, parent=None, preferred_locale: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Language / 言語")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose the PoENavi language / PoENaviの言語を選択してください。"))

        self.japanese_radio = QRadioButton("日本語")
        self.english_radio = QRadioButton("English")
        layout.addWidget(self.japanese_radio)
        layout.addWidget(self.english_radio)

        locale = preferred_locale or QLocale.system().name()
        if str(locale).lower().startswith("ja"):
            self.japanese_radio.setChecked(True)
        else:
            self.english_radio.setChecked(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_locale(self) -> str:
        return JA if self.japanese_radio.isChecked() else EN
