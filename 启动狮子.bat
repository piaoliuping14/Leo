@echo off
title Desktop Lion Assistant
cd /d "%~dp0"

rem Launch the watchdog (auto-restarts the pet if it dies unexpectedly), then exit
start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0lion_watchdog.ps1"
exit /b
