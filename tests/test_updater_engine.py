from pathlib import Path
import zipfile

import pytest
import src.update.updater_engine as updater_engine

from src.update.updater_engine import (
    UpdateApplyError,
    apply_update,
    retry_transient_file_operation,
    wait_for_process_exit,
)


def make_release(path: Path, marker="new", guide="new guide"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("PoENavi/PoENavi.exe", marker)
        archive.writestr("PoENavi/PoENaviUpdater.exe", "updater")
        archive.writestr("PoENavi/guide_data.json", guide)


def make_root_release(path: Path, marker="new"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("PoENavi.exe", marker)
        archive.writestr("PoENaviUpdater.exe", "updater")


def make_install(path: Path, marker="old"):
    path.mkdir(parents=True)
    (path / "PoENavi.exe").write_text(marker, encoding="utf-8")
    (path / "PoENaviUpdater.exe").write_text("updater", encoding="utf-8")


def test_wait_for_process_exit_stops_when_process_finishes():
    states = iter([True, True, False])
    assert wait_for_process_exit(
        42,
        1,
        lambda _pid: next(states),
        sleep=lambda _seconds: None,
    )


def test_retry_transient_file_operation_recovers_from_temporary_lock():
    calls = []

    def operation():
        calls.append("called")
        if len(calls) < 3:
            raise PermissionError("temporarily locked")
        return "done"

    sleeps = []
    assert retry_transient_file_operation(
        operation,
        attempts=3,
        delay=0.25,
        sleep=sleeps.append,
    ) == "done"
    assert len(calls) == 3
    assert sleeps == [0.25, 0.25]


def test_retry_transient_file_operation_raises_after_limit():
    def operation():
        raise PermissionError("still locked")

    with pytest.raises(PermissionError, match="still locked"):
        retry_transient_file_operation(
            operation,
            attempts=2,
            delay=0,
            sleep=lambda _seconds: None,
        )


def test_apply_update_replaces_install_and_launches_new_exe(tmp_path):
    install = tmp_path / "ぽえなび" / "PoENavi"
    make_install(install)
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


def test_apply_update_accepts_build_script_root_layout(tmp_path):
    install = tmp_path / "PoENavi"
    make_install(install)
    archive = tmp_path / "PoENavi.zip"
    make_root_release(archive)

    apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "new"


def test_apply_update_replaces_old_official_guide_with_release_guide(tmp_path):
    install = tmp_path / "PoENavi"
    make_install(install)
    (install / "guide_data.json").write_text("user-edited old guide", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive, guide="latest official guide")

    apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert (install / "guide_data.json").read_text(encoding="utf-8") == "latest official guide"


def test_apply_update_does_not_touch_external_user_data(tmp_path):
    install = tmp_path / "PoENavi"
    make_install(install)
    user_data = tmp_path / "AppData" / "PoENavi"
    user_data.mkdir(parents=True)
    area_notes = user_data / "area_notes_poe1.json"
    config = user_data / "config.json"
    area_notes.write_text('{"area": {"text": "my note"}}', encoding="utf-8")
    config.write_text('{"font_size": 18}', encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert area_notes.read_text(encoding="utf-8") == '{"area": {"text": "my note"}}'
    assert config.read_text(encoding="utf-8") == '{"font_size": 18}'


def test_apply_update_restores_old_install_when_launch_fails(tmp_path):
    install = tmp_path / "PoENavi"
    make_install(install)
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    def fail_launch(_exe):
        raise OSError("launch failed")

    with pytest.raises(UpdateApplyError, match="旧版を復元"):
        apply_update(archive, install, tmp_path / "work", fail_launch)
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"


def test_apply_update_leaves_install_untouched_when_initial_rename_is_denied(
    tmp_path, monkeypatch
):
    install = tmp_path / "PoENavi"
    make_install(install)
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)
    original_rename = Path.rename

    def deny_install_rename(path, target):
        if path == install:
            raise PermissionError("temporarily locked")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", deny_install_rename)
    monkeypatch.setattr(
        updater_engine,
        "retry_transient_file_operation",
        lambda operation: operation(),
    )

    with pytest.raises(UpdateApplyError, match="temporarily locked"):
        apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"
    assert not install.with_name("PoENavi.failed").exists()


def test_apply_update_restores_old_install_when_new_app_exits_immediately(tmp_path):
    install = tmp_path / "PoENavi"
    make_install(install)
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


def test_apply_update_archives_valid_stale_backup_and_removes_it_after_success(tmp_path):
    install = tmp_path / "PoENavi"
    backup = tmp_path / "PoENavi.backup"
    make_install(install, "current")
    make_install(backup, "stale")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    current_backup = apply_update(
        archive,
        install,
        tmp_path / "work",
        lambda _exe: object(),
        timestamp=lambda: "20260804-122500",
    )

    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "new"
    assert (current_backup / "PoENavi.exe").read_text(encoding="utf-8") == "current"
    assert not (tmp_path / "PoENavi.backup-old-20260804-122500").exists()


def test_apply_update_restores_stale_backup_name_when_update_fails(tmp_path):
    install = tmp_path / "PoENavi"
    backup = tmp_path / "PoENavi.backup"
    make_install(install, "current")
    make_install(backup, "stale")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    with pytest.raises(UpdateApplyError, match="旧版を復元"):
        apply_update(
            archive,
            install,
            tmp_path / "work",
            lambda _exe: object(),
            startup_check=lambda _process: False,
            timestamp=lambda: "20260804-122500",
        )

    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "current"
    assert (backup / "PoENavi.exe").read_text(encoding="utf-8") == "stale"
    assert not (tmp_path / "PoENavi.backup-old-20260804-122500").exists()


def test_apply_update_rejects_unrecognizable_stale_backup(tmp_path):
    install = tmp_path / "PoENavi"
    backup = tmp_path / "PoENavi.backup"
    make_install(install)
    backup.mkdir()
    (backup / "unknown.txt").write_text("keep me", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    with pytest.raises(UpdateApplyError, match="安全に確認できません"):
        apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert (backup / "unknown.txt").read_text(encoding="utf-8") == "keep me"
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"


def test_apply_update_reports_when_stale_backup_cannot_be_archived(
    tmp_path, monkeypatch
):
    install = tmp_path / "PoENavi"
    backup = tmp_path / "PoENavi.backup"
    make_install(install)
    make_install(backup, "stale")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)
    original_rename = Path.rename

    def deny_backup_rename(path, target):
        if path == backup:
            raise PermissionError("locked by sync")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", deny_backup_rename)
    monkeypatch.setattr(
        updater_engine,
        "retry_transient_file_operation",
        lambda operation: operation(),
    )

    with pytest.raises(UpdateApplyError, match="安全に退避できませんでした"):
        apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert (backup / "PoENavi.exe").read_text(encoding="utf-8") == "stale"
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"


def test_apply_update_stops_when_failed_update_directory_exists(tmp_path):
    install = tmp_path / "PoENavi"
    failed = tmp_path / "PoENavi.failed"
    make_install(install)
    make_install(failed, "failed")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)

    with pytest.raises(UpdateApplyError, match="自動整理せず停止"):
        apply_update(archive, install, tmp_path / "work", lambda _exe: object())

    assert (failed / "PoENavi.exe").read_text(encoding="utf-8") == "failed"


def test_stale_backup_archive_name_avoids_collision(tmp_path):
    backup = tmp_path / "PoENavi.backup"
    first = tmp_path / "PoENavi.backup-old-20260804-122500"
    second = tmp_path / "PoENavi.backup-old-20260804-122500-2"
    first.mkdir()
    second.mkdir()

    assert updater_engine._next_stale_backup_path(
        backup, "20260804-122500"
    ) == tmp_path / "PoENavi.backup-old-20260804-122500-3"
