@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

echo Local Video Script Reconstructor
echo ========================================================

set "PAUSE_ON_EXIT=0"
if "%~1"=="" set "PAUSE_ON_EXIT=1"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not defined HF_ENDPOINT set "HF_ENDPOINT=https://hf-mirror.com"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

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
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
)

if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>nul
> "%PYTHON_CACHE%" echo %PYTHON_CMD%

set "TARGET_PATH=%~1"
if not defined TARGET_PATH (
    echo Drag a video or folder onto this file, or paste a path below.
    set /p "TARGET_PATH=Video or folder path: "
)
set "TARGET_PATH=%TARGET_PATH:"=%"

if not defined TARGET_PATH (
    echo [ERROR] No video or folder path was provided.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
)

if not exist "%TARGET_PATH%" (
    echo [ERROR] Path not found: "%TARGET_PATH%"
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
)

set "WHISPER_MODEL=%~2"
if not defined WHISPER_MODEL set "WHISPER_MODEL=small"

set "LANGUAGE=%~3"
if not defined LANGUAGE set "LANGUAGE=zh"

echo [INFO] Python:
"%PYTHON_CMD%" --version
echo [INFO] Target: "%TARGET_PATH%"
echo [INFO] Whisper model: %WHISPER_MODEL%
echo [INFO] Language: %LANGUAGE%
echo [INFO] Model download endpoint: %HF_ENDPOINT%
echo.

echo [1/3] Checking dependencies...
"%PYTHON_CMD%" scripts\check_env.py >nul 2>nul
if errorlevel 1 (
    echo [SETUP] Dependencies are missing. Installing automatically...
    "%PYTHON_CMD%" scripts\bootstrap_windows.py
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        if "%PAUSE_ON_EXIT%"=="1" pause
        exit /b 1
    )
) else (
    echo [OK] Dependencies are ready.
)

echo.
echo [2/3] Generating Markdown transcript...
if exist "%TARGET_PATH%\*" (
    "%PYTHON_CMD%" scripts\organize.py --folder "%TARGET_PATH%" --recursive --whisper-model "%WHISPER_MODEL%" --fallback-whisper-model tiny --language "%LANGUAGE%"
) else (
    "%PYTHON_CMD%" scripts\organize.py --video "%TARGET_PATH%" --whisper-model "%WHISPER_MODEL%" --fallback-whisper-model tiny --language "%LANGUAGE%"
)

if errorlevel 1 (
    echo.
    echo [ERROR] Transcription failed. Read the messages above.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
)

echo.
echo [3/3] Done.
echo Ask Codex to read the generated *_转写稿.md files and produce final notes.
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 0
