"""両起動モードで共通利用する起動時アップデート確認。"""

import sys

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from src.ui.update_dialogs import (
    UpdateAvailableDialog,
    UpdateProgressDialog,
    show_update_message,
)
from src.update.qt_controller import UpdateController
from src.utils.config_manager import ConfigManager

CHECK_TIMEOUT_MS = 30_000
DOWNLOAD_INACTIVITY_TIMEOUT_MS = 60_000


def _disconnect(signal, slot) -> None:
    try:
        signal.disconnect(slot)
    except (RuntimeError, TypeError):
        pass


def _run_update_gate(config: dict, parent=None, manual: bool = False) -> bool:
    """更新確認を完了し、通常起動を続ける場合はTrueを返す。"""
    controller = UpdateController(parent)
    check_loop = QEventLoop()
    result = {"release": None, "error": None}
    check_active = True
    check_watchdog = QTimer()
    check_watchdog.setSingleShot(True)

    def on_finished(release, _manual):
        if not check_active:
            return
        result["release"] = release
        check_loop.quit()

    def on_failed(message, _manual):
        if not check_active:
            return
        result["error"] = message
        check_loop.quit()

    def on_check_timeout():
        if not check_active:
            return
        result["error"] = "更新確認がタイムアウトしました。"
        check_loop.quit()

    def start_check():
        if not controller.check(manual):
            result["error"] = "別の更新確認処理が実行中です。"
            check_loop.quit()
            return
        check_watchdog.start(CHECK_TIMEOUT_MS)

    controller.check_finished.connect(on_finished)
    controller.check_failed.connect(on_failed)
    check_watchdog.timeout.connect(on_check_timeout)
    QTimer.singleShot(0, start_check)
    check_loop.exec()
    check_active = False
    check_watchdog.stop()
    _disconnect(controller.check_finished, on_finished)
    _disconnect(controller.check_failed, on_failed)

    release = result["release"]
    if release is None:
        if manual:
            if result["error"]:
                show_update_message(
                    parent,
                    QMessageBox.Warning,
                    "アップデート",
                    f"更新を確認できませんでした。\n{result['error']}",
                )
            else:
                show_update_message(
                    parent,
                    QMessageBox.Information,
                    "アップデート",
                    "最新バージョンです。",
                )
        return True
    if (
        not manual
        and config.get("notified_update_version") == release.version
    ):
        return True

    config["notified_update_version"] = release.version
    ConfigManager.save_config(config)
    supported = getattr(sys, "frozen", False) and sys.platform == "win32"
    dialog = UpdateAvailableDialog(release, supported, parent)
    if not dialog.exec():
        return True
    if not supported:
        QDesktopServices.openUrl(QUrl(release.page_url))
        return True

    progress = UpdateProgressDialog(release.version, parent)
    progress.cancel_requested.connect(controller.cancel_download)
    download_loop = QEventLoop()
    download_result = {"archive": None, "error": None, "cancelled": False}
    download_active = True
    download_watchdog = QTimer()
    download_watchdog.setSingleShot(True)

    def on_progress(done, total):
        if not download_active:
            return
        progress.set_progress(done, total)
        download_watchdog.start(DOWNLOAD_INACTIVITY_TIMEOUT_MS)

    def on_ready(archive, _release):
        if not download_active:
            return
        download_result["archive"] = archive
        download_loop.quit()

    def on_download_failed(message):
        if not download_active:
            return
        download_result["error"] = message
        download_loop.quit()

    def on_cancelled():
        if not download_active:
            return
        download_result["cancelled"] = True
        download_loop.quit()

    def on_download_timeout():
        if not download_active:
            return
        download_result["error"] = (
            "ダウンロードが一定時間進まなかったため中止しました。"
        )
        controller.cancel_download()
        download_loop.quit()

    def start_download():
        if not controller.download(release):
            download_result["error"] = "別のダウンロード処理が実行中です。"
            download_loop.quit()
            return
        download_watchdog.start(DOWNLOAD_INACTIVITY_TIMEOUT_MS)

    controller.download_progress.connect(on_progress)
    controller.download_ready.connect(on_ready)
    controller.download_failed.connect(on_download_failed)
    controller.download_cancelled.connect(on_cancelled)
    download_watchdog.timeout.connect(on_download_timeout)
    progress.show()
    QTimer.singleShot(0, start_download)
    download_loop.exec()
    download_active = False
    download_watchdog.stop()
    _disconnect(controller.download_progress, on_progress)
    _disconnect(controller.download_ready, on_ready)
    _disconnect(controller.download_failed, on_download_failed)
    _disconnect(controller.download_cancelled, on_cancelled)
    _disconnect(progress.cancel_requested, controller.cancel_download)
    progress.close()

    if download_result["cancelled"]:
        return True
    if download_result["error"] or download_result["archive"] is None:
        error = download_result["error"] or "更新ファイルを取得できませんでした。"
        show_update_message(
            parent,
            QMessageBox.Warning,
            "アップデート",
            f"更新をダウンロードできませんでした。\n{error}",
        )
        return True

    answer = show_update_message(
        parent,
        QMessageBox.Question,
        "アップデートを適用",
        f"v{release.version} の検証が完了しました。\n"
        "アプリを終了して更新しますか？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    if answer != QMessageBox.Yes:
        return True
    try:
        controller.launch_updater(download_result["archive"])
    except Exception as exc:
        show_update_message(
            parent,
            QMessageBox.Critical,
            "アップデート",
            str(exc),
        )
        return True
    return False


def run_startup_update_gate(config: dict, parent=None) -> bool:
    """起動時の自動更新確認を行う。"""
    return _run_update_gate(config, parent, manual=False)


def run_manual_update_check(config: dict, parent=None) -> bool:
    """ユーザー操作による更新確認を行い、同じ版の再通知も許可する。"""
    return _run_update_gate(config, parent, manual=True)
