"""設定変更後にPoENaviを安全に再起動する共通処理。"""

import os
from pathlib import Path
import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_mode import normalize_app_mode, startup_preferences


def _restart_command():
    """開発実行とPyInstaller版のそれぞれに合う再起動コマンドを返す。"""
    if getattr(sys, "frozen", False):
        return sys.executable, sys.argv[1:]
    main_script = str(Path(__file__).resolve().parents[1] / "main.py")
    return sys.executable, [main_script, *sys.argv[1:]]


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
    result = QMessageBox.question(
        parent,
        "モード切り替え",
        "起動モードの変更を保存しました。\n"
        "モードを切り替えるため、今すぐ再起動しますか？\n\n"
        f"{next_step}",
        QMessageBox.Ok | QMessageBox.Cancel,
        QMessageBox.Ok,
    )
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
