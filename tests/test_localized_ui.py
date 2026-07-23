import re
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTableWidget,
    QWidget,
)

from src.ui.gem_tracker_widget import PoBSkillSetSelectionDialog
from src.ui.main_window import (
    GuideDetailLevelSelectionDialog,
    MainWindow,
    VendorSearchPresetDialog,
)
from src.ui.settings_dialog import SettingsDialog
from src.poetore.ui import PoetoreWindow
from src.utils.i18n import EN, JA, set_locale
from src.utils.poe_version_data import POE1


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_locale():
    yield
    set_locale(JA)


def _display_texts(root: QWidget) -> list[str]:
    texts = [root.windowTitle()]
    for widget in [root, *root.findChildren(QWidget)]:
        if isinstance(widget, QGroupBox):
            texts.append(widget.title())
        elif isinstance(widget, (QLabel, QAbstractButton)):
            texts.append(widget.text())
        if isinstance(widget, QComboBox):
            texts.extend(widget.itemText(index) for index in range(widget.count()))
        if isinstance(widget, QTableWidget):
            texts.extend(
                widget.horizontalHeaderItem(index).text()
                for index in range(widget.columnCount())
                if widget.horizontalHeaderItem(index) is not None
            )
            texts.extend(
                item.text()
                for row in range(widget.rowCount())
                for column in range(widget.columnCount())
                if (item := widget.item(row, column)) is not None
            )
    return [text for text in texts if text]


def _assert_no_japanese(texts: list[str], *, allowed: set[str] | None = None):
    allowed = allowed or set()
    leftovers = sorted(
        {text for text in texts if JAPANESE.search(text) and text not in allowed}
    )
    assert leftovers == []


def test_main_window_chrome_constructs_in_english(qapp):
    set_locale(EN)
    config = {
        "language": EN,
        "poe_version": POE1,
        "poe_version_mode": POE1,
        "client_log_paths": {},
        "area_note_migration_notice_shown": True,
        "setup_completed": True,
    }
    with (
        patch.object(MainWindow, "_run_startup_update_gate", return_value=True),
        patch.object(MainWindow, "register_hotkeys"),
        patch.object(MainWindow, "_show_area_note_migration_notice_once"),
        patch.object(MainWindow, "_check_first_run"),
        patch.object(MainWindow, "_restore_progress_flags"),
        patch.object(MainWindow, "_restore_timer_state"),
        patch("src.ui.main_window.ConfigManager.save_config"),
    ):
        window = MainWindow(config=config)
        try:
            _assert_no_japanese(_display_texts(window))
        finally:
            window.deleteLater()
            qapp.processEvents()


def test_startup_and_pob_selection_dialogs_construct_in_english(qapp):
    set_locale(EN)
    dialogs = [
        GuideDetailLevelSelectionDialog(),
        PoBSkillSetSelectionDialog(
            [{"id": "campaign", "title": "Act 1", "active": True}]
        ),
    ]
    try:
        for dialog in dialogs:
            _assert_no_japanese(_display_texts(dialog))
    finally:
        for dialog in dialogs:
            dialog.deleteLater()
        qapp.processEvents()


def test_vendor_editor_application_labels_construct_in_english(qapp):
    set_locale(EN)
    with patch("src.ui.main_window.ConfigManager.load_config", return_value={}):
        dialog = VendorSearchPresetDialog(presets_path="")
    try:
        # Regex tooltips intentionally remain client-language search tokens;
        # application-owned visible labels must follow the PoENavi locale.
        _assert_no_japanese(_display_texts(dialog))
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_settings_generated_labels_and_tooltips_construct_in_english(qapp):
    set_locale(EN)
    dialog = SettingsDialog(None, {"language": EN})
    try:
        allowed = {"Language / 言語", "日本語"}
        _assert_no_japanese(_display_texts(dialog), allowed=allowed)
        tooltips = [
            widget.toolTip()
            for widget in dialog.findChildren(QLineEdit)
            if widget.toolTip()
        ]
        _assert_no_japanese(tooltips)
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_poetrieve_window_chrome_constructs_in_english(qapp):
    set_locale(EN)
    window = PoetoreWindow()
    try:
        assert window.windowTitle() == "Poetrieve"
        _assert_no_japanese(_display_texts(window))
        _assert_no_japanese(
            [
                widget.toolTip()
                for widget in [window, *window.findChildren(QWidget)]
                if widget.toolTip()
            ]
        )
    finally:
        window.close()
        qapp.processEvents()


def test_poetrieve_parse_error_is_shown_in_english(qapp):
    set_locale(EN)
    window = PoetoreWindow()
    try:
        window.input_edit.clear()
        with patch("src.poetore.ui.QMessageBox.warning") as warning:
            window.parse_current_text()

        assert warning.call_args.args[1] == "Could not parse item"
        assert warning.call_args.args[2] == "Item text is empty."
    finally:
        window.close()
        qapp.processEvents()


def test_poetrieve_trade_validation_error_is_shown_in_english(qapp):
    set_locale(EN)
    window = PoetoreWindow()
    try:
        window._show_price_error("アイテムレベルは1～100で指定してください。")

        assert window.price_status.text() == "Item Level must be between 1 and 100."
    finally:
        window.close()
        qapp.processEvents()
