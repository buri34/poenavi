from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.ui.dialog_theme import POENAVI_DIALOG_THEME
from src.ui.update_dialogs import build_update_message_box
from src.update.qt_controller import UpdateController
from src.update.startup_gate import (
    run_manual_update_check,
    run_startup_update_gate,
)


class ImmediateThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


def test_common_startup_gate_continues_without_update():
    QApplication.instance() or QApplication([])

    def controller_factory(parent=None):
        return UpdateController(parent, thread_factory=lambda target: ImmediateThread(target))

    with patch(
        "src.update.startup_gate.UpdateController",
        side_effect=controller_factory,
    ), patch(
        "src.update.qt_controller.fetch_latest_release",
        return_value=None,
    ):
        assert run_startup_update_gate({}) is True


def test_manual_check_reports_latest_version():
    QApplication.instance() or QApplication([])

    def controller_factory(parent=None):
        return UpdateController(
            parent,
            thread_factory=lambda target: ImmediateThread(target),
        )

    with patch(
        "src.update.startup_gate.UpdateController",
        side_effect=controller_factory,
    ), patch(
        "src.update.qt_controller.fetch_latest_release",
        return_value=None,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message:
        assert run_manual_update_check({}) is True

    show_message.assert_called_once_with(
        None,
        QMessageBox.Information,
        "アップデート",
        "最新バージョンです。",
    )


def test_update_message_box_overrides_inherited_light_on_light_colors():
    QApplication.instance() or QApplication([])
    parent = QDialog()
    parent.setProperty("dialogTheme", POENAVI_DIALOG_THEME.name)
    parent.setStyleSheet("QWidget { color: white; background: transparent; }")

    message = build_update_message_box(
        parent,
        QMessageBox.Information,
        "アップデート",
        "最新バージョンです。",
    )
    style = message.styleSheet()

    assert f"background-color: {POENAVI_DIALOG_THEME.background}" in style
    assert f"color: {POENAVI_DIALOG_THEME.text}" in style
    assert "QMessageBox QLabel" in style
    assert message.text() == "最新バージョンです。"
    parent.close()
