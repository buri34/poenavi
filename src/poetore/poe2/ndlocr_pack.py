"""Download and install the optional NDLOCR high-accuracy OCR pack."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, Signal

from src.update.artifacts import (
    DownloadCancelled,
    download_file,
    parse_checksum,
    verify_sha256,
)
from src.version import APP_VERSION

PACK_VERSION = "1.3.1"
PACK_ASSET_NAME = "PoENavi-HighAccuracyOCR.zip"
PACK_CHECKSUM_NAME = f"{PACK_ASSET_NAME}.sha256"
PACK_ARCHIVE_ROOT = "PoENavi-HighAccuracyOCR"
PACK_DIR_ENV = "POENAVI_NDLOCR_PACK_DIR"
PACK_URL_ENV = "POENAVI_NDLOCR_PACK_BASE_URL"
MAX_PACK_ENTRIES = 5_000
MAX_PACK_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
MAX_PACK_SINGLE_FILE_SIZE = 256 * 1024 * 1024
MAX_PACK_COMPRESSION_RATIO = 100
REQUIRED_MODELS = (
    "deim-s-1024x1024.onnx",
    "parseq-ndl-24x256-30-tiny-189epoch-tegaki3-r8data-202604.onnx",
    "parseq-ndl-24x384-50-tiny-300epoch-tegaki3-r8data-202604.onnx",
    "parseq-ndl-24x768-100-tiny-153epoch-tegaki3-r8data-202604.onnx",
)


def _default_pack_parent() -> Path:
    configured = os.environ.get(PACK_DIR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "PoENavi" / "ocr-packs"
        return Path.home() / "AppData" / "Local" / "PoENavi" / "ocr-packs"
    return Path(tempfile.gettempdir()) / "PoENavi" / "ocr-packs"


def pack_install_dir() -> Path:
    return _default_pack_parent() / f"ndlocr-{PACK_VERSION}"


def installed_helper_path() -> Path | None:
    root = pack_install_dir()
    marker = root / ".installed.json"
    helper = root / "PoENaviNdlOcr" / "PoENaviNdlOcr.exe"
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if payload.get("pack_version") != PACK_VERSION or not helper.is_file():
        return None
    model_dir = root / "PoENaviNdlOcr" / "_internal" / "model"
    if not all((model_dir / name).is_file() for name in REQUIRED_MODELS):
        return None
    return helper


def pack_is_installed() -> bool:
    return installed_helper_path() is not None


def pack_asset_urls(app_version: str = APP_VERSION) -> tuple[str, str]:
    override = os.environ.get(PACK_URL_ENV, "").strip().rstrip("/")
    base = override or (
        "https://github.com/buri34/poenavi/releases/download/"
        f"v{app_version}"
    )
    return f"{base}/{PACK_ASSET_NAME}", f"{base}/{PACK_CHECKSUM_NAME}"


def _cleanup_stale_work_dirs(parent: Path) -> None:
    for pattern in ("ndlocr-download-*", "ndlocr-install-*"):
        for candidate in parent.glob(pattern):
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)


def _validate_pack_archive(path: Path) -> None:
    required_suffixes = {
        f"{PACK_ARCHIVE_ROOT}/PoENaviNdlOcr/PoENaviNdlOcr.exe",
        *{
            f"{PACK_ARCHIVE_ROOT}/PoENaviNdlOcr/_internal/model/{name}"
            for name in REQUIRED_MODELS
        },
        f"{PACK_ARCHIVE_ROOT}/THIRD_PARTY_LICENSES/NDLOCR-Lite-{PACK_VERSION}/LICENCE.txt",
        f"{PACK_ARCHIVE_ROOT}/THIRD_PARTY_LICENSES/NDLOCR-Lite-{PACK_VERSION}/LICENCE_DEPENDENCIES.txt",
    }
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_PACK_ENTRIES:
            raise ValueError("高精度OCRパックのファイル数が上限を超えています")
        names: set[str] = set()
        total_size = 0
        for info in entries:
            name = info.filename.replace("\\", "/")
            pure_path = PurePosixPath(name)
            if (
                not pure_path.parts
                or pure_path.is_absolute()
                or ".." in pure_path.parts
                or re.match(r"^[A-Za-z]:", name)
            ):
                raise ValueError(f"高精度OCRパックに危険なパスがあります: {name}")
            unix_mode = info.external_attr >> 16
            if unix_mode and (unix_mode & 0o170000) == 0o120000:
                raise ValueError("高精度OCRパックにリンクが含まれています")
            if info.file_size > MAX_PACK_SINGLE_FILE_SIZE:
                raise ValueError("高精度OCRパック内のファイルが大きすぎます")
            total_size += info.file_size
            if total_size > MAX_PACK_UNCOMPRESSED_SIZE:
                raise ValueError("高精度OCRパックの展開後サイズが上限を超えています")
            if info.file_size >= 1024 * 1024:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_PACK_COMPRESSION_RATIO:
                    raise ValueError("高精度OCRパックに異常な圧縮率のファイルがあります")
            names.add(name.rstrip("/"))
        missing = sorted(required_suffixes - names)
        if missing:
            raise ValueError("高精度OCRパックの必須ファイルが不足しています")


def install_pack_archive(
    archive_path: Path,
    expected_sha256: str,
    *,
    destination: Path | None = None,
) -> Path:
    destination = destination or pack_install_dir()
    if not verify_sha256(archive_path, expected_sha256):
        raise ValueError("高精度OCRパックのSHA-256が一致しません")
    _validate_pack_archive(archive_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="ndlocr-install-", dir=destination.parent)
    )
    backup = destination.with_name(f"{destination.name}.previous")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temporary_root)
        payload_root = temporary_root / PACK_ARCHIVE_ROOT
        if not (payload_root / "PoENaviNdlOcr" / "PoENaviNdlOcr.exe").is_file():
            raise ValueError("高精度OCRパックを展開できませんでした")
        marker = {
            "pack_version": PACK_VERSION,
            "archive_sha256": expected_sha256.lower(),
        }
        (payload_root / ".installed.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            destination.replace(backup)
        payload_root.replace(destination)
        shutil.rmtree(backup, ignore_errors=True)
        return destination
    except Exception:
        if not destination.exists() and backup.exists():
            backup.replace(destination)
        raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def download_and_install_pack(
    *,
    app_version: str = APP_VERSION,
    progress: Callable[[int, int], None] = lambda _done, _total: None,
    phase: Callable[[str], None] = lambda _phase: None,
    cancelled: Callable[[], bool] = lambda: False,
    downloader=download_file,
) -> Path:
    archive_url, checksum_url = pack_asset_urls(app_version)
    parent = _default_pack_parent()
    parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_work_dirs(parent)
    with tempfile.TemporaryDirectory(prefix="ndlocr-download-", dir=parent) as work:
        work_dir = Path(work)
        phase("checking")
        checksum_path = downloader(
            checksum_url,
            work_dir / PACK_CHECKSUM_NAME,
            lambda _done, _total: None,
            cancelled,
        )
        expected = parse_checksum(
            checksum_path.read_text(encoding="utf-8"),
            filename=PACK_ASSET_NAME,
        )
        phase("downloading")
        archive_path = downloader(
            archive_url,
            work_dir / PACK_ASSET_NAME,
            progress,
            cancelled,
        )
        phase("installing")
        return install_pack_archive(archive_path, expected)


@dataclass(frozen=True)
class PackStatus:
    state: str
    detail: str = ""
    done: int = 0
    total: int = 0


class NdlOcrPackController(QObject):
    """Application-lived background installer exposed to the settings dialog."""

    status_changed = Signal(object)

    def __init__(self, parent=None, *, worker=download_and_install_pack):
        super().__init__(parent)
        self._worker = worker
        self._cancel = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self.status = PackStatus("ready" if pack_is_installed() else "idle")

    def _publish(self, state: str, detail: str = "", done: int = 0, total: int = 0):
        self.status = PackStatus(state, detail, done, total)
        self.status_changed.emit(self.status)

    def ensure_started(self) -> None:
        if pack_is_installed():
            self._publish("ready")
            return
        with self._lock:
            if self._running:
                return
            self._running = True
        self._cancel.clear()

        def run():
            try:
                self._worker(
                    progress=lambda done, total: self._publish(
                        "downloading", done=done, total=total
                    ),
                    phase=lambda value: self._publish(value),
                    cancelled=self._cancel.is_set,
                )
                self._publish("ready")
            except DownloadCancelled:
                self._publish("idle")
            except Exception as exc:  # noqa: BLE001 - worker boundary
                self._publish("error", str(exc))
            finally:
                with self._lock:
                    self._running = False

        threading.Thread(
            target=run,
            name="ndlocr-pack-download",
            daemon=True,
        ).start()

    def retry(self) -> None:
        self.ensure_started()

    def close(self) -> None:
        self._cancel.set()
