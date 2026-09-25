@echo off
chcp 65001 >nul
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_release_from_local_copy.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo BUILD FAILED. Check all prerequisite messages above.
if "%EXIT_CODE%"=="0" echo BUILD SUCCESS. The output folder has been opened.
pause
exit /b %EXIT_CODE%
