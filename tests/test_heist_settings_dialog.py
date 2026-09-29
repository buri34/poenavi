from pathlib import Path

from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

from src.ui.dialog_theme import POETORE_DIALOG_THEME
from src.ui.heist_settings_dialog import (
    DEFAULT_EXAMPLE_IMAGE_PATH,
    HeistSettingsDialog,
)


def test_heist_settings_reuses_poetore_dialog_structure_and_defaults():
    QApplication.instance() or QApplication([])
    dialog = HeistSettingsDialog()
    try:
        assert dialog.windowTitle() == "ハイスト報酬OCR設定"
        assert dialog.theme == POETORE_DIALOG_THEME
        assert not dialog.enabled_checkbox.isChecked()
        assert dialog.hotkey_widget.key_text == "alt+shift+h"
        assert dialog.settings() == ("alt+shift+h", False)
        assert dialog.findChild(QGroupBox, "basicSettingsGroup") is not None
        assert dialog.findChild(QGroupBox, "readMethodGroup") is not None
        assert dialog.cancel_button.property("buttonRole") == "secondary"
        assert dialog.save_button.property("buttonRole") == "primary"
    finally:
        dialog.close()


def test_heist_settings_shows_manual_selection_example():
    QApplication.instance() or QApplication([])
    dialog = HeistSettingsDialog(enabled=True, hotkey="ctrl+h")
    try:
        assert Path(DEFAULT_EXAMPLE_IMAGE_PATH).is_file()
        assert not dialog.example_thumbnail.pixmap().isNull()
        assert "報酬名とベースタイプ" in dialog.findChild(
            QLabel, "heistSelectionInstruction"
        ).text()
        assert dialog.settings() == ("ctrl+h", True)
    finally:
        dialog.close()
