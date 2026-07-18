@echo off
chcp 65001 >nul
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test_local_update.ps1"
if errorlevel 1 goto :error

echo.
echo LOCAL UPDATE TEST SUCCESS
pause
exit /b 0

:error
echo.
echo LOCAL UPDATE TEST FAILED. Check errors above.
pause
exit /b 1
