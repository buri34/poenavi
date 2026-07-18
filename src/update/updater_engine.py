from pathlib import Path
import shutil
import time
from typing import Callable
import zipfile

from src.update.artifacts import validate_update_archive


class UpdateApplyError(RuntimeError):
    def __init__(self, message: str, backup: Path | None = None):
        super().__init__(message)
        self.backup = backup


def retry_transient_file_operation(
    operation: Callable[[], object],
    attempts: int = 10,
    delay: float = 1.0,
    sleep=time.sleep,
):
    """Retry Windows file operations that can briefly fail during AV scans."""
    for attempt in range(attempts):
        try:
            return operation()
        except PermissionError:
            if attempt == attempts - 1:
                raise
            sleep(delay)


def wait_for_process_exit(
    pid: int,
    timeout: float,
    process_running: Callable[[int], bool],
    sleep=time.sleep,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(pid):
            return True
        sleep(0.2)
    return not process_running(pid)


def apply_update(
    archive: Path,
    install_dir: Path,
    work_dir: Path,
    launcher: Callable[[Path], object],
    startup_check: Callable[[object], bool] = lambda _process: True,
) -> Path:
    archive = archive.resolve()
    install_dir = install_dir.resolve()
    work_dir = work_dir.resolve()
    validate_update_archive(archive)

    stage = work_dir / "stage"
    backup = install_dir.with_name(f"{install_dir.name}.backup")
    shutil.rmtree(stage, ignore_errors=True)
    if backup.exists():
        raise UpdateApplyError(f"既存のバックアップがあります: {backup}", backup)

    stage.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(stage)

    wrapped_replacement = stage / "PoENavi"
    replacement = (
        wrapped_replacement
        if (wrapped_replacement / "PoENavi.exe").is_file()
        else stage
    )
    if not (replacement / "PoENavi.exe").is_file():
        raise UpdateApplyError("更新後の PoENavi.exe がありません")

    backup_created = False
    try:
        retry_transient_file_operation(lambda: install_dir.rename(backup))
        backup_created = True
        shutil.move(str(replacement), str(install_dir))
        process = launcher(install_dir / "PoENavi.exe")
        if not startup_check(process):
            raise RuntimeError("更新後のぽえなびが起動直後に終了しました")
        return backup
    except Exception as exc:
        if backup_created and install_dir.exists():
            failed = install_dir.with_name(f"{install_dir.name}.failed")
            if failed.exists():
                shutil.rmtree(failed)
            retry_transient_file_operation(lambda: install_dir.rename(failed))
        if backup_created and backup.exists():
            retry_transient_file_operation(lambda: backup.rename(install_dir))
        raise UpdateApplyError(
            f"更新に失敗したため旧版を復元しました: {exc}",
            backup,
        ) from exc
