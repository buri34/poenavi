@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "POENAVI_USER_DATA_DIR=%~dp0.dev-user-data"
set "POENAVI_GUIDE_DEV_ZONE_ID=act10_area12"
echo ============================================
echo   PoENavi - Dev Run
echo ============================================
echo User data: %POENAVI_USER_DATA_DIR%
echo Guide editor: Act 10 - 聖廟 (act10_area12)
echo.
echo Source: %CD%
python -B main.py
echo.
pause
