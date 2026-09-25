@echo off
chcp 65001 >nul
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0spikes\001-ndlocr-resident-memory\run_probe.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo TEST FAILED. Check the messages above.
if "%EXIT_CODE%"=="0" echo TEST SUCCESS. The RAM report has been opened.
pause
exit /b %EXIT_CODE%
