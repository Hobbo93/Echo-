@echo off
rem Starts Echo from the folder this file is in. You don't need to copy it anywhere:
rem echo_start.py now adds Echo to Windows start-up by itself (Startup\Echo.bat).
cd /d "%~dp0"
timeout /t 30 /nobreak >nul
py -m pip install -q -r requirements.txt
py echo_start.py --no-browser
