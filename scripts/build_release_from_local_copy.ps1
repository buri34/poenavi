param(
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$source = (Resolve-Path $SourceRoot).Path
$sourceName = Split-Path $source -Leaf
$missing = [System.Collections.Generic.List[string]]::new()

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonLauncher) {
    $missing.Add("Python Launcher (py.exe) and Python 3.12")
}
else {
    & $pythonLauncher.Source -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $missing.Add("Python 3.12 (64-bit)")
    }
}

$dotnet = Get-Command dotnet.exe -ErrorAction SilentlyContinue
if ($null -eq $dotnet) {
    $missing.Add(".NET 8 SDK")
}
else {
    $sdks = @(& $dotnet.Source --list-sdks)
    if (-not ($sdks | Where-Object { $_ -match '^8\.' })) {
        $missing.Add(".NET 8 SDK")
    }
}

foreach ($required in @(
    "scripts\build_release.ps1", "requirements-build.txt",
    "requirements-ndlocr.txt", "tools\ExpeditionWindowsOcr\ExpeditionWindowsOcr.csproj"
)) {
    if (-not (Test-Path (Join-Path $source $required))) {
        $missing.Add("Source file: $required")
    }
}

if ($missing.Count -gt 0) {
    Write-Host "The following build prerequisites are missing:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host "Install Python 3.12 from python.org and the .NET 8 SDK from dotnet.microsoft.com, then run this file again."
    exit 2
}

$localBase = Join-Path $env:LOCALAPPDATA "PoENavi\SourceBuilds"
$localRoot = Join-Path $localBase $sourceName
if (-not $localRoot.StartsWith($localBase, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe local build path: $localRoot"
}
if (Test-Path $localRoot) {
    Remove-Item -Recurse -Force $localRoot
}
New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
Write-Host "Copying the fixed source snapshot to local storage..."
Copy-Item (Join-Path $source "*") $localRoot -Recurse -Force
Copy-Item (Join-Path $source ".gitattributes") $localRoot -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $source ".gitignore") $localRoot -Force -ErrorAction SilentlyContinue

Push-Location $localRoot
try {
    & $pythonLauncher.Source -3.12 -m venv .venv-build
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python 3.12 build environment"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_release.ps1 `
        -Python ".venv-build\Scripts\python.exe"
    if ($LASTEXITCODE -ne 0) {
        throw "PoENavi release build failed"
    }
}
finally {
    Pop-Location
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$commitLabel = $sourceName -replace '^poenavi-windows-', ''
$outputRoot = Join-Path (Split-Path $source -Parent) "poenavi-build-output-$commitLabel-$timestamp"
New-Item -ItemType Directory -Path $outputRoot -ErrorAction Stop | Out-Null
Copy-Item (Join-Path $localRoot "PoENavi.zip") $outputRoot
Copy-Item (Join-Path $localRoot "PoENavi.zip.sha256") $outputRoot

$zip = Get-Item (Join-Path $outputRoot "PoENavi.zip")
$zipHash = (Get-FileHash $zip.FullName -Algorithm SHA256).Hash.ToLower()
$buildInfo = @(
    "source_snapshot=$sourceName",
    "ndlocr_version=1.3.1",
    "ndlocr_source_sha256=e510d3a7b878395ea9de0bdd365711b699e5fd430b5c7e23a40e918e913fd1f2",
    "zip_bytes=$($zip.Length)",
    "zip_sha256=$zipHash",
    "built_at=$((Get-Date).ToString('o'))"
)
Set-Content -Path (Join-Path $outputRoot "BUILD_INFO.txt") -Value $buildInfo -Encoding utf8

Write-Host "Build output: $outputRoot" -ForegroundColor Green
Write-Host "PoENavi.zip: $($zip.Length) bytes" -ForegroundColor Green
Start-Process explorer.exe $outputRoot
