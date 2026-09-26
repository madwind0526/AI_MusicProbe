@echo off
setlocal enabledelayedexpansion
echo Stopping AI Music Probe...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8792" ^| findstr "LISTENING"') do (
    echo Stopping server on port 8792 ^(PID %%P^)...
    taskkill /F /PID %%P >nul 2>&1
)

echo Done.
