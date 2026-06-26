@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not defined HF_ENDPOINT set "HF_ENDPOINT=https://hf-mirror.com"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

set "PYTHON_CMD=python"
"%PYTHON_CMD%" --version >nul 2>nul
if errorlevel 1 (
    if exist "%LocalAppData%\Python\bin\python.exe" (
        set "PYTHON_CMD=%LocalAppData%\Python\bin\python.exe"
    )
)

"%PYTHON_CMD%" --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    exit /b 1
)

if "%~1"=="" (
    echo [ERROR] No arguments provided.
    echo Usage: scripts\organize_windows.bat ^<organize.py arguments^>
    exit /b 1
)

"%PYTHON_CMD%" scripts\organize.py %*
exit /b %ERRORLEVEL%
