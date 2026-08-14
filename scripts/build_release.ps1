param(
    [string]$Python = ".venv-build\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CommandArgs)
    & $Python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

if ($Python -eq ".venv-build\Scripts\python.exe" -and -not (Test-Path $Python)) {
    py -3 -m venv .venv-build
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv-build"
    }
}

Invoke-Python -m pip install -r requirements-build.txt

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

$appVersion = & $Python -c "from src.version import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($appVersion)) {
    throw "Failed to read APP_VERSION"
}
$appVersion = $appVersion.Trim()

Invoke-Python scripts\generate_windows_version_info.py `
    --version $appVersion `
    --description "PoENavi" `
    --filename "PoENavi.exe" `
    --output "build\version\PoENavi-version.txt"
Invoke-Python scripts\generate_windows_version_info.py `
    --version $appVersion `
    --description "PoENavi Updater" `
    --filename "PoENaviUpdater.exe" `
    --output "build\version\PoENaviUpdater-version.txt"

$appArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--noupx", "--onedir", "--windowed",
    "--name", "PoENavi",
    "--icon", "assets\app\icon.ico",
    "--version-file", "build\version\PoENavi-version.txt",
    "--distpath", "dist",
    "--workpath", "build\app",
    "--add-data", "assets\app\icon.ico;.",
    "--add-data", "default_config.json;.",
    "--add-data", "guide_data.json;.",
    "--add-data", "guide_data_poe2.json;.",
    "--add-data", "monster_levels.json;.",
    "--add-data", "LICENSE;.",
    "--add-data", "README.md;.",
    "--add-data", "THIRD_PARTY_NOTICES.md;.",
    "--add-data", "data;data",
    "--add-data", "assets;assets",
    "--add-data", "maps;maps",
    "--hidden-import", "PySide6.QtWidgets",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "pynput",
    "--hidden-import", "pynput.keyboard",
    "--hidden-import", "pynput.keyboard._win32",
    "main.py"
)
Invoke-Python @appArgs

$updaterArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--noupx", "--onefile", "--windowed",
    "--name", "PoENaviUpdater",
    "--icon", "assets\app\updater.ico",
    "--version-file", "build\version\PoENaviUpdater-version.txt",
    "--distpath", "dist\PoENavi",
    "--workpath", "build\updater",
    "--hidden-import", "PySide6.QtWidgets",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "updater_main.py"
)
Invoke-Python @updaterArgs

if (-not (Test-Path dist\PoENavi\PoENavi.exe)) {
    throw "PoENavi.exe was not built"
}
if (-not (Test-Path dist\PoENavi\PoENaviUpdater.exe)) {
    throw "PoENaviUpdater.exe was not built"
}

Remove-Item PoENavi.zip, PoENavi.zip.sha256 -ErrorAction SilentlyContinue
$zipCreated = $false
$zipAttempts = 60
$zipCode = "import shutil; shutil.make_archive('PoENavi', 'zip', root_dir='dist', base_dir='PoENavi')"
for ($attempt = 1; $attempt -le $zipAttempts; $attempt++) {
    try {
        & $Python -c $zipCode
        if ($LASTEXITCODE -ne 0) {
            throw "ZIP creation failed with exit code $LASTEXITCODE"
        }
        $zipCreated = $true
        break
    }
    catch {
        Remove-Item PoENavi.zip -ErrorAction SilentlyContinue
        if ($attempt -eq $zipAttempts) {
            throw "PoENaviUpdater.exe remained locked for 3 minutes. Close PoENavi/PoENaviUpdater if running, then check Windows Security protection history or add the PoENavi build folder as a temporary exclusion before retrying. Original error: $($_.Exception.Message)"
        }

        Write-Warning "ZIP creation failed (attempt $attempt/$zipAttempts). PoENaviUpdater.exe may still be scanned or locked; waiting 3 seconds..."
        Start-Sleep -Seconds 3
    }
}

if (-not $zipCreated) {
    throw "PoENavi.zip was not created"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path PoENavi.zip))
try {
    $entryNames = @($archive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
    foreach ($requiredName in @("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "mod_metadata.json", "pseudo_relations.json", "pseudo_definitions.json", "map_mods.json")) {
        if (-not ($entryNames | Where-Object { $_ -match "(^|/)$([regex]::Escape($requiredName))$" })) {
            throw "Release audit failed: missing $requiredName"
        }
    }
    $forbidden = @($entryNames | Where-Object {
        $_ -match "(^|/)(tests|build|__pycache__)/" -or
        $_ -match "(poetore-sources\.lock\.json|\.candidate|stats\.min\.json|mods\.min\.json)$"
    })
    if ($forbidden.Count -gt 0) {
        throw "Release audit failed: development/raw data found: $($forbidden -join ', ')"
    }
    $metadataEntry = $archive.Entries | Where-Object { $_.FullName -match "(^|[\\/])mod_metadata\.json$" } | Select-Object -First 1
    if ($null -eq $metadataEntry -or $metadataEntry.Length -gt 8MB) {
        throw "Release audit failed: mod_metadata.json is missing or exceeds 8 MiB"
    }
}
finally {
    $archive.Dispose()
}

$hash = (Get-FileHash PoENavi.zip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path PoENavi.zip.sha256 -Value "$hash  PoENavi.zip" -Encoding ascii

Write-Output "Built PoENavi"
$zipPath = (Resolve-Path PoENavi.zip).Path
$shaPath = (Resolve-Path PoENavi.zip.sha256).Path
Write-Output "Release artifacts (do not move or re-zip dist\\PoENavi):"
Write-Output "  ZIP: $zipPath"
Write-Output "  SHA256: $shaPath"
