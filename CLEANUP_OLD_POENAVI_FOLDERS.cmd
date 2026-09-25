@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\cleanup_old_poenavi_folders.ps1" -Root "%SCRIPT_DIR%.." -ProtectPath "%SCRIPT_DIR%" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" echo Cleanup stopped with an error. No unlisted folder was targeted.
pause
exit /b %EXIT_CODE%
