@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   PoENavi - exe Build
echo ============================================
echo.

REM Use a dedicated build virtual environment to avoid unrelated packages
REM from the user's global Python environment being bundled accidentally.
set "VENV_DIR=.venv-build"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Creating build virtual environment...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 goto :error
)

echo Upgrading build tools...
"%PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error

echo Installing runtime dependencies...
"%PYTHON%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error

echo Installing/upgrading PyInstaller...
"%PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

echo.
echo PyInstaller version:
"%PYTHON%" -m PyInstaller --version
if errorlevel 1 goto :error

REM Clean previous build outputs so stale files are not packaged.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build
REM --noupx is explicit because packed binaries are more likely to trigger AV heuristics.
"%PYTHON%" -m PyInstaller --noconfirm --clean --noupx --onedir --windowed ^
    --name "PoENavi" ^
    --icon "icon.ico" ^
    --add-data "icon.ico;." ^
    --add-data "default_config.json;." ^
    --add-data "guide_data.json;." ^
    --add-data "guide_data_poe2.json;." ^
    --add-data "monster_levels.json;." ^
    --add-data "data;data" ^
    --add-data "assets;assets" ^
    --add-data "maps;maps" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "pynput" ^
    --hidden-import "pynput.keyboard" ^
    --hidden-import "pynput.keyboard._win32" ^
    --hidden-import "keyboard" ^
    main.py
if errorlevel 1 goto :error

echo.
if exist dist\PoENavi\PoENavi.exe (
    echo BUILD SUCCESS!
    echo    exe is in: dist\PoENavi
    echo    Zip the contents of dist\PoENavi\ to distribute.
    echo.
    powershell -NoProfile -Command "Get-FileHash -Algorithm SHA256 'dist\PoENavi\PoENavi.exe' | ForEach-Object { 'PoENavi.exe SHA256: ' + $_.Hash.ToLower() }"
) else (
    goto :error
)

echo.
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Check errors above.
echo.
pause
exit /b 1
