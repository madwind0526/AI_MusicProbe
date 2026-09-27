@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run "python -m venv .venv" first.
    exit /b 1
)

rem Always free the port before launching. On Windows a leftover server does not
rem make the new one fail with EADDRINUSE -- it silently takes the port over, which
rem kills the browser's event stream mid-analysis and looks like a crashed server
rem while the old process keeps running to completion in the background.
rem stop.bat also reaps the port-less orphans, so call it instead of duplicating it.
call "%~dp0stop.bat"

echo Starting AI Music Probe: http://127.0.0.1:8792
".venv\Scripts\python.exe" -m probe.app
