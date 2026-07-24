@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
set "POENAVI_USER_DATA_DIR=%~dp0.dev-user-data"

if not exist "%VENV_PYTHON%" (
    echo ERROR: The local Python environment was not found:
    echo   %VENV_PYTHON%
    echo.
    echo Create it with:
    echo   py -3.11 -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt pytest
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   PoENavi - Dev Run
echo ============================================
echo Python:    %VENV_PYTHON%
echo User data: %POENAVI_USER_DATA_DIR%
echo.
"%VENV_PYTHON%" main.py %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.

if not "%EXIT_CODE%"=="0" (
    echo PoENavi exited with code %EXIT_CODE%.
)

pause
exit /b %EXIT_CODE%
