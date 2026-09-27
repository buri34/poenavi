from dataclasses import fields

from src.app_mode import POENAVI_MODE, POETORE_MODE
from src.ui.app_theme import POENAVI_THEME, POETORE_THEME, SETTINGS_THEME
from src.ui.dialog_theme import (
    POENAVI_DIALOG_THEME,
    POETORE_DIALOG_THEME,
    apply_dialog_theme,
    build_dialog_stylesheet,
    dialog_theme_for_mode,
    theme_asset_path,
)
from src.ui.styles import Styles


def test_dialog_theme_for_mode_selects_only_the_accent_variant():
    assert dialog_theme_for_mode(POENAVI_MODE) is POENAVI_DIALOG_THEME
    assert dialog_theme_for_mode(POETORE_MODE) is POETORE_DIALOG_THEME
    assert dialog_theme_for_mode("unknown") is POENAVI_DIALOG_THEME
    assert POENAVI_DIALOG_THEME.accent == "#B0FF7B"
    assert POETORE_DIALOG_THEME.accent == "#65FFCA"


def test_dialog_theme_keeps_all_non_brand_tokens_identical():
    brand_fields = {"name", "accent", "accent_soft"}
    for field in fields(POENAVI_DIALOG_THEME):
        if field.name not in brand_fields:
            assert getattr(POENAVI_DIALOG_THEME, field.name) == getattr(
                POETORE_DIALOG_THEME, field.name
            )

    assert POENAVI_DIALOG_THEME.text == "#E6ECEA"
    assert POENAVI_DIALOG_THEME.selection_control == "#4488FF"
    assert POENAVI_DIALOG_THEME.font_family == "Noto Sans JP"
    assert POENAVI_DIALOG_THEME.title_size > POENAVI_DIALOG_THEME.section_size
    assert POENAVI_DIALOG_THEME.section_size > POENAVI_DIALOG_THEME.body_size
    assert POENAVI_DIALOG_THEME.body_size > POENAVI_DIALOG_THEME.caption_size
    assert (
        POENAVI_DIALOG_THEME.form_control_height
        > POENAVI_DIALOG_THEME.compact_row_height
    )


def test_dialog_stylesheet_contains_every_shared_component_state():
    qss = build_dialog_stylesheet(POENAVI_DIALOG_THEME)
    root = 'QDialog[dialogTheme="poenavi"]'

    assert root in qss
    assert 'QLabel[uiRole="title"]' in qss
    assert 'QLabel[uiRole="section"]' in qss
    assert 'QLabel[uiRole="muted"]' in qss
    assert 'QPushButton[buttonRole="primary"]' in qss
    assert 'QPushButton[buttonRole="danger"]:hover' in qss
    assert "QLineEdit:focus" in qss
    assert "QCheckBox::indicator:checked" in qss
    assert "QRadioButton::indicator:checked" in qss
    assert "QTabBar::tab:selected" in qss
    assert "QAbstractItemView::item:selected" in qss
    assert "QScrollBar::handle:vertical:hover" in qss
    assert "QToolTip" in qss
    assert 'QLabel[state="success"]' in qss
    assert 'QLabel[state="warning"]' in qss
    assert 'QLabel[state="error"]' in qss
    assert 'QWidget[density="compact"]' in qss


def test_dialog_stylesheet_uses_blue_choice_assets_and_brand_focus_only():
    poenavi_qss = build_dialog_stylesheet(POENAVI_DIALOG_THEME)
    poetore_qss = build_dialog_stylesheet(POETORE_DIALOG_THEME)

    for filename in ("ui-checkbox-checked.svg", "ui-radio-checked.svg"):
        path = theme_asset_path(filename)
        assert path.is_file()
        assert str(path).replace("\\", "/") in poenavi_qss
        assert str(path).replace("\\", "/") in poetore_qss

    assert "#4488FF" in poenavi_qss
    assert "#4488FF" in poetore_qss
    assert POENAVI_DIALOG_THEME.accent in poenavi_qss
    assert POETORE_DIALOG_THEME.accent in poetore_qss
    assert POETORE_DIALOG_THEME.accent not in poenavi_qss
    assert POENAVI_DIALOG_THEME.accent not in poetore_qss


def test_existing_global_themes_and_styles_remain_unchanged():
    assert POENAVI_THEME.accent == "#B0FF7B"
    assert POENAVI_THEME.text == "#E9FFBD"
    assert POETORE_THEME.accent == "#65FFCA"
    assert POETORE_THEME.text == "#E6ECEA"
    assert SETTINGS_THEME is POENAVI_THEME
    assert Styles.TEXT_COLOR == "#b0ff7b"
    assert "rgba(0, 0, 0, 180)" in Styles.MAIN_WINDOW
    assert "padding: 5px 10px" in Styles.BUTTON


def test_apply_dialog_theme_marks_only_the_explicit_target():
    class FakeDialog:
        def __init__(self):
            self.properties = {}
            self.stylesheet = ""

        def setProperty(self, name, value):
            self.properties[name] = value

        def setStyleSheet(self, stylesheet):
            self.stylesheet = stylesheet

    dialog = FakeDialog()
    apply_dialog_theme(dialog, POENAVI_DIALOG_THEME)

    assert dialog.properties == {
        "dialogTheme": "poenavi",
        "dialogAccent": "#B0FF7B",
    }
    assert 'QDialog[dialogTheme="poenavi"]' in dialog.stylesheet
    assert "#E9FFBD" not in dialog.stylesheet
