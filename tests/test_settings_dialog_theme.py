import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QPushButton,
    QRadioButton,
    QSlider,
)

from src.ui.dialog_theme import POENAVI_DIALOG_THEME
from src.ui.settings_dialog import MiniNaviEditorDialog, SettingsDialog
from src.ui.styles import Styles


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_poENavi_settings_uses_shared_control_styles_and_button_roles(qapp):
    dialog = SettingsDialog(current_config={})
    try:
        assert dialog.theme is POENAVI_DIALOG_THEME
        assert dialog.title_label.property("uiRole") == "title"
        assert dialog.ok_btn.property("buttonRole") == "primary"
        assert dialog.cancel_btn.property("buttonRole") == "secondary"
        assert dialog.guide_progress_reset_btn.property("buttonRole") == "danger"

        for widget_type in (
            QCheckBox,
            QComboBox,
            QGroupBox,
            QPushButton,
            QRadioButton,
            QSlider,
        ):
            assert all(
                widget.styleSheet() == "" for widget in dialog.findChildren(widget_type)
            )
    finally:
        dialog.close()


def test_settings_footer_places_cancel_before_primary_save(qapp):
    dialog = SettingsDialog(current_config={})
    try:
        widgets = [
            dialog.footer_layout.itemAt(index).widget()
            for index in range(dialog.footer_layout.count())
            if dialog.footer_layout.itemAt(index).widget() is not None
        ]
        assert widgets[-2:] == [dialog.cancel_btn, dialog.ok_btn]
    finally:
        dialog.close()


def test_embedded_management_widgets_use_shared_theme_roles(qapp):
    dialog = SettingsDialog(current_config={})
    try:
        custom = dialog.custom_commands_widget
        assert custom.property("density") == "compact"
        assert custom.table.styleSheet() == ""
        assert custom.add_button.property("buttonRole") == "primary"
        assert custom.remove_button.property("buttonRole") == "danger"

        terms = dialog.gem_shop_search_term_review
        assert terms.property("density") == "compact"
        assert terms._table.styleSheet() == ""
        assert terms.reset_all_button.property("buttonRole") == "danger"

        assert dialog.about_tab.update_button.property("buttonRole") == "primary"
        assert dialog.app_disclaimer_label.property("uiRole") == "muted"
    finally:
        dialog.close()


def test_mini_navi_editor_keeps_its_protected_legacy_theme(qapp):
    settings = SettingsDialog(current_config={})
    editor = MiniNaviEditorDialog(settings, "テストエリア", [])
    try:
        assert editor.property("dialogTheme") is None
        assert editor.styleSheet() == Styles.MAIN_WINDOW
    finally:
        editor.close()
        settings.close()
