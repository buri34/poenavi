from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QRadioButton,
    QScrollArea,
    QTextEdit,
)

from src.ui.dialog_theme import POENAVI_DIALOG_THEME
from src.ui.settings_dialog import (
    AreaNoteDialog,
    GuideEditorDialog,
    GuideSummaryEditorDialog,
    MiniNaviEditorDialog,
)
from src.ui.styles import Styles
from src.ui.vendor_search_dialog import VendorSearchPresetDialog
from src.utils.poe_version_data import POE2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _footer_widgets(layout):
    return [
        layout.itemAt(index).widget()
        for index in range(layout.count())
        if layout.itemAt(index).widget() is not None
    ]


def test_area_note_uses_poENavi_theme_and_shared_footer(qapp):
    dialog = AreaNoteDialog(None, "黄昏の海岸", "テストメモ")
    try:
        assert dialog.theme is POENAVI_DIALOG_THEME
        assert dialog.property("dialogTheme") == "poenavi"
        assert dialog.title_label.property("uiRole") == "title"
        assert dialog.text_edit.styleSheet() == ""
        assert dialog.cancel_button.property("buttonRole") == "secondary"
        assert dialog.save_button.property("buttonRole") == "primary"
        assert _footer_widgets(dialog.footer_layout)[-2:] == [
            dialog.cancel_button,
            dialog.save_button,
        ]
    finally:
        dialog.close()


def test_guide_editors_use_poENavi_theme_without_inline_control_qss(qapp):
    detail = GuideEditorDialog(None, "テストエリア", {}, zone_id="act1_area1")
    summary = GuideSummaryEditorDialog(
        None,
        "テストエリア",
        {"default": {"summary": "要約"}, "flags": {}},
    )
    try:
        for dialog in (detail, summary):
            assert dialog.theme is POENAVI_DIALOG_THEME
            assert dialog.property("dialogTheme") == "poenavi"
            assert dialog.title_label.property("uiRole") == "title"
            assert dialog.cancel_button.property("buttonRole") == "secondary"
            assert dialog.save_button.property("buttonRole") == "primary"
            assert _footer_widgets(dialog.footer_layout)[-2:] == [
                dialog.cancel_button,
                dialog.save_button,
            ]
            for widget_type in (
                QTextEdit,
                QGroupBox,
                QRadioButton,
                QScrollArea,
            ):
                assert all(
                    widget.styleSheet() == ""
                    for widget in dialog.findChildren(widget_type)
                )
    finally:
        detail.close()
        summary.close()


def test_vendor_preset_manager_uses_poENavi_theme_and_common_roles(qapp, tmp_path):
    path = Path(tmp_path) / "presets.json"
    dialog = VendorSearchPresetDialog(presets_path=str(path), poe_version=POE2)
    try:
        assert dialog.theme is POENAVI_DIALOG_THEME
        assert dialog.property("dialogTheme") == "poenavi"
        assert dialog.title_label.property("uiRole") == "title"
        assert dialog.hint_label.property("uiRole") == "muted"
        assert dialog.table.styleSheet() == ""
        assert dialog.name_edit.styleSheet() == ""
        assert dialog.query_edit.styleSheet() == ""
        assert dialog.cancel_button.property("buttonRole") == "secondary"
        assert dialog.save_btn.property("buttonRole") == "primary"
        assert _footer_widgets(dialog.footer_layout)[-2:] == [
            dialog.cancel_button,
            dialog.save_btn,
        ]
    finally:
        dialog.close()


def test_mini_navi_editor_remains_on_protected_legacy_theme(qapp):
    parent = QDialog()
    dialog = MiniNaviEditorDialog(parent, "テストエリア", [])
    try:
        assert dialog.property("dialogTheme") is None
        assert dialog.styleSheet() == Styles.MAIN_WINDOW
    finally:
        dialog.close()
        parent.close()
