param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$testFiles = @(Get-ChildItem tests/test_*.py | Sort-Object Name | ForEach-Object { $_.FullName })
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
    throw "Failing test files: $($failedFiles -join ', ')"
}
