@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

echo.
echo ============================================================
echo   Step 5 - revise the design with one sentence
echo ============================================================
echo.

%PY% scripts\revise.py --interactive

echo.
echo ============================================================
echo.
pause
