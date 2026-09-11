$ErrorActionPreference = "Continue"

Write-Host "super-appium doctor: checking prerequisites"
$failed = 0

function Check-Command {
    param(
        [string]$Name,
        [string]$Hint
    )

    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Host "[OK] $Name"
    } else {
        Write-Host "[MISSING] $Name"
        if ($Hint) { Write-Host "  -> $Hint" }
        $script:failed++
    }
}

Check-Command -Name "node" -Hint "Install Node.js 20+"
Check-Command -Name "npm" -Hint "Install npm"
Check-Command -Name "npx" -Hint "Install npx"
Check-Command -Name "java" -Hint "Install JDK 17+"

$adbPath = ""
if (Get-Command adb -ErrorAction SilentlyContinue) {
    $adbPath = "adb"
} else {
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:ANDROID_HOME)) {
        $candidates += (Join-Path $env:ANDROID_HOME "platform-tools\adb.exe")
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe")
    }
    $hits = @($candidates | Where-Object { Test-Path $_ })
    if ($hits.Count -gt 0) {
        $adbPath = $hits[0]
    }
}

if ([string]::IsNullOrWhiteSpace($adbPath)) {
    Write-Host "[MISSING] adb"
    Write-Host "  -> Install Android platform-tools and set ANDROID_HOME"
    $failed++
} else {
    Write-Host "[OK] adb ($adbPath)"
    & $adbPath devices | Out-Host
}

if (Get-Command appium -ErrorAction SilentlyContinue) {
    Write-Host "[OK] appium"
} elseif (Test-Path ".\node_modules\.bin\appium.cmd") {
    Write-Host "[OK] appium (local node_modules)"
} else {
    Write-Host "[MISSING] appium"
    Write-Host "  -> Run npm install in this folder"
    $failed++
}

if ($failed -gt 0) {
    Write-Host "doctor result: FAILED ($failed issue(s))"
    exit 1
}

Write-Host "doctor result: PASS"
exit 0
