from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.ui.dialog_theme import POENAVI_DIALOG_THEME
from src.ui.update_dialogs import build_update_message_box
from src.update.qt_controller import UpdateController
from src.update.startup_gate import (
    _run_update_gate,
    run_manual_update_check,
    run_startup_update_gate,
)
from src.update.release_client import ReleaseInfo


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


def test_manual_check_timeout_continues_with_warning():
    QApplication.instance() or QApplication([])

    class NeverThread:
        def __init__(self, _target):
            pass

        def start(self):
            pass

    def controller_factory(parent=None):
        return UpdateController(parent, thread_factory=NeverThread)

    with patch(
        "src.update.startup_gate.UpdateController",
        side_effect=controller_factory,
    ), patch(
        "src.update.startup_gate.CHECK_TIMEOUT_MS",
        1,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message:
        assert run_manual_update_check({}) is True

    assert "タイムアウト" in show_message.call_args.args[3]


def test_busy_manual_check_continues_with_warning():
    QApplication.instance() or QApplication([])
    controller = UpdateController()
    controller._checking = True

    with patch(
        "src.update.startup_gate.UpdateController",
        return_value=controller,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message:
        assert run_manual_update_check({}) is True

    assert "実行中" in show_message.call_args.args[3]


def test_manual_check_failure_continues_with_warning():
    QApplication.instance() or QApplication([])
    controller = UpdateController()
    controller.check = Mock(side_effect=lambda manual: (
        controller.check_failed.emit("network down", manual),
        True,
    )[1])

    with patch(
        "src.update.startup_gate.UpdateController",
        return_value=controller,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message:
        assert run_manual_update_check({}) is True

    assert "network down" in show_message.call_args.args[3]


def _release():
    return ReleaseInfo(
        "2.5.0",
        "notes",
        "https://github.com/page",
        "https://github.com/a.zip",
        "https://github.com/a.sha256",
    )


def test_download_timeout_cancels_and_never_launches_updater():
    QApplication.instance() or QApplication([])
    release = _release()
    controller = UpdateController()
    controller.check = Mock(side_effect=lambda manual: (
        controller.check_finished.emit(release, manual),
        True,
    )[1])
    controller.download = Mock(return_value=True)
    controller.cancel_download = Mock()
    controller.launch_updater = Mock()
    progress = Mock()
    progress.cancel_requested = Mock()

    with patch(
        "src.update.startup_gate.UpdateController",
        return_value=controller,
    ), patch(
        "src.update.startup_gate.UpdateAvailableDialog",
    ) as available_dialog, patch(
        "src.update.startup_gate.UpdateProgressDialog",
        return_value=progress,
    ), patch(
        "src.update.startup_gate.DOWNLOAD_INACTIVITY_TIMEOUT_MS",
        1,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message, patch(
        "src.update.startup_gate.ConfigManager.save_config",
    ), patch(
        "src.update.startup_gate.sys.platform",
        "win32",
    ), patch(
        "src.update.startup_gate.sys.frozen",
        True,
        create=True,
    ):
        available_dialog.return_value.exec.return_value = True
        assert _run_update_gate({}, manual=True) is True

    controller.cancel_download.assert_called_once_with()
    controller.launch_updater.assert_not_called()
    assert "一定時間進まなかった" in show_message.call_args.args[3]

    controller.download_ready.emit("late.zip", release)
    controller.launch_updater.assert_not_called()


def test_busy_download_continues_with_warning():
    QApplication.instance() or QApplication([])
    release = _release()
    controller = UpdateController()
    controller.check = Mock(side_effect=lambda manual: (
        controller.check_finished.emit(release, manual),
        True,
    )[1])
    controller.download = Mock(return_value=False)
    controller.cancel_download = Mock()
    controller.launch_updater = Mock()
    progress = Mock()
    progress.cancel_requested = Mock()

    with patch(
        "src.update.startup_gate.UpdateController",
        return_value=controller,
    ), patch(
        "src.update.startup_gate.UpdateAvailableDialog",
    ) as available_dialog, patch(
        "src.update.startup_gate.UpdateProgressDialog",
        return_value=progress,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message, patch(
        "src.update.startup_gate.ConfigManager.save_config",
    ), patch(
        "src.update.startup_gate.sys.platform",
        "win32",
    ), patch(
        "src.update.startup_gate.sys.frozen",
        True,
        create=True,
    ):
        available_dialog.return_value.exec.return_value = True
        assert _run_update_gate({}, manual=True) is True

    controller.cancel_download.assert_not_called()
    controller.launch_updater.assert_not_called()
    assert "実行中" in show_message.call_args.args[3]


def test_download_progress_refreshes_inactivity_watchdog():
    QApplication.instance() or QApplication([])
    release = _release()
    controller = UpdateController()
    controller.check = Mock(side_effect=lambda manual: (
        controller.check_finished.emit(release, manual),
        True,
    )[1])

    def download(_release_info):
        QTimer.singleShot(
            60,
            lambda: controller.download_progress.emit(50, 100),
        )
        QTimer.singleShot(
            120,
            lambda: controller.download_ready.emit("ready.zip", release),
        )
        return True

    controller.download = Mock(side_effect=download)
    controller.cancel_download = Mock()
    controller.launch_updater = Mock()
    progress = Mock()
    progress.cancel_requested = Mock()

    with patch(
        "src.update.startup_gate.UpdateController",
        return_value=controller,
    ), patch(
        "src.update.startup_gate.UpdateAvailableDialog",
    ) as available_dialog, patch(
        "src.update.startup_gate.UpdateProgressDialog",
        return_value=progress,
    ), patch(
        "src.update.startup_gate.DOWNLOAD_INACTIVITY_TIMEOUT_MS",
        100,
    ), patch(
        "src.update.startup_gate.show_update_message",
        return_value=QMessageBox.No,
    ) as show_message, patch(
        "src.update.startup_gate.ConfigManager.save_config",
    ), patch(
        "src.update.startup_gate.sys.platform",
        "win32",
    ), patch(
        "src.update.startup_gate.sys.frozen",
        True,
        create=True,
    ):
        available_dialog.return_value.exec.return_value = True
        assert _run_update_gate({}, manual=True) is True

    progress.set_progress.assert_called_once_with(50, 100)
    controller.cancel_download.assert_not_called()
    controller.launch_updater.assert_not_called()
    assert show_message.call_args.args[1] == QMessageBox.Question


def test_cancelled_download_continues_without_applying():
    QApplication.instance() or QApplication([])
    release = _release()
    controller = UpdateController()
    controller.check = Mock(side_effect=lambda manual: (
        controller.check_finished.emit(release, manual),
        True,
    )[1])
    controller.download = Mock(side_effect=lambda _release_info: (
        controller.download_cancelled.emit(),
        True,
    )[1])
    controller.cancel_download = Mock()
    controller.launch_updater = Mock()
    progress = Mock()
    progress.cancel_requested = Mock()

    with patch(
        "src.update.startup_gate.UpdateController",
        return_value=controller,
    ), patch(
        "src.update.startup_gate.UpdateAvailableDialog",
    ) as available_dialog, patch(
        "src.update.startup_gate.UpdateProgressDialog",
        return_value=progress,
    ), patch(
        "src.update.startup_gate.show_update_message",
    ) as show_message, patch(
        "src.update.startup_gate.ConfigManager.save_config",
    ), patch(
        "src.update.startup_gate.sys.platform",
        "win32",
    ), patch(
        "src.update.startup_gate.sys.frozen",
        True,
        create=True,
    ):
        available_dialog.return_value.exec.return_value = True
        assert _run_update_gate({}, manual=True) is True

    controller.launch_updater.assert_not_called()
    show_message.assert_not_called()


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
