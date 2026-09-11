@echo off
echo =====================================================
echo   Menu Delta Analyzer  -  Multi-Brand (B2/B1/B3)
echo =====================================================
cd /d "%~dp0"

:: Install deps if needed
pip install -r requirements.txt --quiet

:: Ensure report dirs exist
mkdir reports\B2 2>nul
mkdir reports\B1 2>nul
mkdir reports\B3 2>nul

:: Start Flask server in a new window so it keeps running
echo Starting Flask server...
start "Menu Delta Analyzer - Server" python app.py

:: Poll until the server responds (up to 20 seconds), then open browser
echo Waiting for server to be ready...
powershell -NoProfile -Command ^
  "$ready = $false; for ($i = 0; $i -lt 20; $i++) { Start-Sleep -Seconds 1; try { Invoke-WebRequest -Uri 'http://localhost:5000' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null; $ready = $true; break } catch {} }; if ($ready) { Start-Process 'http://localhost:5000'; Write-Host 'Browser opened at http://localhost:5000' } else { Write-Host 'ERROR: Server did not start within 20 seconds. Check the Flask window for errors.' }"

pause
