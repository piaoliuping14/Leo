@echo off
title 桌宠管理
cd /d "%~dp0"

rem Launch the pet manager (GUI), then exit
if exist "C:\Python314\pythonw.exe" (
  start "" "C:\Python314\pythonw.exe" "%~dp0lion_manager.py"
) else (
  start "" pythonw.exe "%~dp0lion_manager.py"
)
exit /b
