from pathlib import Path
import zipfile

import pytest

from src.update.updater_engine import (
    UpdateApplyError,
    apply_update,
    wait_for_process_exit,
)


def make_release(path: Path, marker="new"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("PoENavi/PoENavi.exe", marker)
        archive.writestr("PoENavi/PoENaviUpdater.exe", "updater")
        archive.writestr(
            "PoENavi/update-manifest.json",
            '{"schema": 1, "version": "2.5.0", "mutable_files": {}}',
        )


def test_wait_for_process_exit_stops_when_process_finishes():
    states = iter([True, True, False])
    assert wait_for_process_exit(
        42,
        1,
        lambda _pid: next(states),
        sleep=lambda _seconds: None,
    )


def test_apply_update_replaces_install_and_launches_new_exe(tmp_path):
    install = tmp_path / "ぽえなび" / "PoENavi"
    install.mkdir(parents=True)
    (install / "PoENavi.exe").write_text("old", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)
    launched = []

    backup = apply_update(
        archive,
        install,
        tmp_path / "work",
        lambda exe: launched.append(exe),
    )

    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "new"
    assert launched == [install / "PoENavi.exe"]
    assert backup.exists()


def test_apply_update_restores_old_install_when_launch_fails(tmp_path):
    install = tmp_path / "PoENavi"
    install.mkdir()
    (install / "PoENavi.exe").write_text("old", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    def fail_launch(_exe):
        raise OSError("launch failed")

    with pytest.raises(UpdateApplyError, match="旧版を復元"):
        apply_update(archive, install, tmp_path / "work", fail_launch)
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"


def test_apply_update_restores_old_install_when_new_app_exits_immediately(tmp_path):
    install = tmp_path / "PoENavi"
    install.mkdir()
    (install / "PoENavi.exe").write_text("old", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    with pytest.raises(UpdateApplyError, match="旧版を復元"):
        apply_update(
            archive,
            install,
            tmp_path / "work",
            lambda _exe: object(),
            startup_check=lambda _process: False,
        )
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"
