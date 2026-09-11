# ─────────────────────────────────────────────────────────────────
#  Run Maestro Flow — PowerShell Runner
#
#  Reads test_data.yaml for brand bundle IDs, user creds, and
#  injects them as Maestro --env variables.
#
#  Adopted from the upstream production-sanity suite, run-maestro.ps1
#
#  Usage:
#    .\scripts\run-maestro.ps1 -Flow projects/automation/maestro/flows/brand3/smoke/app-launch.yaml
#    .\scripts\run-maestro.ps1 -Flow projects/automation/maestro/flows/brand3/smoke/ -Brand brand3
#    .\scripts\run-maestro.ps1 -Flow projects/automation/maestro/flows/brand3/guest/pickup-order.yaml -Brand brand3 -Device emulator-5554
# ─────────────────────────────────────────────────────────────────

param(
    [Parameter(Mandatory = $true)]
    [string]$Flow,

    [string]$Device,

    [ValidateSet('brand3', 'Brand One', 'b2', 'Brand Four)]
    [string]$Brand,

    [string]$TestDataPath = "$PSScriptRoot\..\config\test_data.yaml"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $TestDataPath)) {
    throw "test_data.yaml not found at: $TestDataPath"
}

# ── Lightweight YAML value extractor (no external modules) ──
$yamlLines = Get-Content -LiteralPath $TestDataPath

function Get-YamlValue {
    param([string[]]$Lines, [string]$Pattern)
    foreach ($line in $Lines) {
        if ($line -match $Pattern) { return $Matches[1].Trim().Trim('"').Trim("'") }
    }
    return $null
}

function Get-SectionValues {
    param([string[]]$Lines, [string]$SectionHeader)
    $result = @{}; $inSection = $false; $sectionIndent = -1
    foreach ($line in $Lines) {
        if ($line -match "^\s*${SectionHeader}:\s*$") {
            $inSection = $true
            $sectionIndent = ($line -replace '[^ ].*', '').Length
            continue
        }
        if ($inSection) {
            if ($line -match '^\s*$' -or $line -match '^\s*#') { continue }
            $currentIndent = ($line -replace '[^ ].*', '').Length
            if ($currentIndent -le $sectionIndent) { break }
            if ($line -match '^\s+(\w+):\s*"?(.*?)"?\s*$') {
                $result[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $result
}

# ── Brand resolution ──
if (-not $Brand) {
    $Brand = Get-YamlValue $yamlLines '^\s+defaultBrand:\s*"?(.+?)"?\s*$'
    if (-not $Brand) { $Brand = 'brand3' }
}

# ── Bundle ID lookup ──
$bundleId = Get-YamlValue $yamlLines "^\s+${Brand}:\s*""?([a-zA-Z0-9_.]+)""?\s*$"
if (-not $bundleId) {
    $bundleId = Get-YamlValue $yamlLines '^\s+bundleId:\s*"?([a-zA-Z0-9_.]+)"?\s*$'
}
if (-not $bundleId) {
    throw "No Android bundle ID found in test_data.yaml for brand '$Brand'."
}

# ── Extract user data ──
$registered = Get-SectionValues $yamlLines 'registered'
$guest      = Get-SectionValues $yamlLines 'guest'
$visa       = Get-SectionValues $yamlLines 'visa'
$examplecity    = Get-SectionValues $yamlLines 'examplecity'

$authEmail = $registered['email']
$authPass  = $registered['password']

# ── Build env args ──
$envArgs = @(
    '--env', "BUNDLE_ID=$bundleId",
    '--env', "ENGINE_BRAND=$Brand",
    '--env', "AUTH_EMAIL=$authEmail",
    '--env', "AUTH_PASS=$authPass"
)

# Guest info
if ($guest -and $guest['email'])     { $envArgs += @('--env', "GUEST_EMAIL=$($guest['email'])") }
if ($guest -and $guest['phone'])     { $envArgs += @('--env', "GUEST_PHONE=$($guest['phone'])") }
if ($guest -and $guest['firstName']) { $envArgs += @('--env', "GUEST_FIRST_NAME=$($guest['firstName'])") }
if ($guest -and $guest['lastName'])  { $envArgs += @('--env', "GUEST_LAST_NAME=$($guest['lastName'])") }

# Payment card
if ($visa -and $visa['number'])    { $envArgs += @('--env', "TEST_CC_NUMBER=$($visa['number'])") }
if ($visa -and $visa['expiry'])    { $envArgs += @('--env', "TEST_CC_EXPIRY=$($visa['expiry'])") }
if ($visa -and $visa['cvv'])       { $envArgs += @('--env', "TEST_CC_CVV=$($visa['cvv'])") }
if ($visa -and $visa['zip'])       { $envArgs += @('--env', "TEST_CC_ZIP=$($visa['zip'])") }
if ($visa -and $visa['firstName']) { $envArgs += @('--env', "CC_FIRST_NAME=$($visa['firstName'])") }
if ($visa -and $visa['lastName'])  { $envArgs += @('--env', "CC_LAST_NAME=$($visa['lastName'])") }

# Location
if ($examplecity -and $examplecity['zipCode']) { $envArgs += @('--env', "LOCATION_QUERY=$($examplecity['zipCode'])") }
if ($examplecity -and $examplecity['storeId']) { $envArgs += @('--env', "LOCATION_ID=$($examplecity['storeId'])") }

# ── Device args ──
$cmdArgs = @()
if ($Device) {
    $cmdArgs += @('--device', $Device)
}
$cmdArgs += @('test')
$cmdArgs += $envArgs
$cmdArgs += @($Flow)

# ── Execute ──
Write-Host ""
Write-Host "🚀 Maestro Runner" -ForegroundColor Cyan
Write-Host "   Brand:     $Brand" -ForegroundColor DarkGray
Write-Host "   Bundle ID: $bundleId" -ForegroundColor DarkGray
Write-Host "   Flow:      $Flow" -ForegroundColor DarkGray
if ($Device) { Write-Host "   Device:    $Device" -ForegroundColor DarkGray }
Write-Host ""

& maestro @cmdArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ All tests passed!" -ForegroundColor Green
} else {
    Write-Host "`n❌ Some tests failed (exit code: $LASTEXITCODE)" -ForegroundColor Red
}

exit $LASTEXITCODE
