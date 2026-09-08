param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$testFiles = @(
    "tests/test_cheat_sheets.py",
    "tests/test_config_manager.py",
    "tests/test_build_expedition_ocr_items.py",
    "tests/test_expedition_ocr_probe.py",
    "tests/test_expedition_rewards.py",
    "tests/test_feature_support.py",
    "tests/test_poetore_audit_docs.py",
    "tests/test_poetore_awakened_audit_csv.py",
    "tests/test_poetore_categories.py",
    "tests/test_poetore_chart.py",
    "tests/test_poetore_clipboard.py",
    "tests/test_poetore_corrupted_implicits.py",
    "tests/test_poetore_cross_validation.py",
    "tests/test_poetore_distribution.py",
    "tests/test_poetore_hotkey_config.py",
    "tests/test_poetore_lazy_launch.py",
    "tests/test_poetore_merge.py",
    "tests/test_poetore_metadata.py",
    "tests/test_poetore_mode_window.py",
    "tests/test_poetore_parser.py",
    "tests/test_poetore_parser_sample_collection.py",
    "tests/test_poetore_performance.py",
    "tests/test_poetore_poe2_audit.py",
    "tests/test_poetore_poe2_local_global_audit.py",
    "tests/test_poetore_poe2_parser.py",
    "tests/test_poetore_poe2_trade.py",
    "tests/test_poetore_settings_dialog.py",
    "tests/test_poetore_trade.py",
    "tests/test_poetore_ui.py",
    "tests/test_poetore_window_position.py",
    "tests/test_build_poetore_poe2_indexes.py",
    "tests/test_app_composition.py",
    "tests/test_release_client.py",
    "tests/test_security_scan.py",
    "tests/test_startup_selection_flow.py",
    "tests/test_startup_update_gate.py",
    "tests/test_update_artifacts.py",
    "tests/test_update_gui_flow.py",
    "tests/test_update_qt_controller.py",
    "tests/test_updater_engine.py",
    "tests/test_windows_version_info.py"
)
$failedFiles = @()

foreach ($testFile in $testFiles) {
    Write-Host "::group::$testFile"
    & $Python -m pytest -q $testFile
    $testExitCode = $LASTEXITCODE
    Write-Host "::endgroup::"

    if ($testExitCode -ne 0) {
        $failedFiles += $testFile
        Write-Host "$testFile failed with exit code $testExitCode"
    }
}

if ($failedFiles.Count -gt 0) {
    throw "Failing scoped test files: $($failedFiles -join ', ')"
}
