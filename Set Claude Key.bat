@echo off
title Echo - Turn on Claude
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
py set_claude_key.py
echo.
pause
