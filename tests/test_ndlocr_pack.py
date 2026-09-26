import hashlib
import json
import shutil
import zipfile

import pytest

from src.poetore.poe2.ndlocr_pack import (
    PACK_ARCHIVE_ROOT,
    PACK_ASSET_NAME,
    PACK_RELEASE_ARCHIVE_SHA256,
    PACK_RELEASE_TAG,
    PACK_VERSION,
    REQUIRED_MODELS,
    PackStatus,
    download_and_install_pack,
    install_pack_archive,
    installed_helper_path,
    pack_asset_urls,
    pack_is_installed,
)


def make_pack(path, *, unsafe_name=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        prefix = PACK_ARCHIVE_ROOT
        archive.writestr(
            unsafe_name or f"{prefix}/PoENaviNdlOcr/PoENaviNdlOcr.exe",
            b"exe",
        )
        for name in REQUIRED_MODELS:
            archive.writestr(
                f"{prefix}/PoENaviNdlOcr/_internal/model/{name}", b"model"
            )
        archive.writestr(
            f"{prefix}/THIRD_PARTY_LICENSES/NDLOCR-Lite-{PACK_VERSION}/LICENCE.txt",
            "license",
        )
        archive.writestr(
            f"{prefix}/THIRD_PARTY_LICENSES/NDLOCR-Lite-{PACK_VERSION}/LICENCE_DEPENDENCIES.txt",
            "dependencies",
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pack_asset_urls_are_pinned_to_immutable_pack_release():
    archive, checksum = pack_asset_urls()
    assert archive.endswith(f"/{PACK_RELEASE_TAG}/{PACK_ASSET_NAME}")
    assert checksum.endswith(f"/{PACK_RELEASE_TAG}/{PACK_ASSET_NAME}.sha256")
    assert "/v4.4.1/" not in archive
    assert "/v4.4.2/" not in archive


def test_pack_install_is_atomic_and_reusable(tmp_path, monkeypatch):
    parent = tmp_path / "packs"
    monkeypatch.setenv("POENAVI_NDLOCR_PACK_DIR", str(parent))
    archive = tmp_path / PACK_ASSET_NAME
    digest = make_pack(archive)

    installed = install_pack_archive(archive, digest)

    assert installed == parent / f"ndlocr-{PACK_VERSION}"
    assert pack_is_installed()
    assert installed_helper_path() == (
        installed / "PoENaviNdlOcr" / "PoENaviNdlOcr.exe"
    )
    marker = json.loads((installed / ".installed.json").read_text(encoding="utf-8"))
    assert marker == {
        "pack_version": PACK_VERSION,
        "pack_release_tag": PACK_RELEASE_TAG,
        "archive_sha256": digest,
    }


def test_existing_v441_pack_is_reused_only_when_legacy_sha_matches(
    tmp_path, monkeypatch
):
    parent = tmp_path / "packs"
    monkeypatch.setenv("POENAVI_NDLOCR_PACK_DIR", str(parent))
    installed = parent / f"ndlocr-{PACK_VERSION}"
    helper = installed / "PoENaviNdlOcr" / "PoENaviNdlOcr.exe"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"exe")
    model_dir = installed / "PoENaviNdlOcr" / "_internal" / "model"
    model_dir.mkdir(parents=True)
    for name in REQUIRED_MODELS:
        (model_dir / name).write_bytes(b"model")
    marker = installed / ".installed.json"
    marker.write_text(
        json.dumps(
            {
                "pack_version": PACK_VERSION,
                "archive_sha256": PACK_RELEASE_ARCHIVE_SHA256,
            }
        ),
        encoding="utf-8",
    )

    assert installed_helper_path() == helper

    marker.write_text(
        json.dumps({"pack_version": PACK_VERSION, "archive_sha256": "0" * 64}),
        encoding="utf-8",
    )
    assert installed_helper_path() is None


def test_installed_pack_with_different_release_revision_is_rejected(
    tmp_path, monkeypatch
):
    parent = tmp_path / "packs"
    monkeypatch.setenv("POENAVI_NDLOCR_PACK_DIR", str(parent))
    installed = parent / f"ndlocr-{PACK_VERSION}"
    helper = installed / "PoENaviNdlOcr" / "PoENaviNdlOcr.exe"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"exe")
    model_dir = installed / "PoENaviNdlOcr" / "_internal" / "model"
    model_dir.mkdir(parents=True)
    for name in REQUIRED_MODELS:
        (model_dir / name).write_bytes(b"model")
    (installed / ".installed.json").write_text(
        json.dumps(
            {
                "pack_version": PACK_VERSION,
                "pack_release_tag": "ndlocr-pack-v1.3.1-r2",
                "archive_sha256": PACK_RELEASE_ARCHIVE_SHA256,
            }
        ),
        encoding="utf-8",
    )

    assert installed_helper_path() is None


def test_pack_install_rejects_hash_mismatch_without_replacing_existing(tmp_path):
    destination = tmp_path / "installed"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("old", encoding="utf-8")
    archive = tmp_path / PACK_ASSET_NAME
    make_pack(archive)

    with pytest.raises(ValueError, match="SHA-256"):
        install_pack_archive(archive, "0" * 64, destination=destination)

    assert sentinel.read_text(encoding="utf-8") == "old"


def test_pack_install_rejects_path_traversal(tmp_path):
    archive = tmp_path / PACK_ASSET_NAME
    digest = make_pack(archive, unsafe_name="../PoENaviNdlOcr.exe")

    with pytest.raises(ValueError, match="危険なパス"):
        install_pack_archive(archive, digest, destination=tmp_path / "installed")


def test_download_checks_checksum_and_installs_into_user_data(tmp_path, monkeypatch):
    parent = tmp_path / "packs"
    monkeypatch.setenv("POENAVI_NDLOCR_PACK_DIR", str(parent))
    stale = parent / "ndlocr-download-interrupted"
    stale.mkdir(parents=True)
    (stale / "partial.zip").write_bytes(b"partial")
    source = tmp_path / "source.zip"
    digest = make_pack(source)
    phases = []
    downloads = []

    def downloader(url, destination, progress, cancelled):
        assert not cancelled()
        downloads.append(url)
        if url.endswith(".sha256"):
            destination.write_text(
                f"{digest}  {PACK_ASSET_NAME}\n", encoding="utf-8"
            )
        else:
            shutil.copy2(source, destination)
            progress(source.stat().st_size, source.stat().st_size)
        return destination

    installed = download_and_install_pack(phase=phases.append, downloader=downloader)

    assert installed == parent / f"ndlocr-{PACK_VERSION}"
    assert phases == ["checking", "downloading", "installing"]
    assert downloads[0].endswith(f"/{PACK_RELEASE_TAG}/{PACK_ASSET_NAME}.sha256")
    assert downloads[1].endswith(f"/{PACK_RELEASE_TAG}/{PACK_ASSET_NAME}")
    assert pack_is_installed()
    assert not stale.exists()


def test_pack_status_is_plain_immutable_state():
    assert PackStatus("downloading", done=1, total=4).state == "downloading"
