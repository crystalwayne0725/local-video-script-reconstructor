@echo off
setlocal EnableExtensions DisableDelayedExpansion

if defined LocalAppData (
    set "STATE_DIR=%LocalAppData%\LocalVideoScriptReconstructor"
) else if defined TEMP (
    set "STATE_DIR=%TEMP%\LocalVideoScriptReconstructor"
) else (
    set "STATE_DIR=%USERPROFILE%\LocalVideoScriptReconstructor"
)
set "PYTHON_CACHE=%STATE_DIR%\python_path.txt"
set "FOUND_PYTHON="
set "PROGRAMFILES_X86=%ProgramFiles(x86)%"
set "VENV_PYTHON=%STATE_DIR%\venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
    call :try_path "%VENV_PYTHON%"
    if defined FOUND_PYTHON goto found
)

if exist "%PYTHON_CACHE%" (
    set /p "CACHED_PYTHON="<"%PYTHON_CACHE%"
    if defined CACHED_PYTHON (
        call :try_path "%CACHED_PYTHON%"
        if defined FOUND_PYTHON goto found
    )
)

call :try_command py -3.12
if defined FOUND_PYTHON goto found
call :try_command py -3.11
if defined FOUND_PYTHON goto found
call :try_command py -3.10
if defined FOUND_PYTHON goto found
call :try_command py -3.9
if defined FOUND_PYTHON goto found
call :try_command py -3
if defined FOUND_PYTHON goto found
call :try_command python
if defined FOUND_PYTHON goto found
call :try_command python3
if defined FOUND_PYTHON goto found

for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
    call :try_path "%%~fD\python.exe"
    if defined FOUND_PYTHON goto found
)

for /d %%D in ("%ProgramFiles%\Python*") do (
    call :try_path "%%~fD\python.exe"
    if defined FOUND_PYTHON goto found
)

if defined PROGRAMFILES_X86 (
    for /d %%D in ("%PROGRAMFILES_X86%\Python*") do (
        call :try_path "%%~fD\python.exe"
        if defined FOUND_PYTHON goto found
    )
)

endlocal
exit /b 1

:found
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>nul
> "%PYTHON_CACHE%" echo %FOUND_PYTHON%
endlocal & set "PYTHON_CMD=%FOUND_PYTHON%"
exit /b 0

:try_command
if defined FOUND_PYTHON exit /b 0
set "CANDIDATE="
for /f "delims=" %%P in ('%* -c "import sys; print(sys.executable)" 2^>nul') do (
    if not defined CANDIDATE set "CANDIDATE=%%P"
)
if defined CANDIDATE call :try_candidate "%CANDIDATE%"
exit /b 0

:try_path
if defined FOUND_PYTHON exit /b 0
set "CANDIDATE=%~1"
call :try_candidate "%CANDIDATE%"
exit /b 0

:try_candidate
set "CANDIDATE=%~1"
if not defined CANDIDATE exit /b 0
if not exist "%CANDIDATE%" exit /b 0
"%CANDIDATE%" -c "import struct, sys; raise SystemExit(0 if sys.version_info >= (3, 9) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>nul
if not errorlevel 1 set "FOUND_PYTHON=%CANDIDATE%"
exit /b 0
