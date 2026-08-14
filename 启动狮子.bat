@echo off
title Desktop Lion Assistant
cd /d "%~dp0"

rem Regenerate the lion cutout if missing. process_lion.ps1 auto-finds the
rem source image (the largest PNG in katong\ other than lion_crop.png).
if not exist "katong\lion_crop.png" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0process_lion.ps1"
)
if not exist "katong\lion_crop.png" (
  echo [ERROR] Failed to generate katong\lion_crop.png.
  echo        Put the source lion PNG in the katong\ folder and retry.
  pause
  exit /b 1
)

rem Launch the watchdog (auto-restarts the pet if it dies unexpectedly), then exit
start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0lion_watchdog.ps1"
exit /b
