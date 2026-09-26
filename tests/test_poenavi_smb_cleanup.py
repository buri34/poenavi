from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cleanup_batch_calls_guarded_powershell_script_relative_to_snapshot():
    batch_path = ROOT / "CLEANUP_OLD_POENAVI_FOLDERS.cmd"
    raw_batch = batch_path.read_bytes()
    batch = raw_batch.decode("utf-8")

    assert b"\n" not in raw_batch.replace(b"\r\n", b"")
    assert "%~dp0" in batch
    assert "cleanup_old_poenavi_folders.ps1" in batch
    assert '-Root "%SCRIPT_DIR%.."' in batch
    assert '-ProtectPath "%SCRIPT_DIR%."' in batch
    assert '-ProtectPath "%SCRIPT_DIR%"' not in batch
    assert "pause" in batch


def test_cleanup_script_targets_only_known_generated_folder_names():
    script = (ROOT / "scripts" / "cleanup_old_poenavi_folders.ps1").read_text(
        encoding="utf-8"
    )

    assert "^poenavi-windows-[0-9a-f]{7,10}$" in script
    assert "^poenavi-windows-[0-9a-f]{7,10}-incomplete-" in script
    assert "^poenavi-build-output-[0-9a-f]{7,10}-" in script
    assert "Protected snapshot must be a direct child" in script
    assert "Refusing to use a drive root" in script
    assert "FileAttributes]::ReparsePoint" in script
    assert "Other PoENavi folders, including diagnostics and test images, are not targeted." in script
    assert "Remove-Item -LiteralPath $candidate.FullName" in script
    assert "Remove-Item $resolvedRoot" not in script


def test_cleanup_requires_explicit_confirmation_and_keeps_recent_generations():
    script = (ROOT / "scripts" / "cleanup_old_poenavi_folders.ps1").read_text(
        encoding="utf-8"
    )

    assert "[int]$KeepSnapshots = 3" in script
    assert "[int]$KeepBuildOutputs = 1" in script
    assert "$resolvedProtect -notin $keptSnapshotPaths" in script
    assert "[switch]$PreviewOnly" in script
    assert 'Read-Host "Type DELETE' in script
    assert '$confirmation -cne "DELETE"' in script
    assert "does not use the Recycle Bin" in script
