@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_desecration_windows_ocr.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo The OCR test reported a failure. See the report path above.
if "%EXIT_CODE%"=="0" echo The OCR test finished successfully. The HTML report has been opened.
pause
exit /b %EXIT_CODE%
