# ─────────────────────────────────────────────────────────────────
#  Record Maestro Test Execution
#
#  Starts ADB screen recording in the background, runs the
#  Maestro flow, then pulls the recording to local disk.
#
#  Usage:
#    .\scripts\record-test.ps1 -Flow projects/automation/maestro/flows/brand3/smoke/app-launch.yaml
#    .\scripts\record-test.ps1 -Flow projects/automation/maestro/flows/brand3/guest/pickup-order.yaml -MaxSeconds 180
#
#  Output:
#    recordings/<flow-name>_<timestamp>.mp4
#
#  Notes:
#    - ADB screenrecord max is 180 seconds per file (Android limit)
#    - Overhead is ~3-5% — negligible impact on test speed
#    - Recording runs on the device GPU, not CPU
# ─────────────────────────────────────────────────────────────────

param(
    [Parameter(Mandatory = $true)]
    [string]$Flow,

    [int]$MaxSeconds = 180,

    [string]$OutputDir = ".\recordings"
)

$ErrorActionPreference = 'Stop'

# Ensure output dir exists
if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Generate filename from flow path
$flowName = [System.IO.Path]::GetFileNameWithoutExtension($Flow) -replace '[/\\]', '_'
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$devicePath = "/sdcard/maestro_recording.mp4"
$localFile = "$OutputDir/${flowName}_${timestamp}.mp4"

Write-Host ""
Write-Host "[REC] Recording Maestro test execution" -ForegroundColor Cyan
Write-Host "   Flow:       $Flow" -ForegroundColor DarkGray
Write-Host "   Max time:   ${MaxSeconds}s" -ForegroundColor DarkGray
Write-Host "   Output:     $localFile" -ForegroundColor DarkGray
Write-Host ""

# ── Start screen recording in background ──
Write-Host "[REC] Starting screen recording..." -ForegroundColor Yellow
$recordJob = Start-Job -ScriptBlock {
    param($devicePath, $maxSec)
    & adb shell screenrecord --time-limit $maxSec $devicePath 2>&1
} -ArgumentList $devicePath, $MaxSeconds

# Give recording a moment to start
Start-Sleep -Seconds 1

# ── Run the Maestro test ──
Write-Host "[RUN] Running Maestro test..." -ForegroundColor Green
Write-Host ""

$testStart = Get-Date
& maestro test $Flow
$exitCode = $LASTEXITCODE
$testDuration = [math]::Round(((Get-Date) - $testStart).TotalSeconds, 1)

Write-Host ""

# ── Stop recording ──
Write-Host "[STOP] Stopping recording..." -ForegroundColor Yellow
adb shell "pkill -INT screenrecord" 2>$null
Start-Sleep -Seconds 2

# Stop the background job
Stop-Job $recordJob -ErrorAction SilentlyContinue
Remove-Job $recordJob -ErrorAction SilentlyContinue

# ── Pull recording to local machine ──
Write-Host "[PULL] Pulling recording from device..." -ForegroundColor Yellow
adb pull $devicePath $localFile 2>$null

# Clean up device
adb shell rm $devicePath 2>$null

if (Test-Path $localFile) {
    $sizeMB = [math]::Round((Get-Item $localFile).Length / 1MB, 1)
    Write-Host ""
    Write-Host "[OK] Recording saved: $localFile ($sizeMB MB)" -ForegroundColor Green
    Write-Host "   Test duration: ${testDuration}s" -ForegroundColor DarkGray
    Write-Host "   Test result:   $(if ($exitCode -eq 0) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($exitCode -eq 0) { 'Green' } else { 'Red' })
} else {
    Write-Host "[WARN] Recording file not found - device may not support screenrecord" -ForegroundColor Yellow
}

exit $exitCode
