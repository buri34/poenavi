"""設定変更後にPoENaviを安全に再起動する共通処理。"""

import os
from pathlib import Path
import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_mode import POETORE_MODE, normalize_app_mode, startup_preferences
from src.single_instance import RESTART_PID_PREFIX
from src.ui.app_theme import POETORE_THEME
from src.utils.poe_version_data import POE1, POE2, get_poe_label


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
            color: {POETORE_THEME.text};
            border: 1px solid #3A4245;
            border-radius: 4px;
        }}
        QMessageBox QPushButton:hover {{
            background-color: #25332F;
            border-color: {POETORE_THEME.accent};
        }}
        QMessageBox QPushButton:pressed {{
            background-color: #276B5A;
        }}
    """


def _ask_mode_switch_restart(parent, current_mode, text):
    if current_mode != POETORE_MODE:
        return QMessageBox.question(
            parent,
            "設定切り替え",
            text,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )

    message_box = QMessageBox(parent)
    message_box.setWindowTitle("設定切り替え")
    message_box.setIcon(QMessageBox.Question)
    message_box.setText(text)
    message_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    message_box.setDefaultButton(QMessageBox.Ok)
    message_box.setStyleSheet(_poetore_message_box_style())
    return message_box.exec()


def confirm_mode_switch_restart(parent, config, current_poe_version=None):
    """起動モードまたはPoE版の変更時に、安全な再起動を確認する。"""
    app = QApplication.instance()
    current_mode = normalize_app_mode(
        app.property("appMode") if app is not None else None
    )
    preferred_mode, show_selector = startup_preferences(config)
    requested_poe_version = str((config or {}).get("poe_version", POE1))
    poe_version_changed = (
        current_poe_version in (POE1, POE2)
        and requested_poe_version in (POE1, POE2)
        and requested_poe_version != current_poe_version
    )
    mode_changed = preferred_mode != current_mode
    if not mode_changed and not poe_version_changed:
        return False

    changes = []
    if poe_version_changed:
        changes.append(
            f"PoE版：{get_poe_label(current_poe_version)} → "
            f"{get_poe_label(requested_poe_version)}"
        )
    if mode_changed:
        changes.append("起動モード")
    change_summary = "\n".join(changes)
    if show_selector:
        next_step = "再起動後に、起動する設定をもう一度選択します。"
    else:
        next_step = "再起動後に、選択した設定へ切り替わります。"
    message = (
        f"次の変更を保存しました。\n{change_summary}\n\n"
        "設定を安全に切り替えるため、今すぐ再起動しますか？\n\n"
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
