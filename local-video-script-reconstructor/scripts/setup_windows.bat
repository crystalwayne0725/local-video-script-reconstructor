@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

echo Local Video Script Reconstructor setup
echo ========================================================

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not defined HF_ENDPOINT set "HF_ENDPOINT=https://hf-mirror.com"
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"

call "%~dp0find_python_windows.bat"
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install 64-bit Python 3.9 or newer, then run this file again.
    pause
    exit /b 1
)

echo [1/4] Python found:
"%PYTHON_CMD%" --version

echo.
echo [2/4] Creating/reusing the skill virtual environment and installing dependencies...
"%PYTHON_CMD%" scripts\bootstrap_windows.py
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies.
    pause
    exit /b 1
)
call "%~dp0find_python_windows.bat"
if errorlevel 1 (
    echo [ERROR] Runtime Python was not found after dependency installation.
    pause
    exit /b 1
)

echo.
echo [3/4] Model API configuration...
echo [OK] No local API key is required.
echo This skill uses Codex Desktop's configured model provider for final summarization.
echo The transcription script defaults model downloads to https://hf-mirror.com for China network environments.
echo Python dependency installs default to https://pypi.tuna.tsinghua.edu.cn/simple unless PIP_INDEX_URL is set.

echo.
echo [4/4] Running environment check...
"%PYTHON_CMD%" scripts\check_env.py
if errorlevel 1 (
    echo.
    echo [FAILED] Setup finished, but the environment is not ready.
    echo Read the messages above, fix missing items, then run scripts\check_env.py again.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Setup complete. You can now run:
echo scripts\run_windows.bat "VIDEO_PATH"
echo scripts\run_windows.bat "FOLDER_PATH"
echo For hard-subtitle OCR, run: "%PYTHON_CMD%" scripts\bootstrap_windows.py --ocr
pause
exit /b 0
