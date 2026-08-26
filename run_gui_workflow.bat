@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_LAUNCHER="

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_LAUNCHER=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_LAUNCHER=python"
    )
)

if not defined PYTHON_LAUNCHER (
    echo Python 3 was not found on PATH.
    echo Install Python 3.11+ and run this launcher again.
    set "exit_code=9009"
    goto :finish
)

call :run_python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is missing. Installing Python requirements...
    call :ensure_pip
    if errorlevel 1 (
        set "exit_code=%errorlevel%"
        goto :finish
    )

    call :run_python -m pip install -r requirements.txt
    if errorlevel 1 (
        set "exit_code=%errorlevel%"
        goto :finish
    )
)

call :run_python workflow_entry.py
set "exit_code=%errorlevel%"

:finish
if not "%exit_code%"=="0" (
    echo.
    echo GUI Workflow exited with code %exit_code%.
    pause
)

endlocal & exit /b %exit_code%

:run_python
if /i "%PYTHON_LAUNCHER%"=="python" (
    python %*
) else (
    py -3 %*
)
exit /b %errorlevel%

:ensure_pip
call :run_python -m pip --version >nul 2>nul
if not errorlevel 1 (
    exit /b 0
)

echo pip is missing. Bootstrapping it with ensurepip...
call :run_python -m ensurepip --upgrade
if errorlevel 1 (
    echo Failed to bootstrap pip.
    exit /b %errorlevel%
)

call :run_python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo pip is still unavailable after ensurepip.
)
exit /b %errorlevel%
