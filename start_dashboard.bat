@echo off
title Racing Dashboard
cd /d "%~dp0"
python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul && goto python
py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul && goto py
echo.
echo   Python 3.12 or newer was not found.
echo   Double-click install.bat in this folder to set everything up.
echo.
pause
exit /b 1
:python
python core\server.py
goto end
:py
py -3 core\server.py
:end
if errorlevel 1 pause
