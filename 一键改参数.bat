@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo.
echo ============================================================
echo   Step 5 - revise the design with one sentence
echo ============================================================
echo.

python scripts\revise.py --interactive

echo.
echo ============================================================
echo.
pause
