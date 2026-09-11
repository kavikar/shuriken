param(
    [ValidateSet("brand3", "Brand One", "b2", "Brand Four")]
    [string]$Brand = "brand3",

    [ValidateSet("qa", "enterpriseqa", "uat", "enterpriseuat", "prod", "demo")]
    [string]$Env = "uat",

    [ValidateSet("android", "ios")]
    [string]$Platform = "android",

    [string]$SourceRoot = "profiles"
)

$ErrorActionPreference = "Stop"

$runtimeDir = "artifacts/runtime"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$profilePath = "$runtimeDir/$Brand.$Env.profile.json"
$resolvedProfilePath = node ./scripts/sync-brand-profile.js --brand $Brand --env $Env --sourceRoot $SourceRoot --out $profilePath
if (-not (Test-Path $resolvedProfilePath)) {
    throw "Failed to generate runtime profile"
}

$profile = Get-Content -Raw $resolvedProfilePath | ConvertFrom-Json

$bundleId = if ($Platform -eq "android") { $profile.app.androidBundleId } else { $profile.app.iosBundleId }
if (-not $bundleId) {
    throw "Missing bundle ID for platform $Platform in runtime profile"
}

$capabilities = if ($Platform -eq "android") {
    @{
        platformName = "Android"
        "appium:automationName" = "UiAutomator2"
        "appium:deviceName" = "Android Device"
        "appium:appPackage" = $bundleId
        "appium:newCommandTimeout" = 180
        "appium:noReset" = $true
    }
} else {
    @{
        platformName = "iOS"
        "appium:automationName" = "XCUITest"
        "appium:deviceName" = "iPhone Simulator"
        "appium:bundleId" = $bundleId
        "appium:newCommandTimeout" = 180
        "appium:noReset" = $true
    }
}

$capPath = "$runtimeDir/$Brand.$Env.$Platform.capabilities.json"
@{ ($Platform) = $capabilities } | ConvertTo-Json -Depth 8 | Set-Content -NoNewline -Path $capPath

$prompt = @"
You are executing a mobile smoke run using appium-mcp.

Target:
- Brand: $Brand
- Environment: $Env
- Platform: $Platform
- Bundle ID: $bundleId
- API Endpoint: $($profile.endpoints.apiEndpoint)

Execution policy:
1. Create session with capability preset from CAPABILITIES_CONFIG.
2. Capture screenshot at launch, home ready, and pre-exit checkpoints.
3. Validate app launches and lands on a stable home state.
4. If blocking modal appears, dismiss and continue.
5. Record failures with screenshot path and concise root cause.

Expected output:
- SUMMARY: PASS | FAIL | BLOCKED
- EVIDENCE: screenshot file paths
- RESULT: validations performed
- ISSUE: blocker/failure details
"@

$promptPath = "$runtimeDir/$Brand.$Env.$Platform.smoke.prompt.txt"
Set-Content -Path $promptPath -Value $prompt

Write-Host "Runtime profile: $resolvedProfilePath"
Write-Host "Capabilities: $capPath"
Write-Host "Prompt: $promptPath"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1) npm run appium:server"
Write-Host "2) npm run appium:mcp:no-ui -- -CapabilitiesConfig $capPath"
Write-Host "3) Use your MCP client with mcp.config.json and run the generated prompt"
