@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not defined HF_ENDPOINT set "HF_ENDPOINT=https://hf-mirror.com"
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

call "%~dp0find_python_windows.bat"
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install 64-bit Python 3.9 or newer, then run this file again.
    exit /b 1
)

if "%~1"=="" (
    echo [ERROR] No arguments provided.
    echo Usage: scripts\organize_windows.bat ^<organize.py arguments^>
    exit /b 1
)

"%PYTHON_CMD%" scripts\organize.py %*
exit /b %ERRORLEVEL%
