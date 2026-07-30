import pytest
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_settings_can_restore_mode_selector_without_changing_preferred_mode(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        }
    })

    assert not dialog.show_mode_selector_cb.isChecked()
    assert dialog.preferred_mode_combo.currentData() == "poetore"
    dialog.show_mode_selector_cb.setChecked(True)
    dialog.preferred_mode_combo.setCurrentIndex(
        dialog.preferred_mode_combo.findData("poenavi")
    )
    settings = dialog.get_settings()

    assert settings["startup"] == {
        "preferred_mode": "poenavi",
        "show_mode_selector": True,
    }
    dialog.close()


def test_general_group_titles_are_center_aligned(qapp):
    dialog = SettingsDialog(current_config={})
    general_group_titles = {
        "PoE ログファイル",
        "起動モード",
        "PoEバージョン",
        "ホットキー",
        "ウィンドウ設定（本体）",
    }
    groups = {
        group.title(): group
        for group in dialog.findChildren(QGroupBox)
        if group.title() in general_group_titles
    }

    assert groups.keys() == general_group_titles
    for group in groups.values():
        assert "subcontrol-position: top center" in group.styleSheet()

    dialog.close()


def test_startup_mode_note_is_directly_below_selector_checkbox(qapp):
    dialog = SettingsDialog(current_config={})
    note = dialog.findChild(QLabel, "startupModeSelectorNote")
    layout = dialog.show_mode_selector_cb.parentWidget().layout()

    checkbox_index = layout.indexOf(dialog.show_mode_selector_cb)
    note_index = layout.indexOf(note)

    assert checkbox_index >= 0
    assert note_index == checkbox_index + 1
    dialog.close()


def test_general_settings_save_note_is_at_bottom(qapp):
    dialog = SettingsDialog(current_config={})
    note = dialog.findChild(QLabel, "generalSettingsSaveNote")
    layout = note.parentWidget().layout()

    assert "変更は保存後すぐ反映されます" in note.text()
    assert "保存後に再起動を確認します" in note.text()
    assert layout.indexOf(note) == layout.count() - 2
    assert layout.itemAt(layout.count() - 1).spacerItem() is not None
    dialog.close()
