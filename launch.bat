@echo off
setlocal enabledelayedexpansion

:: ================================================================
::  Folder Icon Changer - Smart Launcher
::  Flow: Python check -> install if missing -> venv -> packages -> run
:: ================================================================

title Folder Icon Changer
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "VENV=%ROOT%\.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "REQS=%ROOT%\requirements.txt"
set "STAMP=%VENV%\.reqs_stamp"
set "DBG=%ROOT%\dbg.ps1"

:: #region agent log H1 H3 -- confirm set commands ran and vars are populated
powershell -noprofile -executionpolicy bypass -file "%DBG%" "launch.bat:20" "vars_set" "H1_H3" "ROOT_ok" "!ROOT!" "VENV_PIP" "!VENV_PIP!" "REQS" "!REQS!" >nul 2>&1
:: #endregion

echo.
echo  +--------------------------------------------------+
echo  ^|       Folder Icon Changer  -  Launcher          ^|
echo  +--------------------------------------------------+
echo.

:: ================================================================
:: [1/4]  Find Python 3.10 or newer
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

:: Try the Windows 'py' launcher as fallback
if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2" %%v in ('py -3 --version 2^>^&1') do set "PYTHON_VER=%%v"
        call :check_ver "!PYTHON_VER!"
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )
)

:: #region agent log H3 H4 -- confirm Python detection result
powershell -noprofile -executionpolicy bypass -file "%DBG%" "launch.bat:52" "python_check" "H3_H4" "PYTHON_CMD" "!PYTHON_CMD!" "PYTHON_VER" "!PYTHON_VER!" >nul 2>&1
:: #endregion

if defined PYTHON_CMD (
    echo         Found: Python %PYTHON_VER% [OK]
    goto :setup_venv
)

:: ---- Python not found ----
echo         Python 3.10 or newer was NOT found.
echo.
echo   This app needs Python 3.10+. Windows can install it
echo   automatically in about 1-2 minutes.
echo.
choice /C YN /N /M "  Auto-install Python 3.12 now? [Y/N] "
if errorlevel 2 goto :user_declined_python

winget --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Windows Package Manager ^(winget^) is not available.
    goto :show_manual_python
)

echo.
echo         Installing Python 3.12, please wait...
echo.
winget install --id Python.Python.3.12 --source winget --accept-source-agreements --accept-package-agreements --silent
if errorlevel 1 (
    echo.
    echo   Automatic install failed.
    goto :show_manual_python
)

echo         Refreshing PATH...
for /f "usebackq delims=" %%p in (`powershell -noprofile -command "[Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH','User')"`) do set "PATH=%%p"

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python installed! Close and reopen this window,
    echo   then run the launcher again.
    echo.
    pause
    exit /b 0
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYTHON_VER=%%v"
set "PYTHON_CMD=python"
echo         Python %PYTHON_VER% installed. [OK]
goto :setup_venv

:user_declined_python
echo.
echo   Install Python 3.10+ from: https://www.python.org/downloads/
echo   During install: tick "Add Python to PATH"
echo   Then run this launcher again.
echo.
pause
exit /b 0

:show_manual_python
echo.
echo   Install Python 3.10+ from: https://www.python.org/downloads/
echo   During install: tick "Add Python to PATH"
echo.
pause
exit /b 1

:: ================================================================
:: [2/4]  Set up virtual environment
:: ================================================================
:setup_venv
echo.
echo  [2/4]  Checking virtual environment...

if exist "%VENV_PY%" (
    echo         Virtual environment OK. [OK]
    goto :check_deps
)

echo         Creating Python environment...
%PYTHON_CMD% -m venv "%VENV%"
if errorlevel 1 (
    echo.
    echo   ERROR: Could not create virtual environment.
    echo   Try: right-click this file, then "Run as administrator"
    echo.
    pause
    exit /b 1
)
if exist "%STAMP%" del "%STAMP%"
echo         Environment created. [OK]

:: ================================================================
:: [3/4]  Install / sync packages
:: ================================================================
:check_deps
echo.
echo  [3/4]  Checking packages...

for /f "usebackq delims=" %%h in (`powershell -noprofile -command "(Get-FileHash '%REQS%' -Algorithm SHA256).Hash"`) do set "CUR_HASH=%%h"

set "OLD_HASH="
if exist "%STAMP%" set /p OLD_HASH=<"%STAMP%"

:: #region agent log H3 H4 -- confirm hash check
powershell -noprofile -executionpolicy bypass -file "%DBG%" "launch.bat:127" "hash_check" "H3_H4" "CUR_HASH" "!CUR_HASH!" "OLD_HASH" "!OLD_HASH!" "VENV_PIP" "!VENV_PIP!" >nul 2>&1
:: #endregion

if "%CUR_HASH%"=="%OLD_HASH%" (
    echo         All packages up to date. [OK]
    goto :launch
)

echo         Installing packages ^(first run takes 1-3 minutes^)...
echo.

"%VENV_PIP%" install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 echo         ^(pip self-upgrade skipped, continuing^)

"%VENV_PIP%" install -r "%REQS%"
if errorlevel 1 (
    echo.
    echo   ERROR: Package installation failed!
    echo   Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

>"%STAMP%" echo %CUR_HASH%
echo.
echo         Packages installed. [OK]

:: ================================================================
:: [4/4]  Launch
:: ================================================================
:launch
echo.
echo  [4/4]  Starting Folder Icon Changer...
echo.
title Folder Icon Changer
cd /d "%ROOT%"
"%VENV_PY%" -m app.main
set "APP_EXIT=%errorlevel%"

if %APP_EXIT% neq 0 (
    echo.
    echo   App closed with error ^(exit code: %APP_EXIT%^).
    echo   Check the output above for details.
    echo.
    pause
)
exit /b %APP_EXIT%

:: ================================================================
::  check_ver "<major.minor.patch>"
::  Returns errorlevel 0 if version >= 3.10, else 1
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
