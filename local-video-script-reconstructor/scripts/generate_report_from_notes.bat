@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

call "%~dp0find_python_windows.bat"
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install 64-bit Python 3.9 or newer, then run this file again.
    exit /b 1
)

if "%~1"=="" (
    echo [ERROR] No organized notes path provided.
    echo Usage: scripts\generate_report_from_notes.bat ^<organized_notes.md^> [--output report.md] [--excel-output report.xlsx]
    exit /b 1
)

"%PYTHON_CMD%" scripts\generate_report_from_notes.py %*
exit /b %ERRORLEVEL%
