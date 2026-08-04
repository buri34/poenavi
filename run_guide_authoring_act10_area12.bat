@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "POENAVI_USER_DATA_DIR=%~dp0.dev-user-data-guide-act10-area12"
set "POENAVI_GUIDE_DEV_ZONE_ID=act10_area12"
echo ============================================
echo   PoENavi - Guide Authoring
echo ============================================
echo Target: Act 10 - 聖廟 (act10_area12)
echo User data: %POENAVI_USER_DATA_DIR%
echo.
echo IMPORTANT: Close every running PoENavi window first.
echo.
python -B main.py
echo.
pause
