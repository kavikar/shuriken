param(
    [ValidateSet("brand3", "Brand One", "b2", "Brand Four")]
    [string]$Brand = "brand3",

    [ValidateSet("qa", "enterpriseqa", "uat", "enterpriseuat", "prod", "demo")]
    [string]$Env = "uat",

    [ValidateSet("android", "ios")]
    [string]$Platform = "android",

    [string]$Suite = "smoke"
)

$ErrorActionPreference = "Stop"

$planPath = "plans/$Brand.$Suite.json"
if (-not (Test-Path $planPath)) {
    throw "Suite plan not found: $planPath"
}

npm run smoke:agentic -- -Brand $Brand -Env $Env -Platform $Platform | Out-Host

$profilePath = "artifacts/runtime/$Brand.$Env.profile.json"
if (-not (Test-Path $profilePath)) {
    throw "Expected profile not found: $profilePath"
}

$manifestPath = node ./scripts/generate-suite-artifacts.js --plan $planPath --profile $profilePath --out artifacts/runtime/suites
if (-not (Test-Path $manifestPath)) {
    throw "Failed to generate suite manifest"
}

Write-Host "Suite manifest: $manifestPath"
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
Write-Host "Combined prompt: $($manifest.consolidatedPath)"
Write-Host "Tests in pack: $($manifest.tests.Count)"
