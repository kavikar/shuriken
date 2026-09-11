@echo off
cd /d "%~dp0"
start "" /B python api_server.py
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5000/"
