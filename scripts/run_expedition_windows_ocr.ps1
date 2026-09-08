param(
    [string]$InputDirectory = "",
    [string]$Dictionary = "",
    [string]$Csv = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Split-Path -Parent $repoRoot
$project = Join-Path $repoRoot "tools\ExpeditionWindowsOcr\ExpeditionWindowsOcr.csproj"
$probe = Join-Path $repoRoot "scripts\expedition_ocr_probe.py"
if (-not $InputDirectory) { $InputDirectory = Join-Path $shareRoot "expedition-ocr-screenshots-20260908" }
if (-not $Dictionary) {
    $Dictionary = Join-Path $repoRoot "vendor-sources\poe2-trade-api-2026-08-09\items_ja.json"
}
if (-not $Csv) { $Csv = Join-Path $shareRoot "expedition-items-windows.csv" }
if (-not $Output) { $Output = Join-Path $shareRoot "expedition-ocr-windows-run" }
$helperOutput = Join-Path $Output "helper"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 8 SDK was not found: https://dotnet.microsoft.com/download/dotnet/8.0"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Activate the PoENavi development environment."
}
if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
    throw "Input image directory was not found: $InputDirectory"
}
if (-not (Test-Path -LiteralPath $Dictionary -PathType Leaf)) {
    throw "Japanese item dictionary was not found: $Dictionary"
}

dotnet build $project --configuration Release --output $helperOutput
if ($LASTEXITCODE -ne 0) { throw "Failed to build the Windows OCR helper." }
$env:POENAVI_WINDOWS_OCR_HELPER = Join-Path $helperOutput "ExpeditionWindowsOcr.dll"

python $probe $InputDirectory `
    --engine windows `
    --language ja-JP `
    --dictionary $Dictionary `
    --csv $Csv `
    --output $Output
if ($LASTEXITCODE -ne 0) { throw "OCR probe failed." }

Write-Host "Windows OCR CSV: $((Resolve-Path $Csv).Path)"
