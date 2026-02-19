@echo off
chcp 65001 >nul
echo ============================================
echo   PoENavi - exe Build
echo ============================================
echo.

REM Install PyInstaller if needed
pip install pyinstaller 2>nul

REM Build
pyinstaller --noconfirm --onedir --windowed ^
    --name "PoENavi" ^
    --add-data "guide_data.json;." ^
    --add-data "monster_levels.json;." ^
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

echo.
if exist dist\PoENavi\PoENavi.exe (
    echo BUILD SUCCESS!
    echo    exe is in: dist\PoENavi    echo    Zip the dist\PoENavi\ folder to distribute
) else (
    echo BUILD FAILED. Check errors above.
)
echo.
pause
