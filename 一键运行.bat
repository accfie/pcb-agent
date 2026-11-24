@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo.
echo ============================================================
echo   AI Agent PCB Board  -  offline pipeline
echo ============================================================
echo.

python scripts\offline_run.py

echo.
echo ============================================================
echo   Finished. Opening the output folder...
echo ============================================================
start "" "%~dp0out\offline"

echo Close this window when you are done.
pause >nul
