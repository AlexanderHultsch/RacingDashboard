@echo off
title Racing Dashboard
cd /d "%~dp0"
python -c "" >nul 2>nul
if errorlevel 1 (
    py -3 core\server.py
) else (
    python core\server.py
)
if errorlevel 1 pause
