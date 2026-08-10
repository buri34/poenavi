"""設定変更後にPoENaviを安全に再起動する共通処理。"""

import os
from pathlib import Path
import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_mode import POETORE_MODE, normalize_app_mode, startup_preferences
from src.single_instance import RESTART_PID_PREFIX
from src.ui.app_theme import POETORE_THEME


def _restart_command():
    """開発実行とPyInstaller版のそれぞれに合う再起動コマンドを返す。"""
    forwarded_arguments = [
        argument for argument in sys.argv[1:]
        if not argument.startswith(RESTART_PID_PREFIX)
    ]
    forwarded_arguments.append(f"{RESTART_PID_PREFIX}{os.getpid()}")
    if getattr(sys, "frozen", False):
        return sys.executable, forwarded_arguments
    main_script = str(Path(__file__).resolve().parents[1] / "main.py")
    return sys.executable, [main_script, *forwarded_arguments]


def restart_application():
    """新しいプロセスを起動できた場合だけ、現在のアプリを終了する。"""
    program, arguments = _restart_command()
    result = QProcess.startDetached(program, arguments, os.getcwd())
    started = result[0] if isinstance(result, tuple) else result
    if not started:
        return False
    app = QApplication.instance()
    if app is not None:
        app.quit()
    return True


def _poetore_message_box_style():
    return f"""
        QMessageBox {{
            background-color: {POETORE_THEME.background};
        }}
        QMessageBox QLabel {{
            background-color: transparent;
            color: {POETORE_THEME.text};
        }}
        QMessageBox QPushButton {{
            min-width: 72px;
            padding: 5px 12px;
            background-color: {POETORE_THEME.panel};
            color: {POETORE_THEME.accent};
            border: 1px solid {POETORE_THEME.accent};
            border-radius: 4px;
        }}
        QMessageBox QPushButton:hover {{
            background-color: #382440;
        }}
        QMessageBox QPushButton:pressed {{
            background-color: #4A2D54;
        }}
    """


def _ask_mode_switch_restart(parent, current_mode, text):
    if current_mode != POETORE_MODE:
        return QMessageBox.question(
            parent,
            "モード切り替え",
            text,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )

    message_box = QMessageBox(parent)
    message_box.setWindowTitle("モード切り替え")
    message_box.setIcon(QMessageBox.Question)
    message_box.setText(text)
    message_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    message_box.setDefaultButton(QMessageBox.Ok)
    message_box.setStyleSheet(_poetore_message_box_style())
    return message_box.exec()


def confirm_mode_switch_restart(parent, config):
    """保存後の希望モードが現在モードと異なる時だけ再起動を確認する。"""
    app = QApplication.instance()
    current_mode = normalize_app_mode(
        app.property("appMode") if app is not None else None
    )
    preferred_mode, show_selector = startup_preferences(config)
    if preferred_mode == current_mode:
        return False

    next_step = (
        "再起動後に、起動するモードをもう一度選択します。"
        if show_selector
        else "再起動後に、選択したモードへ切り替わります。"
    )
    message = (
        "起動モードの変更を保存しました。\n"
        "モードを切り替えるため、今すぐ再起動しますか？\n\n"
        f"{next_step}"
    )
    result = _ask_mode_switch_restart(parent, current_mode, message)
    if result != QMessageBox.Ok:
        return False

    if restart_application():
        return True

    QMessageBox.warning(
        parent,
        "再起動エラー",
        "アプリを再起動できませんでした。\n"
        "設定は保存されているため、いったん終了して起動し直してください。",
    )
    return False
