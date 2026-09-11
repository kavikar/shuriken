@echo off
setlocal
cd /d %~dp0

py -m pip install -r requirements.txt
if errorlevel 1 goto :err

py interactive.py
goto :eof

:err
echo Failed to install dependencies.
exit /b 1
