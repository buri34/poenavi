from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QDialog

from src.ui.settings_dialog import AreaNoteDialog, SettingsDialog
from src.utils.poe_version_data import POE1, POE2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_settings_area_note_editor_loads_and_saves_current_version(monkeypatch, qapp):
    dialog = SettingsDialog.__new__(SettingsDialog)
    QDialog.__init__(dialog)
    dialog.poe_version = POE2

    monkeypatch.setattr("src.ui.settings_dialog.get_area_note", lambda version, zone_id: "既存メモ")
    saved = []
    monkeypatch.setattr(
        "src.ui.settings_dialog.set_area_note",
        lambda version, zone_id, content: saved.append((version, zone_id, content)),
    )

    editor = MagicMock()
    editor.exec.return_value = True
    editor.content.return_value = "更新メモ"
    editor_class = MagicMock(return_value=editor)
    monkeypatch.setattr("src.ui.settings_dialog.AreaNoteDialog", editor_class)

    dialog._open_area_note_editor("poe2_act1_area1", "クリアフェル")

    editor_class.assert_called_once_with(dialog, "クリアフェル", "既存メモ")
    assert saved == [(POE2, "poe2_act1_area1", "更新メモ")]


def test_settings_area_note_editor_does_not_save_when_cancelled(monkeypatch, qapp):
    dialog = SettingsDialog.__new__(SettingsDialog)
    QDialog.__init__(dialog)
    dialog.poe_version = POE1

    monkeypatch.setattr("src.ui.settings_dialog.get_area_note", lambda version, zone_id: "")
    save = MagicMock()
    monkeypatch.setattr("src.ui.settings_dialog.set_area_note", save)
    editor = MagicMock()
    editor.exec.return_value = False
    monkeypatch.setattr("src.ui.settings_dialog.AreaNoteDialog", MagicMock(return_value=editor))

    dialog._open_area_note_editor("act1_area1", "黄昏の海岸")

    save.assert_not_called()


def test_area_note_dialog_stylesheets_parse_without_qt_warnings(qapp):
    messages = []
    previous_handler = qInstallMessageHandler(
        lambda message_type, context, message: messages.append(message)
    )
    try:
        dialog = AreaNoteDialog(None, "黄昏の海岸", "テストメモ")
        dialog.show()
        qapp.processEvents()
        dialog.close()
    finally:
        qInstallMessageHandler(previous_handler)

    assert not [message for message in messages if "Could not parse stylesheet" in message]
