param(
    [string]$InputDirectory = "",
    [string]$Manifest = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$windowsRunner = Join-Path $PSScriptRoot "run_desecration_windows_ocr.ps1"
$fusionScript = Join-Path $PSScriptRoot "desecration_ocr_fusion_report.py"
$defaultInput = Join-Path $repoRoot "tests\fixtures\poetore\poe2\desecration"
if (-not $InputDirectory) { $InputDirectory = $defaultInput }
if (-not $Manifest) { $Manifest = Join-Path $defaultInput "reported-cases.json" }

$version = "1.3.1"
$archiveSha256 = "E510D3A7B878395EA9DE0BDD365711B699E5FD430B5C7E23A40E918E913FD1F2"
$archiveUrl = "https://github.com/ndl-lab/ndlocr-lite/archive/refs/tags/$version.zip"
$cacheRoot = Join-Path $env:LOCALAPPDATA "PoENavi\NdlocrLiteSpike\$version"
$archivePath = Join-Path $cacheRoot "ndlocr-lite-$version.zip"
$sourceRoot = Join-Path $cacheRoot "ndlocr-lite-$version"
$venvRoot = Join-Path $cacheRoot "venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$readyMarker = Join-Path $venvRoot ".ndlocr-lite-$version-ready"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $env:LOCALAPPDATA "PoENavi\DesecrationOcrFusionProbe\$timestamp"
$windowsOutput = Join-Path $runRoot "windows"
$ndlInput = Join-Path $runRoot "ndl-input"
$ndlRaw = Join-Path $runRoot "ndl-raw"
$plan = Join-Path $runRoot "ndl-plan.json"
if (-not $Output) { $Output = Join-Path $runRoot "report" }

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.10 or newer was not found."
}
$pythonVersionOk = python -c "import sys; print('yes' if sys.version_info >= (3, 10) else 'no')"
if ($LASTEXITCODE -ne 0 -or $pythonVersionOk.Trim() -ne "yes") {
    throw "Python 3.10 or newer is required."
}
python -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Python package PySide6 is required." }
if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
    throw "Input directory was not found: $InputDirectory"
}
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
    throw "Manifest was not found: $Manifest"
}

New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
Write-Host "Step 1/4: Running the existing Windows OCR probe..."
& $windowsRunner -InputDirectory $InputDirectory -Manifest $Manifest `
    -Output $windowsOutput -NoOpen -AllowMismatches
$windowsSummary = Join-Path $windowsOutput "summary.json"
if (-not (Test-Path -LiteralPath $windowsSummary -PathType Leaf)) {
    throw "Windows OCR summary was not created: $windowsSummary"
}

Write-Host "Step 2/4: Selecting only stable Windows OCR numeric gaps..."
New-Item -ItemType Directory -Path $ndlInput -Force | Out-Null
python $fusionScript prepare --windows-summary $windowsSummary `
    --input-dir $InputDirectory --ndl-input $ndlInput --plan $plan
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare NDLOCR-Lite inputs." }
$planData = Get-Content -LiteralPath $plan -Raw | ConvertFrom-Json

New-Item -ItemType Directory -Path $ndlRaw -Force | Out-Null
if ($planData.candidate_count -gt 0) {
    Write-Host "Step 3/4: Running NDLOCR-Lite only for numeric-gap choices..."
    New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
        Write-Host "Downloading NDLOCR-Lite $version source archive..."
        Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath
    }
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($actualHash -ne $archiveSha256) {
        throw "NDLOCR-Lite archive SHA-256 mismatch. Expected $archiveSha256 but got $actualHash"
    }
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        Write-Host "Extracting NDLOCR-Lite..."
        Expand-Archive -LiteralPath $archivePath -DestinationPath $cacheRoot
    }
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Host "Creating isolated Python environment..."
        python -m venv $venvRoot
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python environment." }
    }
    if (-not (Test-Path -LiteralPath $readyMarker -PathType Leaf)) {
        Write-Host "Installing pinned NDLOCR-Lite dependencies. This is only needed once..."
        & $venvPython -m pip install --disable-pip-version-check `
            -r (Join-Path $sourceRoot "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Failed to install NDLOCR-Lite dependencies." }
        New-Item -ItemType File -Path $readyMarker -Force | Out-Null
    }
    & $venvPython (Join-Path $sourceRoot "src\ocr.py") `
        --sourcedir $ndlInput --output $ndlRaw --json-only
    if ($LASTEXITCODE -ne 0) { throw "NDLOCR-Lite inference failed." }
} else {
    Write-Host "Step 3/4: No eligible numeric gaps; NDLOCR-Lite was not run."
}

Write-Host "Step 4/4: Building the combined decision report..."
python $fusionScript report --windows-summary $windowsSummary `
    --ndl-raw $ndlRaw --plan $plan --manifest $Manifest --output $Output
$reportExitCode = $LASTEXITCODE
$report = Join-Path $Output "report.html"
if (Test-Path -LiteralPath $report -PathType Leaf) {
    Start-Process $report
    Write-Host "Combined OCR report: $report"
}
if ($reportExitCode -ne 0) {
    throw "One or more combined OCR results did not match the expected values."
}
