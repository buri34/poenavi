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
python -B main.py
echo.
pause
