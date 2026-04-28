@echo off
setlocal enabledelayedexpansion

:: ================================================================
::  Folder Icon Changer — Smart Launcher
::  Flow: Python check → install if missing → venv → packages → run
:: ================================================================

title Folder Icon Changer — Starting...
chcp 65001 >nul 2>&1

:: Project root = the folder this .bat lives in
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "VENV=%ROOT%\.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "REQS=%ROOT%\requirements.txt"
set "STAMP=%VENV%\.reqs_stamp"

echo.
echo  +--------------------------------------------------+
echo  ^|        Folder Icon Changer  —  Launcher         ^|
echo  +--------------------------------------------------+
echo.

:: ================================================================
::  [1/4]  Locate Python 3.10 or newer
:: ================================================================
echo  [1/4]  Checking for Python 3.10+...
echo.

set "PYTHON_CMD="
set "PYTHON_VER="

:: Try the 'python' command first
python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYTHON_VER=%%v"
    call :check_ver "!PYTHON_VER!"
    if not errorlevel 1 set "PYTHON_CMD=python"
)

:: Try the Windows 'py' launcher as a fallback
if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2" %%v in ('py -3 --version 2^>^&1') do set "PYTHON_VER=%%v"
        call :check_ver "!PYTHON_VER!"
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )
)

if defined PYTHON_CMD (
    echo         Found: Python %PYTHON_VER% [OK]
    goto :setup_venv
)

:: ---- Python not found — offer to auto-install via winget ----
echo         Python 3.10 or newer was NOT found on this PC.
echo.
echo   This app needs Python 3.10+. Windows can install it
echo   automatically in about 1-2 minutes — no tech knowledge
echo   required.
echo.
choice /C YN /N /M "  Auto-install Python 3.12 now? [Y/N] "
if errorlevel 2 goto :user_declined_python

:: Check winget is available (built into Windows 10 1709+ / Windows 11)
winget --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Windows Package Manager (winget) is not available.
    goto :show_manual_python_instructions
)

echo.
echo         Downloading and installing Python 3.12, please wait...
echo.
winget install --id Python.Python.3.12 --source winget ^
    --accept-source-agreements --accept-package-agreements --silent
if errorlevel 1 (
    echo.
    echo   Automatic install failed. See the message above.
    goto :show_manual_python_instructions
)

:: Refresh the PATH in this session from the Windows registry
echo.
echo         Refreshing PATH...
for /f "usebackq delims=" %%p in (`powershell -noprofile -command ^
    "[Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH','User')"`) do set "PATH=%%p"

:: Re-check Python after install
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python was installed but needs a fresh terminal to
    echo   activate. Please close this window and run the
    echo   launcher again.
    echo.
    pause
    exit /b 0
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYTHON_VER=%%v"
set "PYTHON_CMD=python"
echo         Python %PYTHON_VER% installed and ready. [OK]
goto :setup_venv

:user_declined_python
echo.
echo   To run Folder Icon Changer you need Python 3.10+.
echo   Download it from:  https://www.python.org/downloads/
echo.
echo   During installation: tick  "Add Python to PATH"
echo   Then double-click this launcher again.
echo.
pause
exit /b 0

:show_manual_python_instructions
echo.
echo   Please install Python 3.10+ manually from:
echo      https://www.python.org/downloads/
echo.
echo   During installation: tick  "Add Python to PATH"
echo.
pause
exit /b 1

:: ================================================================
::  [2/4]  Set up the virtual environment
:: ================================================================
:setup_venv
echo.
echo  [2/4]  Checking virtual environment...

if exist "%VENV_PY%" (
    echo         Virtual environment OK. [OK]
    goto :check_deps
)

echo         Creating isolated Python environment...
%PYTHON_CMD% -m venv "%VENV%"
if errorlevel 1 (
    echo.
    echo   ERROR: Could not create the virtual environment.
    echo   Try right-clicking this launcher and choosing
    echo   "Run as administrator".
    echo.
    pause
    exit /b 1
)

:: Delete stamp so packages are installed into the fresh venv
if exist "%STAMP%" del "%STAMP%"
echo         Environment created. [OK]

:: ================================================================
::  [3/4]  Install / sync packages (skipped when nothing changed)
:: ================================================================
:check_deps
echo.
echo  [3/4]  Checking packages...

:: Hash requirements.txt — only reinstall when the file changes
for /f "usebackq delims=" %%h in (`powershell -noprofile -command ^
    "(Get-FileHash '%REQS%' -Algorithm SHA256).Hash"`) do set "CUR_HASH=%%h"

set "OLD_HASH="
if exist "%STAMP%" set /p OLD_HASH=<"%STAMP%"

if "%CUR_HASH%"=="%OLD_HASH%" (
    echo         All packages are up to date. [OK]
    goto :launch
)

echo         Installing packages (first run: 1-3 min, please wait)...
echo.

:: Silently upgrade pip so it can install modern packages
"%VENV_PIP%" install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 echo         (pip self-upgrade skipped, continuing)

:: Install the app's dependencies with visible progress
"%VENV_PIP%" install -r "%REQS%"
if errorlevel 1 (
    echo.
    echo   ERROR: Package installation failed!
    echo.
    echo   Common causes:
    echo     - No internet connection
    echo     - Firewall or proxy blocking pip
    echo     - Disk is full
    echo.
    echo   Fix the issue and run the launcher again.
    echo.
    pause
    exit /b 1
)

:: Write hash stamp so the next launch is instant
>"%STAMP%" echo %CUR_HASH%
echo.
echo         Packages installed successfully. [OK]

:: ================================================================
::  [4/4]  Launch the application
:: ================================================================
:launch
echo.
echo  [4/4]  Launching Folder Icon Changer...
echo.
title Folder Icon Changer
cd /d "%ROOT%"
"%VENV_PY%" -m app.main
set "APP_EXIT=%errorlevel%"

if %APP_EXIT% neq 0 (
    echo.
    echo  +---------------------------------------------------------+
    echo  ^|  The app closed with an error  (exit code: %APP_EXIT%)   ^|
    echo  ^|  Review the messages above for details.                 ^|
    echo  +---------------------------------------------------------+
    echo.
    pause
)
exit /b %APP_EXIT%

:: ================================================================
::  Subroutine: check_ver "<major.minor.patch>"
::  Returns errorlevel 0 = compatible (>= 3.10), 1 = too old
:: ================================================================
:check_ver
set "_cv=%~1"
set /a "_maj=0"
set /a "_min=0"
for /f "tokens=1,2 delims=." %%a in ("%_cv%") do (
    set /a "_maj=%%a" 2>nul
    set /a "_min=%%b" 2>nul
)
if %_maj% lss 3 exit /b 1
if %_maj% gtr 3 exit /b 0
if %_min% geq 10 exit /b 0
exit /b 1
