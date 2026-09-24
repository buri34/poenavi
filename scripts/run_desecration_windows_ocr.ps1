param(
    [string]$InputDirectory = "",
    [string]$Manifest = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$projectSource = Join-Path $repoRoot "tools\ExpeditionWindowsOcr"
$probe = Join-Path $repoRoot "scripts\desecration_ocr_probe.py"
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
if (-not $dotnetCommand) {
    $missing += ".NET 8 SDK (dotnet)"
} else {
    $dotnetSdks = dotnet --list-sdks
    if (-not ($dotnetSdks -match "^8\.")) { $missing += ".NET 8 SDK" }
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
Copy-Item -LiteralPath $projectSource -Destination $localProject -Recurse -Force
dotnet build (Join-Path $localProject "ExpeditionWindowsOcr.csproj") `
    --configuration Release --output $helperOutput
if ($LASTEXITCODE -ne 0) { throw "Failed to build the Windows OCR helper." }
$env:POENAVI_WINDOWS_OCR_HELPER = Join-Path $helperOutput "ExpeditionWindowsOcr.dll"
dotnet $env:POENAVI_WINDOWS_OCR_HELPER --check ja-JP
if ($LASTEXITCODE -ne 0) {
    throw "Windows Japanese OCR is not installed. Add Japanese OCR in Windows Language settings."
}

$arguments = @($probe, "--input-dir", $InputDirectory, "--output", $Output)
if ($Manifest) { $arguments += @("--manifest", $Manifest) }
python @arguments
$probeExitCode = $LASTEXITCODE
$report = Join-Path $Output "report.html"
if (Test-Path -LiteralPath $report -PathType Leaf) {
    Start-Process $report
    Write-Host "OCR report: $report"
}
if ($probeExitCode -ne 0) { throw "One or more OCR results did not match the expected tiers." }
