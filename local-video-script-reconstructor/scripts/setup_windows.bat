@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."

echo Local Video Script Reconstructor setup
echo ========================================================

set "PYTHON_CMD=python"
%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 (
    if exist "%LocalAppData%\Python\bin\python.exe" (
        set "PYTHON_CMD=%LocalAppData%\Python\bin\python.exe"
    )
)

"%PYTHON_CMD%" --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install Python 3.9 or newer, then run this file again.
    pause
    exit /b 1
)

echo [1/4] Python found:
"%PYTHON_CMD%" --version

echo.
echo [2/4] Installing Python dependencies from requirements.txt...
"%PYTHON_CMD%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies.
    pause
    exit /b 1
)

echo.
echo [3/4] Model API configuration...
echo [OK] No local API key is required.
echo This skill uses Codex Desktop's configured model provider for final summarization.
echo The transcription script defaults model downloads to https://hf-mirror.com for China network environments.

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
echo scripts\run_windows.bat "your_video.mp4"
echo scripts\run_windows.bat "your_video_folder"
echo For hard-subtitle OCR, run: "%PYTHON_CMD%" scripts\bootstrap_windows.py --ocr
pause
exit /b 0
