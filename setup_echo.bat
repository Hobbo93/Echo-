@echo off
title Echo Setup
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Get it from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Installing Echo requirements...
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Could not install requirements.
  pause
  exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed. Get it from https://ollama.com then run this again.
) else (
  echo Downloading the AI model. This can take a while...
  ollama pull llama3.2
)

echo.
py echo_setup.py
echo.
echo Checking everything...
py echo_preflight.py
echo.
echo Setup finished. Double-click start_echo.bat to run Echo.
pause
