"""Asynchronous persistent icon cache for Currency Exchange catalog items."""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import threading
import zlib
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.poetore.exchange_catalog import (
    divination_card_icon_path,
    placeholder_icon_path,
)
from src.utils.config_manager import ConfigManager

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_DIMENSION = 2048
MAX_IMAGE_PIXELS = 4 * 1024 * 1024
ALLOWED_ICON_HOSTS = frozenset({"web.poecdn.com"})


@dataclass(frozen=True)
class IconResult:
    path: Path
    source: str
    image_format: str | None = None

    @property
    def is_placeholder(self) -> bool:
        return self.source == "placeholder"


def _completed_future(result: IconResult) -> Future[IconResult]:
    future: Future[IconResult] = Future()
    future.set_result(result)
    return future


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 33
        or not data.startswith(b"\x89PNG\r\n\x1a\n")
        or data[12:16] != b"IHDR"
    ):
        return None
    dimensions = struct.unpack(">II", data[16:24])
    offset = 8
    saw_end = False
    while offset + 12 <= len(data):
        chunk_length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(data):
            return None
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + chunk_length]
        expected_crc = int.from_bytes(data[offset + 8 + chunk_length:chunk_end], "big")
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return None
        offset = chunk_end
        if chunk_type == b"IEND":
            saw_end = True
            break
    return dimensions if saw_end and offset == len(data) else None


def _gif_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 14
        or data[:6] not in {b"GIF87a", b"GIF89a"}
        or data[-1:] != b";"
    ):
        return None
    return struct.unpack("<HH", data[6:10])


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 4
        or not data.startswith(b"\xff\xd8")
        or not data.endswith(b"\xff\xd9")
    ):
        return None
    offset = 2
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while offset + 3 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            return None
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[offset:offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            return None
        if marker in start_of_frame:
            if segment_length < 7:
                return None
            height = int.from_bytes(data[offset + 3:offset + 5], "big")
            width = int.from_bytes(data[offset + 5:offset + 7], "big")
            return width, height
        offset += segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    if int.from_bytes(data[4:8], "little") + 8 != len(data):
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        return (
            1 + int.from_bytes(data[24:27], "little"),
            1 + int.from_bytes(data[27:30], "little"),
        )
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        return (
            int.from_bytes(data[26:28], "little") & 0x3FFF,
            int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    return None


def inspect_image(data: bytes) -> str | None:
    """Return a supported format only for bounded, structurally valid images."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    inspections = (
        ("png", _png_dimensions),
        ("jpeg", _jpeg_dimensions),
        ("gif", _gif_dimensions),
        ("webp", _webp_dimensions),
    )
    for image_format, inspect in inspections:
        dimensions = inspect(data)
        if dimensions is None:
            continue
        width, height = dimensions
        if (
            0 < width <= MAX_IMAGE_DIMENSION
            and 0 < height <= MAX_IMAGE_DIMENSION
            and width * height <= MAX_IMAGE_PIXELS
        ):
            return image_format
        return None
    return None


def _download_icon(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "image/png,image/jpeg,image/webp,image/gif",
            "Accept-Encoding": "identity",
            "User-Agent": "PoENavi/poetore-icon-cache",
        },
    )
    with urlopen(request, timeout=20) as response:
        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > MAX_IMAGE_BYTES:
            raise ValueError("Currency Exchange icon exceeds the size limit")
        data = response.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Currency Exchange icon exceeds the size limit")
    return data


class ExchangeIconCache:
    """Resolve bundled and remote icons without network work on the caller thread."""

    def __init__(
        self,
        cache_root: Path | None = None,
        *,
        fetcher: Callable[[str], bytes] = _download_icon,
        max_workers: int = 4,
    ):
        self.cache_root = cache_root or ConfigManager.get_user_data_path(
            "poetore-icon-cache"
        )
        self._fetcher = fetcher
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="poetore-icon",
        )
        self._memory: dict[str, IconResult] = {}
        self._inflight: dict[str, Future[IconResult]] = {}
        self._lock = threading.RLock()

    def request(
        self, icon_kind: str, icon_url: str | None = None,
    ) -> Future[IconResult]:
        if icon_kind == "divination_card":
            return _completed_future(IconResult(
                divination_card_icon_path(), "bundled", "png",
            ))
        if icon_kind != "remote" or not self._valid_remote_url(icon_url):
            return _completed_future(self._placeholder())

        key = hashlib.sha256(icon_url.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self._memory.get(key)
            if cached is not None:
                return _completed_future(IconResult(
                    cached.path, "memory", cached.image_format,
                ))
            disk = self._disk_result(key)
            if disk is not None:
                self._memory[key] = disk
                return _completed_future(disk)
            inflight = self._inflight.get(key)
            if inflight is not None:
                if not inflight.done():
                    return inflight
                self._inflight.pop(key, None)
            future = self._executor.submit(self._fetch_and_store, key, icon_url)
            self._inflight[key] = future
            future.add_done_callback(
                lambda completed, cache_key=key: self._request_finished(
                    cache_key, completed,
                )
            )
            return future

    def close(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _fetch_and_store(self, key: str, url: str) -> IconResult:
        try:
            data = self._fetcher(url)
            image_format = inspect_image(data)
            if image_format is None:
                return self._placeholder()
            path = self.cache_root / f"{key}.img"
            self._atomic_write(path, data)
            result = IconResult(path, "network", image_format)
            with self._lock:
                self._memory[key] = result
            return result
        except Exception:  # noqa: BLE001 - network worker returns a placeholder
            return self._placeholder()

    def _request_finished(
        self, key: str, future: Future[IconResult],
    ) -> None:
        try:
            future.result()
        except Exception:  # noqa: BLE001, S110 - executor boundary is contained
            pass
        with self._lock:
            if self._inflight.get(key) is future:
                self._inflight.pop(key, None)

    def _disk_result(self, key: str) -> IconResult | None:
        path = self.cache_root / f"{key}.img"
        if not path.is_file():
            return None
        try:
            data = path.read_bytes()
        except OSError:
            return None
        image_format = inspect_image(data)
        return IconResult(path, "disk", image_format) if image_format else None

    @staticmethod
    def _valid_remote_url(icon_url: str | None) -> bool:
        if not isinstance(icon_url, str):
            return False
        parsed = urlparse(icon_url)
        return (
            parsed.scheme == "https"
            and (parsed.hostname or "").casefold() in ALLOWED_ICON_HOSTS
        )

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, delete=False,
            ) as temporary:
                temporary.write(data)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _placeholder() -> IconResult:
        return IconResult(placeholder_icon_path(), "placeholder", "svg")
