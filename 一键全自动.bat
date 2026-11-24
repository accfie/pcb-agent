@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

echo.
echo ============================================================
echo   FULL AUTO  -  one sentence to schematic, no copy-paste
echo ============================================================
echo.

%PY% scripts\auto_run.py --check
if errorlevel 1 goto failed

echo.
set /p REQ=  Type your requirement, or press Enter for the default: 
if "%REQ%"=="" goto default_run

%PY% scripts\auto_run.py "%REQ%"
goto done

:default_run
%PY% scripts\auto_run.py
goto done

:failed
echo.
echo   Model endpoint is not ready. Read the message above.
echo   Guide: docs\auto-mode.md

:done
echo.
echo ============================================================
start "" "%~dp0out\auto"
echo.
pause
