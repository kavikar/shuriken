param(
    [string]$Address = "127.0.0.1",
    [int]$Port = 4723,
    [string]$BasePath = "/",
    [switch]$RelaxedSecurity = $true
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path

if (-not $env:ANDROID_HOME -or [string]::IsNullOrWhiteSpace($env:ANDROID_HOME)) {
    $candidate = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (Test-Path $candidate) {
        $env:ANDROID_HOME = $candidate
    }
}

if ($env:ANDROID_HOME) {
    $platformTools = Join-Path $env:ANDROID_HOME "platform-tools"
    $emulatorTools = Join-Path $env:ANDROID_HOME "emulator"
    $env:PATH = "$platformTools;$emulatorTools;$($env:PATH)"
}

$args = @(
    "--address", $Address,
    "--port", "$Port",
    "--base-path", $BasePath,
    "--log-timestamp"
)

if ($RelaxedSecurity) {
    $args += "--relaxed-security"
}

Write-Host "Starting Appium server at http://$Address`:$Port$BasePath"

if (Test-Path (Join-Path $projectRoot "node_modules\.bin\appium.cmd")) {
    & (Join-Path $projectRoot "node_modules\.bin\appium.cmd") @args
} elseif (Get-Command appium -ErrorAction SilentlyContinue) {
    & appium @args
} else {
    & npx appium @args
}
