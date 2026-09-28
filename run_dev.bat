@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "POENAVI_USER_DATA_DIR=%~dp0.dev-user-data"
set "POENAVI_POE2_GUIDE_DEV=1"
set "POENAVI_DEV_RUNTIME=%LOCALAPPDATA%\PoENavi\DevRuntime"
set "POENAVI_DEV_PYTHON=%POENAVI_DEV_RUNTIME%\Scripts\python.exe"
set "POENAVI_DEV_REQUIREMENTS=%POENAVI_DEV_RUNTIME%\requirements.txt"
echo ============================================
echo   PoENavi - Dev Run
echo ============================================
echo User data: %POENAVI_USER_DATA_DIR%
echo.
echo Source: %CD%

if not exist "%POENAVI_DEV_PYTHON%" goto create_runtime
goto check_requirements

:create_runtime
echo Preparing isolated Python environment...
python -m venv "%POENAVI_DEV_RUNTIME%"
if errorlevel 1 goto runtime_error

:check_requirements
if not exist "%POENAVI_DEV_REQUIREMENTS%" goto install_requirements
fc /b "%~dp0requirements.txt" "%POENAVI_DEV_REQUIREMENTS%" >nul
if errorlevel 1 goto install_requirements
"%POENAVI_DEV_PYTHON%" -c "import PySide6, miniaudio, pynput, urllib3" >nul 2>&1
if errorlevel 1 goto install_requirements
goto launch

:install_requirements
echo Installing or updating PoENavi runtime dependencies...
"%POENAVI_DEV_PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto dependency_error
copy /y "%~dp0requirements.txt" "%POENAVI_DEV_REQUIREMENTS%" >nul

:launch
"%POENAVI_DEV_PYTHON%" -B main.py
goto finished

:runtime_error
echo.
echo ERROR: Failed to create the isolated Python environment.
goto failed

:dependency_error
echo.
echo ERROR: Failed to install PoENavi runtime dependencies.

:failed
echo Close this window and run run_dev.bat again after checking the network connection.
pause
exit /b 1

:finished
echo.
pause
endlocal
