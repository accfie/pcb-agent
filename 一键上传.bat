@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set REPO=https://github.com/accfie/pcb-agent.git

where git >nul 2>&1
if not errorlevel 1 goto git_ok
echo.
echo   [ERROR] Git is not installed on this computer.
echo.
echo   Install it first, takes about 5 minutes:
echo   https://git-scm.com/download/win
echo.
echo   Just keep clicking Next, all defaults are fine.
echo.
pause
exit /b 1
:git_ok

echo.
echo ============================================================
echo   Upload project to GitHub
echo ============================================================
echo   Target repo: %REPO%
echo.

for /f "delims=" %%i in ('git config user.name 2^>nul') do set NAME=%%i
for /f "delims=" %%i in ('git config user.email 2^>nul') do set EMAIL=%%i

if not "%NAME%"=="" goto have_name
echo   First time setup. Type your name, it shows up in the commit history.
set /p NAME=  Your name: 
git config --global user.name "!NAME!"
:have_name

if not "%EMAIL%"=="" goto have_email
set /p EMAIL=  Your email: 
git config --global user.email "!EMAIL!"
:have_email

echo.
echo   Author: %NAME% / %EMAIL%
echo.

git remote get-url origin >nul 2>&1
if errorlevel 1 goto add_remote
git remote set-url origin %REPO%
goto remote_done
:add_remote
git remote add origin %REPO%
:remote_done
echo   Remote ready.
echo.

git add -A
git commit -m "W1-W6: scaffold, offline pipeline, netlist to kicad sch, verify passed" >nul 2>&1
if errorlevel 1 echo   Nothing new to commit, already up to date.
if not errorlevel 1 echo   Commit created.
echo.

git branch -M main
echo   Pushing now. If a browser window opens, sign in to GitHub and click Authorize.
echo.
git push -u origin main

echo.
if errorlevel 1 echo   PUSH FAILED - read the message above for the reason.
if not errorlevel 1 echo   DONE. Your repo: https://github.com/accfie/pcb-agent

echo.
echo ============================================================
echo.
pause
