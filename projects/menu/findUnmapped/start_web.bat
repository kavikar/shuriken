@echo off
setlocal
cd /d %~dp0

echo Installing dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 goto :err

echo Starting findUnmapped web server on http://localhost:5100 ...
py web_server.py
goto :eof

:err
echo Failed to install dependencies.
exit /b 1
