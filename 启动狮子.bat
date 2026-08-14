@echo off
title Desktop Lion Assistant
cd /d "%~dp0"

rem Launch the watchdog (auto-restarts the pet if it dies), then exit
if exist "C:\Python314\pythonw.exe" (
  start "" /min "C:\Python314\pythonw.exe" "%~dp0lion_watchdog.py"
) else (
  start "" /min pythonw.exe "%~dp0lion_watchdog.py"
)
exit /b
