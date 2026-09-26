from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_restart import (
    _restart_command,
    _poetore_message_box_style,
    confirm_mode_switch_restart,
    restart_application,
)


def _app_with_mode(mode):
    app = QApplication.instance() or QApplication([])
    app.setProperty("appMode", mode)
    return app


def test_same_mode_does_not_prompt():
    _app_with_mode("poetore")
    config = {
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        }
    }

    with patch("src.app_restart.QMessageBox.question") as question:
        assert confirm_mode_switch_restart(None, config) is False

    question.assert_not_called()


def test_changed_mode_restarts_after_ok():
    _app_with_mode("poetore")
    config = {
        "startup": {
            "preferred_mode": "poenavi",
            "show_mode_selector": False,
        }
    }

    with (
        patch(
            "src.app_restart._ask_mode_switch_restart",
            return_value=QMessageBox.Ok,
        ) as question,
        patch(
            "src.app_restart.restart_application",
            return_value=True,
        ) as restart,
    ):
        assert confirm_mode_switch_restart(None, config) is True

    assert question.call_args.args[1] == "poetore"
    assert "選択した設定へ切り替わります" in question.call_args.args[2]
    restart.assert_called_once_with()


def test_changed_mode_with_selector_explains_mode_will_be_selected_again():
    _app_with_mode("poenavi")
    config = {
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": True,
        }
    }

    with (
        patch(
            "src.app_restart._ask_mode_switch_restart",
            return_value=QMessageBox.Cancel,
        ) as question,
        patch("src.app_restart.restart_application") as restart,
    ):
        assert confirm_mode_switch_restart(None, config) is False

    assert "もう一度選択します" in question.call_args.args[2]
    restart.assert_not_called()


def test_changed_poe_version_prompts_even_when_mode_is_unchanged():
    _app_with_mode("poetore")
    config = {
        "poe_version": "poe2",
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        },
    }

    with (
        patch(
            "src.app_restart._ask_mode_switch_restart",
            return_value=QMessageBox.Cancel,
        ) as question,
        patch("src.app_restart.restart_application") as restart,
    ):
        assert confirm_mode_switch_restart(
            None, config, current_poe_version="poe1"
        ) is False

    message = question.call_args.args[2]
    assert "PoE版：PoE1 → PoE2" in message
    assert "今すぐ再起動しますか" in message
    restart.assert_not_called()


def test_same_poe_version_and_mode_do_not_prompt():
    _app_with_mode("poetore")
    config = {
        "poe_version": "poe1",
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        },
    }

    with patch("src.app_restart._ask_mode_switch_restart") as question:
        assert confirm_mode_switch_restart(
            None, config, current_poe_version="poe1"
        ) is False

    question.assert_not_called()


def test_poetore_restart_prompt_uses_teal_neutral_theme():
    style = _poetore_message_box_style()

    assert "#65FFCA" in style
    assert "#111416" in style
    assert "QMessageBox QPushButton" in style


def test_development_restart_command_runs_main_script():
    with (
        patch("src.app_restart.sys.frozen", False, create=True),
        patch("src.app_restart.sys.argv", ["main.py", "--sample"]),
        patch("src.app_restart.os.getpid", return_value=4321),
    ):
        program, arguments = _restart_command()

    assert program
    assert arguments[0].endswith("main.py")
    assert arguments[1:] == [
        "--sample",
        "--single-instance-restart-pid=4321",
    ]


def test_restart_command_replaces_existing_internal_pid_argument():
    with (
        patch("src.app_restart.sys.frozen", True, create=True),
        patch(
            "src.app_restart.sys.argv",
            ["PoENavi.exe", "--single-instance-restart-pid=111"],
        ),
        patch("src.app_restart.os.getpid", return_value=4321),
    ):
        _program, arguments = _restart_command()

    assert arguments == ["--single-instance-restart-pid=4321"]


def test_restart_does_not_quit_when_detached_process_fails():
    app = _app_with_mode("poenavi")

    with (
        patch(
            "src.app_restart.QProcess.startDetached",
            return_value=(False, 0),
        ),
        patch.object(app, "quit") as quit_app,
    ):
        assert restart_application() is False

    quit_app.assert_not_called()


def test_restart_quits_after_detached_process_starts():
    app = _app_with_mode("poenavi")

    with (
        patch(
            "src.app_restart.QProcess.startDetached",
            return_value=(True, 123),
        ),
        patch.object(app, "quit") as quit_app,
    ):
        assert restart_application() is True

    quit_app.assert_called_once_with()
