from unittest.mock import patch

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

from src.app_restart import confirm_mode_switch_restart
from src.ui.appearance import configure_appearance, current_appearance, normalize_appearance, resolve_tokens
from src.ui.appearance_settings import AppearanceSettingsWidget
from src.ui.settings_dialog import SettingsDialog
from src.ui.poetore_settings_dialog import PoetoreSettingsDialog


@pytest.fixture(autouse=True)
def reset_appearance(qapp):
    before = current_appearance()
    configure_appearance(None)
    qapp.setProperty("appMode", "poenavi")
    yield
    configure_appearance(before)


@pytest.mark.parametrize("dialog_class", [SettingsDialog, PoetoreSettingsDialog])
def test_both_modes_edit_the_same_shared_settings(qapp, dialog_class):
    appearance = {"preset": "poetore", "overrides": {"text": "#123456", "base_font_size": 16}}
    dialog = dialog_class(current_config={"appearance": appearance})
    try:
        editor = dialog.appearance_widget
        assert editor.settings() == appearance
        assert dialog.get_settings()["appearance"] == appearance
        editor.preset_combo.setCurrentIndex(editor.preset_combo.findData("poenavi"))
        assert editor.settings()["preset"] == "poenavi"
        assert editor.settings()["overrides"] == appearance["overrides"]
        assert current_appearance() == normalize_appearance(None)
    finally:
        dialog.close()


@pytest.mark.parametrize("dialog_class", [SettingsDialog, PoetoreSettingsDialog])
@pytest.mark.parametrize("preset, label", [
    ("tokyo_night", "Tokyo Night"), ("vscode_dark_2026", "VS Code Dark 2026"),
])
def test_upstream_presets_are_selectable_saved_and_previewed(qapp, dialog_class, preset, label):
    dialog = dialog_class(current_config={})
    restored = None
    try:
        editor = dialog.appearance_widget
        index = editor.preset_combo.findText(label)
        assert index >= 0
        assert editor.preset_combo.itemData(index) == preset
        editor.preset_combo.setCurrentIndex(index)
        settings = {"preset": preset, "overrides": {}}
        assert editor.settings() == settings
        assert dialog.get_settings()["appearance"] == settings
        tokens = resolve_tokens(settings)
        for role, _label in editor.COLOR_FIELDS:
            assert editor.color_buttons[role].text() == getattr(tokens, role)
        assert tokens.surface in editor.preview.styleSheet()
        assert tokens.muted_text in editor.preview.styleSheet()
        restored = AppearanceSettingsWidget(settings)
        assert restored.preset_combo.currentText() == label
        assert restored.settings() == settings
        assert current_appearance() == normalize_appearance(None)
    finally:
        if restored is not None:
            restored.close()
        dialog.close()


def test_color_picker_handles_accept_and_cancel_without_changing_running_theme(qapp):
    editor = AppearanceSettingsWidget()
    try:
        with patch("src.ui.appearance_settings.QColorDialog.getColor", return_value=QColor("#123456")):
            editor.color_buttons["text"].click()
        assert editor.settings()["overrides"]["text"] == "#123456"
        with patch("src.ui.appearance_settings.QColorDialog.getColor", return_value=QColor()):
            editor.color_buttons["text"].click()
        assert editor.settings()["overrides"]["text"] == "#123456"
        assert "#123456" in editor.preview.styleSheet()
        assert current_appearance() == normalize_appearance(None)
        editor.reset_button.click()
        assert editor.settings() == normalize_appearance(None)
    finally:
        editor.close()


@pytest.mark.parametrize("answer", [QMessageBox.Ok, QMessageBox.Cancel])
def test_appearance_only_change_offers_restart(qapp, answer):
    config = {"startup": {"preferred_mode": "poenavi"}, "appearance": {"preset": "poetore"}}
    with (
        patch("src.app_restart._ask_mode_switch_restart", return_value=answer) as question,
        patch("src.app_restart.restart_application", return_value=True) as restart,
    ):
        assert confirm_mode_switch_restart(None, config) is (answer == QMessageBox.Ok)
        assert "外観" in question.call_args.args[2]
        assert "再起動後" in question.call_args.args[2]
        assert restart.call_count == (1 if answer == QMessageBox.Ok else 0)


def test_failed_restart_keeps_saved_settings_and_reports_recovery(qapp):
    config = {"startup": {"preferred_mode": "poenavi"}, "appearance": {"overrides": {"base_font_size": 18}}}
    with (
        patch("src.app_restart._ask_mode_switch_restart", return_value=QMessageBox.Ok),
        patch("src.app_restart.restart_application", return_value=False),
        patch("src.app_restart.QMessageBox.warning") as warning,
    ):
        assert confirm_mode_switch_restart(None, config) is False
        assert "設定は保存されている" in warning.call_args.args[2]
        assert config["appearance"]["overrides"]["base_font_size"] == 18
