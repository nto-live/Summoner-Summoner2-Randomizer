@echo off
rem Summoner Randomizer - desktop app. Double-click to launch.
rem Takes an ISO, randomizes what you tick, returns a new ISO, and shows the seed.
rem No server, no browser. Bring your own disc; nothing is uploaded.
setlocal
cd /d "%~dp0"

set EXE=%~dp0publish\SummonerRando.exe
if not exist "%EXE%" set EXE=%~dp0SummonerRando.Desktop\bin\Release\net8.0-windows\SummonerRando.exe
if not exist "%EXE%" set EXE=%~dp0SummonerRando.exe

if not exist "%EXE%" (
  echo The app is not built yet. Build it first:
  echo     dotnet build -c Release
  echo   or publish the portable bundle:
  echo     powershell -File ..\package-portable.ps1
  pause
  exit /b 1
)

rem A frozen engine (summoner-engine.exe) means no Python is needed at all - that is how the
rem portable build ships. Only ask for Python when the app is expected to run cli.py.
set FROZEN=%~dp0summoner-engine.exe
if exist "%FROZEN%" goto run

where python >nul 2>nul
if errorlevel 1 (
  echo No engine found next to the app, and Python 3 is not on PATH.
  echo Either ship summoner-engine.exe alongside SummonerRando.exe ^(see desktop\PACKAGING.md^)
  echo or install Python 3.13.
  pause
  exit /b 1
)

:run
start "" "%EXE%" %*
