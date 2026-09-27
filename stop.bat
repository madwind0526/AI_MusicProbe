@echo off
setlocal enabledelayedexpansion
echo Stopping AI Music Probe...

rem A port check alone is not enough here. Windows lets a second socket bind a port
rem that another process already holds (SO_REUSEADDR hijacks the port instead of
rem failing with EADDRINUSE), so an older server can lose port 8792 to a newer
rem instance and then stay alive holding ~1 GB with nothing listening. Matching only
rem LISTENING pids leaves those orphans behind, so match the command line instead.
rem Only python processes are considered, and only ones running this project's
rem entry point, so unrelated servers (e.g. ComfyUI) are never touched.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*probe.app*' } | ForEach-Object { Write-Host ('  Stopping probe.app (PID ' + $_.ProcessId + ')...'); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

rem Wait for the listening socket to actually go away, so a caller that restarts
rem immediately cannot race the dying process still holding the port.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(10); while((Get-Date) -lt $deadline){ if(-not (Get-NetTCPConnection -LocalPort 8792 -State Listen -ErrorAction SilentlyContinue)){ break }; Start-Sleep -Milliseconds 250 }; if(Get-NetTCPConnection -LocalPort 8792 -State Listen -ErrorAction SilentlyContinue){ Write-Host '  WARNING: port 8792 is still bound by another process.' } else { Write-Host '  Port 8792 is free.' }"

echo Done.
