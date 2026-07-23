$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseDir = Join-Path $repoRoot "dist\PoENavi"
$archive = Join-Path $repoRoot "PoENavi.zip"
$testRoot = Join-Path $repoRoot "build\local-update-e2e"
$installDir = Join-Path $testRoot "install\PoENavi"
$userDataDir = Join-Path $testRoot "user-data"
$workDir = Join-Path $testRoot "updater-work"
$notesPath = Join-Path $userDataDir "area_notes_poe1.json"
$oldGuideMarker = "LOCAL_UPDATE_TEST_OLD_GUIDE"
$releaseGuidePath = Join-Path $releaseDir "_internal\guide_data.json"
$releasePoe2GuidePath = Join-Path $releaseDir "_internal\guide_data_poe2.json"
$releaseEnglishGuidePath = Join-Path $releaseDir "_internal\guide_data_en.json"
$releaseEnglishPoe2GuidePath = Join-Path $releaseDir "_internal\guide_data_poe2_en.json"
$releaseLocaleDir = Join-Path $releaseDir "_internal\data\i18n"

if (-not (Test-Path (Join-Path $releaseDir "PoENavi.exe"))) {
    throw "dist\PoENavi\PoENavi.exe was not found. Run build_exe.bat first."
}
if (-not (Test-Path (Join-Path $releaseDir "PoENaviUpdater.exe"))) {
    throw "dist\PoENavi\PoENaviUpdater.exe was not found. Run build_exe.bat first."
}
if (-not (Test-Path $archive)) {
    throw "PoENavi.zip was not found. Run build_exe.bat first."
}
if (-not (Test-Path $releaseGuidePath)) {
    throw "The release guide_data.json was not found under dist\PoENavi\_internal."
}
if (-not (Test-Path $releasePoe2GuidePath)) {
    throw "The release guide_data_poe2.json was not found under dist\PoENavi\_internal."
}
if (-not (Test-Path $releaseEnglishGuidePath)) {
    throw "The English guide_data_en.json was not found under dist\PoENavi\_internal."
}
if (-not (Test-Path $releaseEnglishPoe2GuidePath)) {
    throw "The English guide_data_poe2_en.json was not found under dist\PoENavi\_internal."
}
foreach ($catalog in @("ja.json", "en.json")) {
    if (-not (Test-Path (Join-Path $releaseLocaleDir $catalog))) {
        throw "The locale catalog $catalog was not found under dist\PoENavi\_internal\data\i18n."
    }
}

Remove-Item $testRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item (Split-Path $installDir) -ItemType Directory -Force | Out-Null
New-Item $userDataDir -ItemType Directory -Force | Out-Null
New-Item $workDir -ItemType Directory -Force | Out-Null
Copy-Item $releaseDir $installDir -Recurse

# Create an old-only guide marker and verify that the update replaces it.
$installedGuidePath = Join-Path $installDir "_internal\guide_data.json"
$expectedGuideHash = (Get-FileHash $releaseGuidePath -Algorithm SHA256).Hash
[IO.File]::WriteAllText(
    $installedGuidePath,
    $oldGuideMarker,
    [Text.UTF8Encoding]::new($false)
)

# Prepare isolated user data in the real area-note format.
$noteJson = @'
{
  "schema": 1,
  "notes": {
    "act1_area1": "LOCAL UPDATE TEST NOTE"
  }
}
'@
[IO.File]::WriteAllText($notesPath, $noteJson, [Text.UTF8Encoding]::new($false))
$notesHashBefore = (Get-FileHash $notesPath -Algorithm SHA256).Hash

$updater = Join-Path $workDir "PoENaviUpdater.exe"
$stagedArchive = Join-Path $workDir "PoENavi.zip"
Copy-Item (Join-Path $releaseDir "PoENaviUpdater.exe") $updater
Copy-Item $archive $stagedArchive

$previousUserDataDir = $env:POENAVI_USER_DATA_DIR
$env:POENAVI_USER_DATA_DIR = $userDataDir
try {
    $process = Start-Process -FilePath $updater -ArgumentList @(
        "--pid", "2147483647",
        "--archive", ('"' + $stagedArchive + '"'),
        "--install-dir", ('"' + $installDir + '"'),
        "--work-dir", ('"' + $workDir + '"')
    ) -WorkingDirectory $workDir -WindowStyle Hidden -PassThru

    $deadline = (Get-Date).AddSeconds(60)
    while (-not $process.HasExited) {
        if ((Get-Date) -gt $deadline) {
            throw "Updater did not exit within 60 seconds."
        }
        Start-Sleep -Seconds 1
        $process.Refresh()
    }
}
finally {
    if ($null -eq $previousUserDataDir) {
        Remove-Item Env:POENAVI_USER_DATA_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:POENAVI_USER_DATA_DIR = $previousUserDataDir
    }
}

if ($process.ExitCode -ne 0) {
    throw "Updater failed with exit code $($process.ExitCode)."
}
if (-not (Test-Path (Join-Path $installDir "PoENavi.exe"))) {
    throw "PoENavi.exe was not found after the update."
}
if (-not (Test-Path $installedGuidePath)) {
    throw "The official guide was not found after the update."
}
$actualGuideHash = (Get-FileHash $installedGuidePath -Algorithm SHA256).Hash
if ($actualGuideHash -ne $expectedGuideHash) {
    throw "The old official guide was not replaced with the release guide."
}
if (-not (Test-Path $notesPath)) {
    throw "The area-note file was lost during the update."
}
$notesHashAfter = (Get-FileHash $notesPath -Algorithm SHA256).Hash
if ($notesHashAfter -ne $notesHashBefore) {
    throw "The area-note file changed during the update."
}

Write-Host ""
Write-Host "LOCAL UPDATE TEST SUCCESS" -ForegroundColor Green
Write-Host "- Official guide: replaced"
Write-Host "- Area notes: preserved"
Write-Host "- Updated PoENavi: launched"
Write-Host "Test data: $testRoot"
