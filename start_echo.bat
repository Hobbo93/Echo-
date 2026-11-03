@echo off
title Echo
cd /d "%~dp0"
echo Checking Echo's Python packages...
py -m pip install -q -r requirements.txt
py echo_start.py
timeout /t 10
