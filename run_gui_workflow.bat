@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python workflow_entry.py
) else (
    py -3 workflow_entry.py
)

set "exit_code=%errorlevel%"
if not "%exit_code%"=="0" (
    echo.
    echo GUI Workflow exited with code %exit_code%.
    pause
)

endlocal & exit /b %exit_code%
