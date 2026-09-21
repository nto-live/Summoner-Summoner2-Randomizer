@echo off
rem Summoner Randomizer — double-click to start.
rem Opens the tool in your browser. Bring your own disc; nothing is uploaded.
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required and was not found on PATH.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8091/
python app.py %*
if errorlevel 1 pause
