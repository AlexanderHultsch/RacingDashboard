@echo off
rem Racing Dashboard installer: sets up Python, firewall and shortcuts. Run it again to repair.
title Racing Dashboard - installer
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" %*
echo.
pause
