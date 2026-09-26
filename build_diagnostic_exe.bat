@echo off
chcp 65001 >nul
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_release.ps1" -Diagnostic
if errorlevel 1 goto :error

echo.
echo BUILD SUCCESS: PoENavi-diagnostic.zip and PoENavi-diagnostic.zip.sha256
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Check errors above.
pause
exit /b 1
