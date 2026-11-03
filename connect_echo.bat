@echo off
title Connect Echo to your apps
cd /d "%~dp0"
echo CONNECT ECHO
echo Shopify, Alpaca trading, Gmail, Google Places and phone calls.
echo Press Enter to skip anything. Keys stay on this PC only.
echo.
py echo_setup.py --connect
echo.
echo Restart Echo (close its windows, then start_echo.bat) so every office picks up the new connections.
pause
