import pytest
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

from src.ui.settings_dialog import SettingsDialog
from src.utils.poe_version_data import POE1, POE2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_settings_app_mode_uses_one_shared_startup_checkbox(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        }
    })

    assert dialog.app_mode_radios["poetore"].isChecked()
    assert not dialog.skip_startup_selector_checkbox.isChecked()
    dialog.app_mode_radios["poenavi"].setChecked(True)
    dialog.skip_startup_selector_checkbox.setChecked(True)
    settings = dialog.get_settings()

    assert settings["startup"] == {
        "preferred_mode": "poenavi",
        "show_mode_selector": False,
    }
    assert settings["poe_version_mode"] == settings["poe_version"]
    dialog.close()


def test_settings_dialog_uses_readable_shared_theme(qapp):
    dialog = SettingsDialog(current_config={})
    style = dialog.styleSheet()

    assert dialog.objectName() == "settingsDialog"
    assert "#B0FF7B" in style
    assert "#E9FFBD" in style
    assert "#101310" in style
    assert "#1E241E" in style
    assert "font-size: 13px" in style
    dialog.close()


def test_general_group_titles_are_center_aligned(qapp):
    dialog = SettingsDialog(current_config={})
    general_group_titles = {
        "PoE ログファイル",
        "起動設定",
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


def test_poe_version_and_app_mode_are_in_one_startup_group(qapp):
    dialog = SettingsDialog(current_config={})
    groups = [group for group in dialog.findChildren(QGroupBox) if group.title() == "起動設定"]
    labels = [label.text() for label in groups[0].findChildren(QLabel)]
    assert len(groups) == 1
    assert "PoEバージョン" in labels
    assert "起動モード" in labels
    dialog.close()


def test_startup_controls_have_one_shared_checkbox(qapp):
    dialog = SettingsDialog(current_config={})
    assert [radio.text() for radio in dialog.app_mode_radios.values()] == [
        "ぽえなび", "ぽえとれ"
    ]
    assert dialog.skip_startup_selector_checkbox.text() == "次回からこの設定で直接起動"
    assert not hasattr(dialog, "poe_version_mode_combo")
    assert not hasattr(dialog, "app_mode_startup_combo")
    dialog.close()


def test_fixed_startup_mode_selects_the_fixed_app(qapp):
    dialog = SettingsDialog(current_config={
        "startup": {"preferred_mode": "poenavi", "show_mode_selector": True}
    })
    dialog.app_mode_radios["poetore"].setChecked(True)
    dialog.skip_startup_selector_checkbox.setChecked(True)

    assert dialog.get_settings()["startup"] == {
        "preferred_mode": "poetore",
        "show_mode_selector": False,
    }
    dialog.close()


def test_poe2_enables_poetore_mode_and_fixed_startup(qapp):
    dialog = SettingsDialog(current_config={
        "poe_version": POE2,
        "poe_version_mode": POE2,
        "startup": {"preferred_mode": "poetore", "show_mode_selector": False},
    })

    assert dialog.app_mode_radios["poetore"].isEnabled()
    assert dialog.app_mode_radios["poetore"].isChecked()
    assert dialog.skip_startup_selector_checkbox.isChecked()
    assert dialog.get_settings()["startup"] == {
        "preferred_mode": "poetore",
        "show_mode_selector": False,
    }
    dialog.close()


def test_legacy_partially_fixed_startup_defaults_to_showing_selector(qapp):
    dialog = SettingsDialog(current_config={
        "poe_version": POE2,
        "poe_version_mode": "ask",
        "startup": {"preferred_mode": "poetore", "show_mode_selector": False},
    })

    assert not dialog.skip_startup_selector_checkbox.isChecked()
    settings = dialog.get_settings()
    assert settings["poe_version_mode"] == "ask"
    assert settings["startup"]["show_mode_selector"] is True
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


def test_monastery_hotkey_is_visible_only_for_poe1(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={"poe_version": POE2})

    assert not dialog.monastery_row.isVisibleTo(dialog)
    assert not dialog.map_check_row.isVisibleTo(dialog)
    assert not dialog.gem_shop_search_settings.isVisibleTo(dialog)

    dialog._on_poe_version_changed(POE1, True)
    assert dialog.monastery_row.isVisibleTo(dialog)
    assert dialog.map_check_row.isVisibleTo(dialog)
    assert dialog.gem_shop_search_settings.isVisibleTo(dialog)
    dialog.close()


def test_poe1_settings_preserve_voicevox_without_exposing_it(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    existing = {"enabled": True, "speaker_id": 8, "speed_scale": 1.3, "volume_scale": 0.7}
    dialog = SettingsDialog(current_config={"poe_version": POE1, "voicevox": existing})
    assert not dialog.voicevox_group.isVisibleTo(dialog)
    assert dialog.get_settings()["voicevox"] == existing
    dialog.close()
