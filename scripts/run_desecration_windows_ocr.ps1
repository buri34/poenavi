param(
    [string]$InputDirectory = "",
    [string]$Manifest = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Split-Path -Parent $repoRoot
$projectSource = Join-Path $repoRoot "tools\ExpeditionWindowsOcr"
$probe = Join-Path $repoRoot "scripts\desecration_ocr_probe.py"
$prebuiltHelper = Join-Path $shareRoot "poenavi-short-ocr-diagnostic\helper\ExpeditionWindowsOcr.exe"
$prebuiltHelperSha256 = "35E60499170EE7DD9DAB8AED7D2B346C8D421ECF490EC1D4DBBD0E033E22AF8E"
$defaultInput = Join-Path $repoRoot "tests\fixtures\poetore\poe2\desecration"
if (-not $InputDirectory) { $InputDirectory = $defaultInput }
if (-not $Manifest -and $InputDirectory -eq $defaultInput) {
    $Manifest = Join-Path $defaultInput "reported-cases.json"
}
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$localRoot = Join-Path $env:LOCALAPPDATA "PoENavi\DesecrationOcrProbe\$timestamp"
$localProject = Join-Path $localRoot "ExpeditionWindowsOcr"
$helperOutput = Join-Path $localRoot "helper"
if (-not $Output) { $Output = Join-Path $localRoot "report" }

$missing = @()
$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$trustedPrebuilt = $false
if (Test-Path -LiteralPath $prebuiltHelper -PathType Leaf) {
    $actualHash = (Get-FileHash -LiteralPath $prebuiltHelper -Algorithm SHA256).Hash
    $trustedPrebuilt = $actualHash -eq $prebuiltHelperSha256
}
if (-not $trustedPrebuilt) {
    if (-not $dotnetCommand) {
        $missing += "Trusted OCR helper or .NET 8 SDK (dotnet)"
    } else {
        $dotnetSdks = dotnet --list-sdks
        if (-not ($dotnetSdks -match "^8\.")) { $missing += "Trusted OCR helper or .NET 8 SDK" }
    }
}
if (-not $pythonCommand) {
    $missing += "Python (python)"
} else {
    python -c "import PySide6" 2>$null
    if ($LASTEXITCODE -ne 0) { $missing += "Python package PySide6" }
}
if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) { $missing += "Input directory: $InputDirectory" }
if ($Manifest -and -not (Test-Path -LiteralPath $Manifest -PathType Leaf)) { $missing += "Manifest: $Manifest" }
if ($missing.Count -gt 0) { throw "Missing requirements: $($missing -join ', ')" }

New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
if ($trustedPrebuilt) {
    New-Item -ItemType Directory -Path $helperOutput -Force | Out-Null
    $helperPath = Join-Path $helperOutput "ExpeditionWindowsOcr.exe"
    Copy-Item -LiteralPath $prebuiltHelper -Destination $helperPath -Force
} else {
    Copy-Item -LiteralPath $projectSource -Destination $localProject -Recurse -Force
    dotnet build (Join-Path $localProject "ExpeditionWindowsOcr.csproj") `
        --configuration Release --output $helperOutput
    if ($LASTEXITCODE -ne 0) { throw "Failed to build the Windows OCR helper." }
    $helperPath = Join-Path $helperOutput "ExpeditionWindowsOcr.dll"
}
$env:POENAVI_WINDOWS_OCR_HELPER = $helperPath
if ($helperPath.EndsWith(".exe")) {
    & $helperPath --check ja-JP
} else {
    dotnet $helperPath --check ja-JP
}
$japaneseOcrExitCode = $LASTEXITCODE
if ($japaneseOcrExitCode -ne 0) {
    throw "Windows Japanese OCR is not installed. Add Japanese OCR in Windows Language settings."
}
if ($helperPath.EndsWith(".exe")) {
    & $helperPath --check en-US
} else {
    dotnet $helperPath --check en-US
}
$numericOcrAvailable = $LASTEXITCODE -eq 0

$arguments = @($probe, "--input-dir", $InputDirectory, "--output", $Output)
if ($Manifest) { $arguments += @("--manifest", $Manifest) }
if ($numericOcrAvailable) { $arguments += @("--numeric-language", "en-US") }
python @arguments
$probeExitCode = $LASTEXITCODE
$report = Join-Path $Output "report.html"
if (Test-Path -LiteralPath $report -PathType Leaf) {
    Start-Process $report
    Write-Host "OCR report: $report"
}
if ($probeExitCode -ne 0) { throw "One or more OCR results did not match the expected tiers." }
