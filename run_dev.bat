@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "POENAVI_USER_DATA_DIR=%~dp0.dev-user-data"
set "POENAVI_TWILIGHT_TRACE=1"
echo ============================================
echo   PoENavi - Dev Run
echo ============================================
echo User data: %POENAVI_USER_DATA_DIR%
echo Twilight Strand trace: ON
echo.
echo Source: %CD%
python -B main.py
echo.
pause
