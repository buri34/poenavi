"""両起動モードで共通利用する起動時アップデート確認。"""

import sys

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from src.ui.update_dialogs import UpdateAvailableDialog, UpdateProgressDialog
from src.update.qt_controller import UpdateController
from src.utils.config_manager import ConfigManager


def run_startup_update_gate(config: dict, parent=None) -> bool:
    """更新確認を完了し、通常起動を続ける場合はTrueを返す。"""
    controller = UpdateController(parent)
    check_loop = QEventLoop()
    result = {"release": None, "error": None}

    def on_finished(release, _manual):
        result["release"] = release
        check_loop.quit()

    def on_failed(message, _manual):
        result["error"] = message
        check_loop.quit()

    controller.check_finished.connect(on_finished)
    controller.check_failed.connect(on_failed)
    QTimer.singleShot(0, lambda: controller.check(False))
    check_loop.exec()
    controller.check_finished.disconnect(on_finished)
    controller.check_failed.disconnect(on_failed)

    release = result["release"]
    if release is None:
        return True
    if config.get("notified_update_version") == release.version:
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

    def on_progress(done, total):
        progress.set_progress(done, total)

    def on_ready(archive, _release):
        download_result["archive"] = archive
        download_loop.quit()

    def on_download_failed(message):
        download_result["error"] = message
        download_loop.quit()

    def on_cancelled():
        download_result["cancelled"] = True
        download_loop.quit()

    controller.download_progress.connect(on_progress)
    controller.download_ready.connect(on_ready)
    controller.download_failed.connect(on_download_failed)
    controller.download_cancelled.connect(on_cancelled)
    progress.show()
    QTimer.singleShot(0, lambda: controller.download(release))
    download_loop.exec()
    progress.close()

    if download_result["cancelled"]:
        return True
    if download_result["error"]:
        QMessageBox.warning(
            parent,
            "アップデート",
            f"更新をダウンロードできませんでした。\n{download_result['error']}",
        )
        return True

    answer = QMessageBox.question(
        parent,
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
        QMessageBox.critical(parent, "アップデート", str(exc))
        return True
    return False
