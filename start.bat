@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 가상 환경을 찾지 못했습니다. 먼저 python -m venv .venv 를 실행해 주세요.
  exit /b 1
)
echo AI Music Probe: http://127.0.0.1:8792
".venv\Scripts\python.exe" -m probe.app
