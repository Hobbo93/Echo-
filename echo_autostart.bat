@echo off
rem Starts Echo when Windows starts (put a copy of this file in your Startup folder).
cd /d "C:\Users\tailen\Downloads\Echo_fresh_test"
timeout /t 30 /nobreak >nul
py -m pip install -q -r requirements.txt
py echo_start.py --no-browser
