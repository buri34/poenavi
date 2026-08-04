from pathlib import Path
import shutil
import time
from typing import Callable
import zipfile

from src.update.artifacts import validate_update_archive


REQUIRED_INSTALL_FILES = ("PoENavi.exe", "PoENaviUpdater.exe")


class UpdateApplyError(RuntimeError):
    def __init__(self, message: str, backup: Path | None = None):
        super().__init__(message)
        self.backup = backup

    def user_message(self) -> str:
        if self.backup is None:
            return str(self)
        return f"{self}\n\n対象フォルダ:\n{self.backup}"


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


def _validate_install_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        detail = "フォルダではありません"
    else:
        missing = [name for name in REQUIRED_INSTALL_FILES if not (path / name).is_file()]
        if not missing:
            return
        detail = f"不足しているファイル: {', '.join(missing)}"

    if label == "既存のバックアップ":
        message = (
            f"{label}の内容を安全に確認できないため、アップデートを中止しました。"
            f"\n（{detail}）\n\n"
            "対処方法:\n"
            "1. この画面を閉じます。\n"
            "2. 下記の対象フォルダを、PoENaviフォルダの外へ移動します。"
            "削除する必要はありません。\n"
            "3. ぽえなびを起動し、もう一度アップデートしてください。\n\n"
            "安全を確認できなかったため、ファイルの削除や変更は行っていません。"
        )
    else:
        message = (
            f"{label}の内容を確認できないため、アップデートを中止しました。"
            f"\n（{detail}）\n\n"
            "対処方法:\n"
            "1. この画面を閉じます。\n"
            "2. 公式配布の PoENavi.zip をもう一度ダウンロードします。\n"
            "3. ZIPを新しいフォルダへ展開し、PoENavi.exeを起動してください。\n\n"
            "現在のフォルダは変更していません。"
        )
    raise UpdateApplyError(message, path)


def _next_stale_backup_path(backup: Path, timestamp: str) -> Path:
    base = backup.with_name(f"{backup.name}-old-{timestamp}")
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = backup.with_name(f"{base.name}-{suffix}")
        suffix += 1
    return candidate


def apply_update(
    archive: Path,
    install_dir: Path,
    work_dir: Path,
    launcher: Callable[[Path], object],
    startup_check: Callable[[object], bool] = lambda _process: True,
    timestamp: Callable[[], str] = lambda: time.strftime("%Y%m%d-%H%M%S"),
) -> Path:
    archive = archive.resolve()
    install_dir = install_dir.resolve()
    work_dir = work_dir.resolve()
    validate_update_archive(archive)

    stage = work_dir / "stage"
    backup = install_dir.with_name(f"{install_dir.name}.backup")
    failed = install_dir.with_name(f"{install_dir.name}.failed")
    shutil.rmtree(stage, ignore_errors=True)
    _validate_install_directory(install_dir, "現在のインストール先")
    if failed.exists():
        raise UpdateApplyError(
            "前回のアップデートで作成された失敗フォルダが残っているため、"
            "アップデートを中止しました。\n\n"
            "対処方法:\n"
            "1. この画面を閉じます。\n"
            "2. 下記の対象フォルダを、PoENaviフォルダの外へ移動します。"
            "削除する必要はありません。\n"
            "3. ぽえなびを起動し、もう一度アップデートしてください。\n\n"
            "安全のため、失敗フォルダは自動削除していません。",
            failed,
        )

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

    stale_backup = None
    if backup.exists():
        _validate_install_directory(backup, "既存のバックアップ")
        stale_backup = _next_stale_backup_path(backup, timestamp())
        try:
            retry_transient_file_operation(lambda: backup.rename(stale_backup))
        except Exception as exc:
            raise UpdateApplyError(
                "既存のバックアップを移動できなかったため、アップデートを中止しました。"
                f"\n（Windowsからの詳細: {exc}）\n\n"
                "対処方法:\n"
                "1. この画面を閉じます。\n"
                "2. OneDriveの同期やセキュリティソフトの確認処理が終わるまで待ちます。\n"
                "3. ぽえなびを起動し、もう一度アップデートしてください。\n"
                "4. 繰り返し発生する場合は、Windowsを再起動してから再度お試しください。\n\n"
                "ファイルの削除や変更は行っていません。",
                backup,
            ) from exc

    backup_created = False
    try:
        retry_transient_file_operation(lambda: install_dir.rename(backup))
        backup_created = True
        shutil.move(str(replacement), str(install_dir))
        process = launcher(install_dir / "PoENavi.exe")
        if not startup_check(process):
            raise RuntimeError("更新後のぽえなびが起動直後に終了しました")
        if stale_backup is not None:
            shutil.rmtree(stale_backup, ignore_errors=True)
        return backup
    except Exception as exc:
        if backup_created and install_dir.exists():
            if failed.exists():
                shutil.rmtree(failed)
            retry_transient_file_operation(lambda: install_dir.rename(failed))
        if backup_created and backup.exists():
            retry_transient_file_operation(lambda: backup.rename(install_dir))
        if stale_backup is not None and stale_backup.exists() and not backup.exists():
            retry_transient_file_operation(lambda: stale_backup.rename(backup))
        raise UpdateApplyError(
            "アップデートに失敗したため、更新前のぽえなびを復元しました。"
            f"\n（詳細: {exc}）\n\n"
            "対処方法:\n"
            "1. この画面を閉じます。\n"
            "2. 現在のPoENavi.exeを起動できることを確認します。\n"
            "3. 起動できた場合は、もう一度アップデートしてください。\n"
            "4. 繰り返し失敗する場合は、この画面の内容を添えてご報告ください。",
            install_dir,
        ) from exc
