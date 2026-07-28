@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "POENAVI_USER_DATA_DIR=%~dp0.dev-user-data"
echo ============================================
echo   PoENavi - Dev Run
echo ============================================
echo User data: %POENAVI_USER_DATA_DIR%
echo.
echo Source: %CD%

python -c "from winrt.windows.globalization import Language; from winrt.windows.graphics.imaging import BitmapDecoder; from winrt.windows.media.ocr import OcrEngine; from winrt.windows.storage.streams import InMemoryRandomAccessStream" >nul 2>&1
if errorlevel 1 (
    echo OCR components are missing. Installing dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install PoENavi dependencies.
        echo Check the network connection and Python/pip setup, then run this file again.
        echo.
        pause
        exit /b 1
    )
    echo.
)

python -B main.py
echo.
pause
