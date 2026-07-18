import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from src.update.artifacts import (
    DownloadCancelled,
    MAX_ARCHIVE_ENTRIES,
    MAX_COMPRESSION_RATIO,
    MAX_SINGLE_FILE_SIZE,
    MAX_TOTAL_UNCOMPRESSED_SIZE,
    download_file,
    parse_checksum,
    validate_update_archive,
    verify_sha256,
)


def write_zip(path: Path, names: list[str]):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"content")


def test_default_archive_limits_match_release_policy():
    assert MAX_ARCHIVE_ENTRIES == 5_000
    assert MAX_TOTAL_UNCOMPRESSED_SIZE == 512 * 1024 * 1024
    assert MAX_SINGLE_FILE_SIZE == 128 * 1024 * 1024
    assert MAX_COMPRESSION_RATIO == 100


def test_parse_checksum_and_verify_file(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    archive.write_bytes(b"release")
    digest = hashlib.sha256(b"release").hexdigest()
    assert parse_checksum(f"{digest}  PoENavi.zip\n") == digest
    assert verify_sha256(archive, digest)


@pytest.mark.parametrize(
    "text",
    ["bad PoENavi.zip", "a" * 64 + "  Other.zip", ""],
)
def test_parse_checksum_rejects_invalid_content(text):
    with pytest.raises(ValueError):
        parse_checksum(text)


def test_validate_update_archive_accepts_release_layout(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi/PoENavi.exe",
            "PoENavi/PoENaviUpdater.exe",
        ],
    )
    validate_update_archive(archive)


def test_validate_update_archive_accepts_build_script_root_layout(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi.exe",
            "PoENaviUpdater.exe",
            "_internal/guide_data.json",
        ],
    )
    validate_update_archive(archive)


def test_validate_update_archive_rejects_ambiguous_mixed_layout(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi.exe",
            "PoENaviUpdater.exe",
            "PoENavi/PoENavi.exe",
            "PoENavi/PoENaviUpdater.exe",
        ],
    )
    with pytest.raises(ValueError, match="配置が不正"):
        validate_update_archive(archive)


def test_validate_update_archive_rejects_too_many_entries(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi/PoENavi.exe",
            "PoENavi/PoENaviUpdater.exe",
            "PoENavi/extra.txt",
        ],
    )

    with pytest.raises(ValueError, match="ファイル数"):
        validate_update_archive(archive, max_entries=2)


def test_validate_update_archive_rejects_single_oversized_file(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi/PoENavi.exe",
            "PoENavi/PoENaviUpdater.exe",
        ],
    )

    with pytest.raises(ValueError, match="ファイルがサイズ上限"):
        validate_update_archive(archive, max_single_file_size=6)


def test_validate_update_archive_rejects_oversized_total(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi/PoENavi.exe",
            "PoENavi/PoENaviUpdater.exe",
        ],
    )

    with pytest.raises(ValueError, match="展開後サイズ"):
        validate_update_archive(archive, max_total_size=10)


def test_validate_update_archive_rejects_extreme_compression_ratio(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("PoENavi/PoENavi.exe", b"A" * 10_000)
        bundle.writestr("PoENavi/PoENaviUpdater.exe", b"updater")

    with pytest.raises(ValueError, match="異常な圧縮率"):
        validate_update_archive(
            archive,
            min_ratio_check_size=1,
            max_compression_ratio=10,
        )


@pytest.mark.parametrize(
    "entry",
    ["../outside", "PoENavi/../../outside", "/absolute", "C:/absolute"],
)
def test_validate_update_archive_rejects_path_escape(tmp_path, entry):
    archive = tmp_path / "PoENavi.zip"
    write_zip(
        archive,
        [
            "PoENavi/PoENavi.exe",
            "PoENavi/PoENaviUpdater.exe",
            entry,
        ],
    )
    with pytest.raises(ValueError):
        validate_update_archive(archive)


class Response(io.BytesIO):
    def __init__(self, data: bytes, final_url="https://github.com/file"):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self._final_url = final_url

    def geturl(self):
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_download_reports_progress_and_honors_cancel(tmp_path):
    progress = []
    target = download_file(
        "https://github.com/file",
        tmp_path / "file",
        lambda done, total: progress.append((done, total)),
        lambda: False,
        opener=lambda _request, timeout: Response(b"release"),
    )
    assert target.read_bytes() == b"release"
    assert progress[-1] == (7, 7)

    with pytest.raises(DownloadCancelled):
        download_file(
            "https://github.com/file",
            tmp_path / "cancelled",
            lambda _done, _total: None,
            lambda: True,
            opener=lambda _request, timeout: Response(b"release"),
        )
    assert not (tmp_path / "cancelled").exists()


def test_download_rejects_redirect_outside_github(tmp_path):
    with pytest.raises(ValueError, match="GitHub"):
        download_file(
            "https://github.com/file",
            tmp_path / "file",
            lambda _done, _total: None,
            lambda: False,
            opener=lambda _request, timeout: Response(
                b"release",
                final_url="https://example.com/file",
            ),
        )
