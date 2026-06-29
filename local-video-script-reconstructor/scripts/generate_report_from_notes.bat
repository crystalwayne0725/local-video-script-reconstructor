@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "STATE_DIR=%LocalAppData%\LocalVideoScriptReconstructor"
set "PYTHON_CACHE=%STATE_DIR%\python_path.txt"
set "PYTHON_CMD=python"
if exist "%PYTHON_CACHE%" (
    set /p "PYTHON_CMD="<"%PYTHON_CACHE%"
)

"%PYTHON_CMD%" --version >nul 2>nul
if errorlevel 1 (
    if exist "%LocalAppData%\Python\bin\python.exe" (
        set "PYTHON_CMD=%LocalAppData%\Python\bin\python.exe"
    )
)

"%PYTHON_CMD%" --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install Python 3.9 or newer, then run this file again.
    exit /b 1
)

if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>nul
> "%PYTHON_CACHE%" echo %PYTHON_CMD%

if "%~1"=="" (
    echo [ERROR] No organized notes path provided.
    echo Usage: scripts\generate_report_from_notes.bat ^<organized_notes.md^> [--output report.md]
    exit /b 1
)

"%PYTHON_CMD%" scripts\generate_report_from_notes.py %*
exit /b %ERRORLEVEL%
