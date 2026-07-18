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
Invoke-Python -m pip install --upgrade -r requirements.txt pyinstaller pytest

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

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
    "--icon", "assets\app\updater.ico",
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
$hash = (Get-FileHash PoENavi.zip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path PoENavi.zip.sha256 -Value "$hash  PoENavi.zip" -Encoding ascii

Write-Output "Built PoENavi"
$zipPath = (Resolve-Path PoENavi.zip).Path
$shaPath = (Resolve-Path PoENavi.zip.sha256).Path
Write-Output "Release artifacts (do not move or re-zip dist\\PoENavi):"
Write-Output "  ZIP: $zipPath"
Write-Output "  SHA256: $shaPath"
