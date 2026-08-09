import pytest
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_settings_app_mode_uses_same_radio_and_startup_combo_structure(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        }
    })

    assert dialog.app_mode_radios["poetore"].isChecked()
    assert dialog.app_mode_startup_combo.currentData() == "poetore"
    dialog.app_mode_radios["poenavi"].setChecked(True)
    dialog.app_mode_startup_combo.setCurrentIndex(
        dialog.app_mode_startup_combo.findData("ask")
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


def test_poe_version_group_is_above_startup_mode_group(qapp):
    dialog = SettingsDialog(current_config={})
    groups = {
        group.title(): group
        for group in dialog.findChildren(QGroupBox)
        if group.title() in {"PoEバージョン", "起動モード"}
    }
    layout = groups["PoEバージョン"].parentWidget().layout()

    assert layout.indexOf(groups["PoEバージョン"]) < layout.indexOf(groups["起動モード"])
    dialog.close()


def test_startup_mode_controls_match_poe_version_control_structure(qapp):
    dialog = SettingsDialog(current_config={})
    assert [radio.text() for radio in dialog.app_mode_radios.values()] == [
        "ぽえなび", "ぽえとれ"
    ]
    assert [
        dialog.app_mode_startup_combo.itemData(index)
        for index in range(dialog.app_mode_startup_combo.count())
    ] == ["ask", "poenavi", "poetore"]
    assert [
        dialog.app_mode_startup_combo.itemText(index)
        for index in range(dialog.app_mode_startup_combo.count())
    ] == ["毎回確認", "ぽえなび固定", "ぽえとれ固定"]
    dialog.close()


def test_fixed_startup_mode_selects_the_fixed_app(qapp):
    dialog = SettingsDialog(current_config={
        "startup": {"preferred_mode": "poenavi", "show_mode_selector": True}
    })
    dialog.app_mode_startup_combo.setCurrentIndex(
        dialog.app_mode_startup_combo.findData("poetore")
    )

    assert dialog.get_settings()["startup"] == {
        "preferred_mode": "poetore",
        "show_mode_selector": False,
    }
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
