from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

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
    ), patch.object(
        QMessageBox,
        "information",
    ) as information:
        assert run_manual_update_check({}) is True

    information.assert_called_once_with(
        None,
        "アップデート",
        "最新バージョンです。",
    )
