import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Callable
import urllib.request
import zipfile


CHECKSUM_PATTERN = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+)$")
GITHUB_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}

# v2.4.0 配布物（529エントリー、展開後約219MiB、最大ファイル約19.7MiB、
# 最大圧縮率約4.8倍）を基準に、将来の増加へ十分な余裕を持たせつつ、
# 更新ZIPによるディスク枯渇を防ぐための上限を設ける。
MAX_ARCHIVE_ENTRIES = 5_000
MAX_TOTAL_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
MAX_SINGLE_FILE_SIZE = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MIN_RATIO_CHECK_SIZE = 1024 * 1024


class DownloadCancelled(Exception):
    pass


def _validate_url(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in GITHUB_HOSTS:
        raise ValueError("GitHub 管理外のダウンロード URL です")


class _GitHubRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _request(url: str) -> urllib.request.Request:
    _validate_url(url)
    return urllib.request.Request(url, headers={"User-Agent": "PoENavi-Updater"})


def _open(request: urllib.request.Request, timeout: int):
    return urllib.request.build_opener(_GitHubRedirectHandler()).open(
        request,
        timeout=timeout,
    )


def download_file(
    url: str,
    destination: Path,
    progress: Callable[[int, int], None],
    cancelled: Callable[[], bool],
    opener=None,
) -> Path:
    opener = opener or _open
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with opener(_request(url), timeout=30) as response, destination.open("wb") as output:
            final_url = getattr(response, "geturl", lambda: url)()
            _validate_url(final_url)
            total = int(response.headers.get("Content-Length", "0"))
            done = 0
            while True:
                if cancelled():
                    raise DownloadCancelled()
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                progress(done, total)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def parse_checksum(text: str, filename: str = "PoENavi.zip") -> str:
    match = CHECKSUM_PATTERN.fullmatch(text.strip())
    if not match or Path(match.group(2)).name != filename:
        raise ValueError("チェックサムファイルの形式が不正です")
    return match.group(1).lower()


def verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected.lower()


def validate_update_archive(
    path: Path,
    *,
    max_entries: int = MAX_ARCHIVE_ENTRIES,
    max_total_size: int = MAX_TOTAL_UNCOMPRESSED_SIZE,
    max_single_file_size: int = MAX_SINGLE_FILE_SIZE,
    max_compression_ratio: float = MAX_COMPRESSION_RATIO,
    min_ratio_check_size: int = MIN_RATIO_CHECK_SIZE,
) -> None:
    wrapped_required = {
        "PoENavi/PoENavi.exe",
        "PoENavi/PoENaviUpdater.exe",
    }
    root_required = {
        "PoENavi.exe",
        "PoENaviUpdater.exe",
    }
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > max_entries:
            raise ValueError(
                f"更新 ZIP のファイル数が上限を超えています: {len(entries)}"
            )

        names = set()
        total_size = 0
        for info in entries:
            name = info.filename.replace("\\", "/")
            pure_path = PurePosixPath(name)
            parts = pure_path.parts
            if (
                not parts
                or ".." in parts
                or pure_path.is_absolute()
                or re.match(r"^[A-Za-z]:", name)
            ):
                raise ValueError(f"危険な ZIP エントリーです: {name}")
            unix_mode = info.external_attr >> 16
            if unix_mode and (unix_mode & 0o170000) == 0o120000:
                raise ValueError(f"リンクを含む ZIP は使用できません: {name}")

            if info.file_size > max_single_file_size:
                raise ValueError(
                    f"更新 ZIP 内のファイルがサイズ上限を超えています: {name}"
                )
            total_size += info.file_size
            if total_size > max_total_size:
                raise ValueError("更新 ZIP の展開後サイズが上限を超えています")

            if info.file_size >= min_ratio_check_size:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > max_compression_ratio:
                    raise ValueError(
                        f"更新 ZIP に異常な圧縮率のファイルがあります: {name}"
                    )
            names.add(name.rstrip("/"))

    has_wrapped_layout = wrapped_required <= names
    has_root_layout = root_required <= names
    if has_wrapped_layout == has_root_layout:
        raise ValueError(
            "更新 ZIP の配置が不正です: PoENavi.exe と "
            "PoENaviUpdater.exe が同じ階層に必要です"
        )
