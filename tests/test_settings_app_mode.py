import pytest
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

from src.ui.settings_dialog import SettingsDialog
from src.utils.poe_version_data import POE1, POE2


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


def test_poe2_enables_poetore_mode_and_fixed_startup(qapp):
    dialog = SettingsDialog(current_config={
        "poe_version": POE2,
        "startup": {"preferred_mode": "poetore", "show_mode_selector": False},
    })

    assert dialog.app_mode_radios["poetore"].isEnabled()
    assert dialog.app_mode_radios["poetore"].isChecked()
    poetore_index = dialog.app_mode_startup_combo.findData("poetore")
    assert dialog.app_mode_startup_combo.model().item(poetore_index).isEnabled()
    assert dialog.app_mode_startup_combo.currentData() == "poetore"
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


def test_general_settings_does_not_expose_poetore_result_position_reset(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={
        "poetore": {
            "league": "Standard",
            "result_positions": {
                "stash": {"x_ratio": 0.2, "y_ratio": 0.3},
                "inventory": {"x_ratio": 0.8, "y_ratio": 0.4},
            },
        }
    })

    poetore = dialog.get_settings()["poetore"]

    assert poetore["league"] == "Standard"
    assert poetore["result_positions"] == {
        "stash": {"x_ratio": 0.2, "y_ratio": 0.3},
        "inventory": {"x_ratio": 0.8, "y_ratio": 0.4},
    }
    assert not hasattr(dialog, "reset_poetore_result_positions_button")
    dialog.close()


def test_voicevox_is_off_by_default_and_visible_only_for_poe2(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={"poe_version": POE2})
    assert dialog.voicevox_group.isVisibleTo(dialog)
    assert not dialog.voicevox_enabled_cb.isChecked()
    assert dialog.voicevox_speed_spin.value() == 1.2
    assert dialog.voicevox_speed_spin.singleStep() == 0.05
    assert dialog.voicevox_speed_spin.decimals() == 2
    assert dialog.voicevox_pause_length_spin.value() == 1.5
    assert dialog.voicevox_pause_length_spin.singleStep() == 0.05
    assert dialog.voicevox_pause_length_spin.decimals() == 2
    assert dialog.voicevox_post_phoneme_spin.value() == 0.3
    assert dialog.voicevox_post_phoneme_spin.singleStep() == 0.01
    assert dialog.voicevox_post_phoneme_spin.decimals() == 2
    labels = {label.text() for label in dialog.voicevox_group.findChildren(QLabel)}
    assert "読点の無音時間の長さ:" in labels
    assert "読点等の無音時間の長さ:" not in labels
    assert "文末の無音時間の長さ:" in labels
    assert dialog.voicevox_volume_spin.singleStep() == 0.1
    assert dialog.voicevox_volume_spin.decimals() == 1
    assert dialog.get_settings()["voicevox"] == {
        "enabled": False,
        "speaker_id": 3,
        "speed_scale": 1.2,
        "pause_length_scale": 1.5,
        "post_phoneme_length": 0.3,
        "volume_scale": 1.0,
    }
    dialog._on_poe_version_changed(POE1, True)
    assert not dialog.voicevox_group.isVisible()
    dialog.close()


def test_poe1_settings_preserve_voicevox_without_exposing_it(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    existing = {"enabled": True, "speaker_id": 8, "speed_scale": 1.3, "volume_scale": 0.7}
    dialog = SettingsDialog(current_config={"poe_version": POE1, "voicevox": existing})
    assert not dialog.voicevox_group.isVisibleTo(dialog)
    assert dialog.get_settings()["voicevox"] == existing
    dialog.close()
