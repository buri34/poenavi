@echo off
chcp 65001 >nul
setlocal

set "SOURCE_DIR=%~dp0dist\PoENavi-v2.4-updater-source"
set "TEST_DIR=%~dp0dist\PoENavi-v2.4-updater-test"
set "TEST_CLIENT=%TEST_DIR%\PoENavi.exe"
set "POENAVI_USER_DATA_DIR=%~dp0.prerelease-test-user-data"

if not exist "%SOURCE_DIR%\PoENavi.exe" (
    echo ERROR: pristine v2.4.0 updater-enabled test client was not found.
    echo Build v2.4.0 from the current source and copy dist\PoENavi to:
    echo   dist\PoENavi-v2.4-updater-source
    pause
    exit /b 1
)
if not exist "%SOURCE_DIR%\PoENaviUpdater.exe" (
    echo ERROR: PoENaviUpdater.exe was not found in the v2.4.0 test client.
    echo The official v2.4.0 Release cannot be used for this test.
    pause
    exit /b 1
)

if exist "%TEST_DIR%" rmdir /s /q "%TEST_DIR%"
robocopy "%SOURCE_DIR%" "%TEST_DIR%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo ERROR: Failed to create a fresh v2.4.0 test client.
    pause
    exit /b 1
)

set "POENAVI_UPDATE_TEST_TAG=v2.5.0"
if exist "%POENAVI_USER_DATA_DIR%" rmdir /s /q "%POENAVI_USER_DATA_DIR%"
echo Starting PoENavi in pre-release update test mode for v2.5.0.
echo Test user data: %POENAVI_USER_DATA_DIR%
start "" "%TEST_CLIENT%"
