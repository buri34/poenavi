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

Invoke-Python -m pip install --upgrade pip setuptools wheel
Invoke-Python -m pip install --upgrade -r requirements.txt pyinstaller pytest pillow

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force build\generated | Out-Null

$iconCode = @"
from pathlib import Path
from PIL import Image, ImageOps
source = Image.open(Path('assets/icons/green.png')).convert('RGBA')
icon = ImageOps.fit(source, (256, 256), method=Image.Resampling.LANCZOS)
icon.save(Path('build/generated/updater.ico'), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
"@
& $Python -c $iconCode
if ($LASTEXITCODE -ne 0) {
    throw "Failed to generate updater.ico"
}

$appArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--noupx", "--onedir", "--windowed",
    "--name", "PoENavi",
    "--icon", "assets\app\icon.ico",
    "--distpath", "dist",
    "--workpath", "build\app",
    "--add-data", "assets\app\icon.ico;.",
    "--add-data", "default_config.json;.",
    "--add-data", "guide_data.json;.",
    "--add-data", "guide_data_poe2.json;.",
    "--add-data", "monster_levels.json;.",
    "--add-data", "data;data",
    "--add-data", "assets;assets",
    "--add-data", "maps;maps",
    "--hidden-import", "PySide6.QtWidgets",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "pynput",
    "--hidden-import", "pynput.keyboard",
    "--hidden-import", "pynput.keyboard._win32",
    "--hidden-import", "keyboard",
    "main.py"
)
Invoke-Python @appArgs

$updaterArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--noupx", "--onefile", "--windowed",
    "--name", "PoENaviUpdater",
    "--icon", "build\generated\updater.ico",
    "--distpath", "dist\PoENavi",
    "--workpath", "build\updater",
    "--hidden-import", "PySide6.QtWidgets",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "updater_main.py"
)
Invoke-Python @updaterArgs

$version = (& $Python -c "from src.version import APP_VERSION; print(APP_VERSION)").Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read APP_VERSION"
}
Invoke-Python scripts\generate_update_manifest.py dist\PoENavi $version

if (-not (Test-Path dist\PoENavi\PoENavi.exe)) {
    throw "PoENavi.exe was not built"
}
if (-not (Test-Path dist\PoENavi\PoENaviUpdater.exe)) {
    throw "PoENaviUpdater.exe was not built"
}
if (-not (Test-Path dist\PoENavi\update-manifest.json)) {
    throw "update-manifest.json was not generated"
}

Remove-Item PoENavi.zip, PoENavi.zip.sha256 -ErrorAction SilentlyContinue
Compress-Archive -Path dist\PoENavi -DestinationPath PoENavi.zip
$hash = (Get-FileHash PoENavi.zip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path PoENavi.zip.sha256 -Value "$hash  PoENavi.zip" -Encoding ascii

Write-Output "Built PoENavi v$version"
Write-Output "Artifacts: PoENavi.zip, PoENavi.zip.sha256"
