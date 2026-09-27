@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run "python -m venv .venv" first.
  exit /b 1
)
echo AI Music Probe: http://127.0.0.1:8792
".venv\Scripts\python.exe" -m probe.app
