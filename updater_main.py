import argparse
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PySide6.QtWidgets import QApplication, QMessageBox

from src.update.updater_engine import (
    UpdateApplyError,
    apply_update,
    wait_for_process_exit,
)


def process_running(pid: int) -> bool:
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def show_error(message: str) -> None:
    app = QApplication.instance() or QApplication([])
    QMessageBox.critical(None, "ぽえなび アップデート", message)
    app.processEvents()


def startup_stable(process) -> bool:
    time.sleep(3)
    return process.poll() is None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    install_dir = args.install_dir.resolve()
    if install_dir.parent == install_dir or not (install_dir / "PoENavi.exe").is_file():
        show_error("更新対象の PoENavi.exe が見つかりません。")
        return 2
    if not wait_for_process_exit(args.pid, 30, process_running):
        show_error("ぽえなびを終了できなかったため、更新を中止しました。")
        return 3

    try:
        backup = apply_update(
            args.archive,
            install_dir,
            args.work_dir,
            lambda exe: subprocess.Popen([str(exe)], cwd=str(exe.parent)),
            startup_check=startup_stable,
        )
    except UpdateApplyError as exc:
        suffix = f"\nバックアップ: {exc.backup}" if exc.backup else ""
        show_error(f"{exc}{suffix}")
        return 4

    shutil.rmtree(backup, ignore_errors=True)
    shutil.rmtree(args.work_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
