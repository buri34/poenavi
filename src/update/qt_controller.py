from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from PySide6.QtCore import QCoreApplication, QObject, Signal

from src.update.artifacts import (
    DownloadCancelled,
    download_file,
    parse_checksum,
    validate_update_archive,
    verify_sha256,
)
from src.update.release_client import ReleaseInfo, fetch_latest_release
from src.version import APP_VERSION
from src.utils.i18n import get_locale, tr


class UpdateController(QObject):
    check_finished = Signal(object, bool)
    check_failed = Signal(str, bool)
    download_progress = Signal(int, int)
    download_ready = Signal(object, object)
    download_failed = Signal(str)
    download_cancelled = Signal()

    def __init__(self, parent=None, thread_factory=None):
        super().__init__(parent)
        self._thread_factory = thread_factory or (
            lambda target: threading.Thread(target=target, daemon=True)
        )
        self._checking = False
        self._downloading = False
        self._cancel = threading.Event()
        self._work_dir: Path | None = None
        self._ready_archive: Path | None = None
        self._ready_version: str | None = None
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.discard_download)
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            cleanup_timer = threading.Timer(10, self._cleanup_stale_update_dirs)
            cleanup_timer.daemon = True
            cleanup_timer.start()

    @staticmethod
    def _cleanup_stale_update_dirs() -> None:
        temp_dir = Path(tempfile.gettempdir())
        for path in temp_dir.glob("PoENavi-Updater-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    def check(self, manual: bool) -> None:
        if self._checking:
            return
        self._checking = True

        def work():
            try:
                self.check_finished.emit(
                    fetch_latest_release(APP_VERSION),
                    manual,
                )
            except Exception as exc:
                self.check_failed.emit(str(exc), manual)
            finally:
                self._checking = False

        self._thread_factory(work).start()

    def download(self, release: ReleaseInfo) -> None:
        if self._downloading:
            return
        cached = self.ready_archive(release.version)
        if cached is not None:
            self.download_ready.emit(cached, release)
            return
        if self._work_dir is not None:
            self.discard_download()
        self._downloading = True
        self._cancel.clear()
        self._work_dir = Path(
            tempfile.mkdtemp(prefix=f"PoENavi-{release.version}-")
        )

        def work():
            ready = False
            try:
                archive = download_file(
                    release.zip_url,
                    self._work_dir / "PoENavi.zip",
                    self.download_progress.emit,
                    self._cancel.is_set,
                )
                checksum_file = download_file(
                    release.checksum_url,
                    self._work_dir / "PoENavi.zip.sha256",
                    lambda _done, _total: None,
                    self._cancel.is_set,
                )
                expected = parse_checksum(
                    checksum_file.read_text(encoding="utf-8")
                )
                if not verify_sha256(archive, expected):
                    raise ValueError(
                        tr("update.checksum_mismatch")
                    )
                validate_update_archive(archive)
                self._ready_archive = archive
                self._ready_version = release.version
                ready = True
                self.download_ready.emit(archive, release)
            except DownloadCancelled:
                self.download_cancelled.emit()
            except Exception as exc:
                self.download_failed.emit(str(exc))
            finally:
                self._downloading = False
                if not ready and self._work_dir is not None:
                    shutil.rmtree(self._work_dir, ignore_errors=True)
                    self._work_dir = None

        self._thread_factory(work).start()

    def cancel_download(self) -> None:
        self._cancel.set()

    def ready_archive(self, version: str) -> Path | None:
        if self._ready_version != version:
            if self._ready_archive is not None:
                self.discard_download()
            return None
        if self._ready_archive is None or not self._ready_archive.is_file():
            self.discard_download()
            return None
        return self._ready_archive

    def discard_download(self) -> None:
        if self._work_dir is not None:
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None
        self._ready_archive = None
        self._ready_version = None

    def launch_updater(self, archive: Path) -> None:
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            raise RuntimeError(
                tr("update.windows_only")
            )

        install_dir = Path(sys.executable).resolve().parent
        source = install_dir / "PoENaviUpdater.exe"
        if not source.is_file():
            raise RuntimeError(tr("update.updater_missing"))

        updater_work = Path(tempfile.mkdtemp(prefix="PoENavi-Updater-"))
        updater_work.mkdir(parents=True, exist_ok=True)
        updater = updater_work / "PoENaviUpdater.exe"
        staged_archive = updater_work / "PoENavi.zip"
        try:
            shutil.copy2(source, updater)
            shutil.copy2(Path(archive).resolve(), staged_archive)
            subprocess.Popen(
                [
                    str(updater),
                    "--pid",
                    str(os.getpid()),
                    "--archive",
                    str(staged_archive),
                    "--install-dir",
                    str(install_dir),
                    "--work-dir",
                    str(updater_work),
                    "--language",
                    get_locale(),
                ],
                cwd=str(updater_work),
            )
        except Exception:
            shutil.rmtree(updater_work, ignore_errors=True)
            raise

        self.discard_download()
