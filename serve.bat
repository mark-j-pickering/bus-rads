@echo off
rem Serve the Bus RADS site locally and open it in the browser.
rem Double-click this file, or run it from any folder. Close the window (or Ctrl+C) to stop.
setlocal
cd /d "%~dp0"

set PORT=8765
set PY=.venv\Scripts\python.exe

if not exist "%PY%" (
  echo No Python environment found. Set it up once with:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "site\data\index.json" (
  echo No map data yet. Building it from the GTFS feed in gtfs\ ...
  "%PY%" -m busrads build || (pause & exit /b 1)
)

echo Serving http://127.0.0.1:%PORT%/  -  close this window to stop.
start "" "http://127.0.0.1:%PORT%/"
"%PY%" tools\serve.py %PORT%
