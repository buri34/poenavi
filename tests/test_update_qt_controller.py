import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication

from src.update.qt_controller import UpdateController
from src.update.release_client import ReleaseInfo


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    return QCoreApplication.instance() or QCoreApplication([])


class ImmediateThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


def test_check_emits_release_and_manual_flag(monkeypatch):
    release = ReleaseInfo(
        "2.5.0",
        "notes",
        "https://github.com/page",
        "https://github.com/a.zip",
        "https://github.com/a.sha256",
    )
    controller = UpdateController(thread_factory=ImmediateThread)
    received = []
    controller.check_finished.connect(
        lambda value, manual: received.append((value, manual))
    )
    monkeypatch.setattr(
        "src.update.qt_controller.fetch_latest_release",
        lambda _version: release,
    )

    controller.check(True)

    assert received == [(release, True)]


def test_launch_updater_copies_executable_archive_and_uses_argument_list(
    tmp_path,
    monkeypatch,
):
    install = tmp_path / "ぽえなび" / "PoENavi"
    install.mkdir(parents=True)
    (install / "PoENavi.exe").write_text("app", encoding="utf-8")
    (install / "PoENaviUpdater.exe").write_text("updater", encoding="utf-8")
    download_dir = tmp_path / "download"
    download_dir.mkdir()
    archive = download_dir / "PoENavi.zip"
    archive.write_bytes(b"zip")
    updater_work = tmp_path / "updater-work"
    launched = []
    controller = UpdateController()
    controller._work_dir = download_dir
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(install / "PoENavi.exe"))
    monkeypatch.setattr(
        "src.update.qt_controller.tempfile.mkdtemp",
        lambda prefix: str(updater_work),
    )
    monkeypatch.setattr(
        "src.update.qt_controller.subprocess.Popen",
        lambda args, cwd: launched.append((args, cwd)),
    )

    controller.launch_updater(archive)

    args, cwd = launched[0]
    assert args[0] == str(updater_work / "PoENaviUpdater.exe")
    assert args[args.index("--install-dir") + 1] == str(install)
    staged_archive = Path(args[args.index("--archive") + 1])
    assert staged_archive == updater_work / "PoENavi.zip"
    assert staged_archive.read_bytes() == b"zip"
    assert cwd == str(updater_work)
    assert args[args.index("--language") + 1] == "ja"
    assert not download_dir.exists()


def test_cleanup_stale_update_directories(tmp_path, monkeypatch):
    stale = tmp_path / "PoENavi-Updater-old"
    stale.mkdir()
    (stale / "PoENaviUpdater.exe").write_text("old", encoding="utf-8")
    unrelated = tmp_path / "other-app"
    unrelated.mkdir()
    monkeypatch.setattr(
        "src.update.qt_controller.tempfile.gettempdir",
        lambda: str(tmp_path),
    )

    UpdateController._cleanup_stale_update_dirs()

    assert not stale.exists()
    assert unrelated.exists()


def test_download_reuses_verified_archive(tmp_path):
    release = ReleaseInfo(
        "2.5.0",
        "notes",
        "https://github.com/page",
        "https://github.com/a.zip",
        "https://github.com/a.sha256",
    )
    work_dir = tmp_path / "download"
    work_dir.mkdir()
    archive = work_dir / "PoENavi.zip"
    archive.write_bytes(b"verified")
    controller = UpdateController(thread_factory=ImmediateThread)
    controller._work_dir = work_dir
    controller._ready_archive = archive
    controller._ready_version = release.version
    received = []
    controller.download_ready.connect(
        lambda ready_archive, ready_release: received.append(
            (ready_archive, ready_release)
        )
    )

    controller.download(release)

    assert received == [(archive, release)]
    assert archive.is_file()


def test_ready_archive_discards_different_version(tmp_path):
    work_dir = tmp_path / "download"
    work_dir.mkdir()
    archive = work_dir / "PoENavi.zip"
    archive.write_bytes(b"old")
    controller = UpdateController()
    controller._work_dir = work_dir
    controller._ready_archive = archive
    controller._ready_version = "2.5.0"

    assert controller.ready_archive("2.6.0") is None
    assert not work_dir.exists()
