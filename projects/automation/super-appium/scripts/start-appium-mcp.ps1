param(
    [switch]$NoUi,
    [string]$CapabilitiesConfig = "",
    [string]$AndroidHome = ""
)

$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($AndroidHome)) {
    $env:ANDROID_HOME = $AndroidHome
}

if (-not $env:ANDROID_HOME -or [string]::IsNullOrWhiteSpace($env:ANDROID_HOME)) {
    $candidate = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (Test-Path $candidate) {
        $env:ANDROID_HOME = $candidate
    }
}

if ($NoUi) {
    $env:NO_UI = "true"
}

if (-not [string]::IsNullOrWhiteSpace($CapabilitiesConfig)) {
    $env:CAPABILITIES_CONFIG = $CapabilitiesConfig
}

Write-Host "Starting appium-mcp with ANDROID_HOME=$($env:ANDROID_HOME)"
if ($env:NO_UI -eq "true") {
    Write-Host "NO_UI mode enabled"
}
if ($env:CAPABILITIES_CONFIG) {
    Write-Host "CAPABILITIES_CONFIG=$($env:CAPABILITIES_CONFIG)"
}

& npx -y appium-mcp@latest
