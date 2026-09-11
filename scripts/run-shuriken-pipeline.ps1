<#
.SYNOPSIS
  Shuriken — Local CI/CD Pipeline Runner
  Runs the full pipeline locally: Smoke Tests → Confluence Report → Teams/Outlook Notification

.DESCRIPTION
  Simulates the GitLab CI pipeline on your local machine.
  1. Runs Maestro smoke suite for specified brand(s) on local emulator
  2. Parses JUnit XML results into summary JSON
  3. Publishes branded report to Confluence
  4. Sends Teams Adaptive Card + Outlook notification with Confluence link

.PARAMETER Brand
  Brand(s) to test: brand3, Brand One, b2, or "all" (default: all)

.PARAMETER BuildVersion
  Build version label (default: "local-<timestamp>")

.PARAMETER SkipTests
  Skip test execution and use existing results in test-results/

.PARAMETER SkipConfluence
  Skip Confluence report publishing

.PARAMETER SkipNotify
  Skip Teams/Outlook notifications

.EXAMPLE
  .\scripts\run-shuriken-pipeline.ps1 -Brand brand3
  .\scripts\run-shuriken-pipeline.ps1 -Brand all -BuildVersion "4.2.1-rc.3"
  .\scripts\run-shuriken-pipeline.ps1 -SkipTests  # Re-publish from existing results
#>

param(
    [string]$Brand = "all",
    [string]$BuildVersion = "",
    [switch]$SkipTests,
    [switch]$SkipConfluence,
    [switch]$SkipNotify
)

# ─── Config ───────────────────────────────────────────────────
$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
# Override with $env:MAESTRO_BIN; falls back to whatever is on PATH.
$MaestroBin = if ($env:MAESTRO_BIN) { $env:MAESTRO_BIN } else { "maestro" }
$TestResultsDir = Join-Path $ProjectRoot "test-results"
$ScreenshotsDir = Join-Path $ProjectRoot "screenshots"
$CiScripts = Join-Path $ProjectRoot "scripts\ci"

# Environment variables (set these or they'll be prompted)
$env:CONFLUENCE_BASE_URL   = if ($env:CONFLUENCE_BASE_URL)   { $env:CONFLUENCE_BASE_URL }   else { "https://your-tenant.atlassian.net/wiki" }
$env:CONFLUENCE_SPACE_KEY  = if ($env:CONFLUENCE_SPACE_KEY)  { $env:CONFLUENCE_SPACE_KEY }  else { "QE" }
# These must be set before running:
# $env:CONFLUENCE_EMAIL       = "user@example.com"
# $env:CONFLUENCE_API_TOKEN   = "your-api-token"
# $env:TEAMS_WEBHOOK_URL      = "https://outlook.office.com/webhook/..."
# $env:OUTLOOK_WEBHOOK_URL    = "https://..."  (optional)

# ─── Setup ────────────────────────────────────────────────────
if (-not $BuildVersion) {
    $BuildVersion = "local-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}

$Brands = if ($Brand -eq "all") { @("brand3", "Brand One", "b2") } else { @($Brand) }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   🍽️  Shuriken — Local Pipeline Runner                     ║" -ForegroundColor Cyan
Write-Host "║   Predictive Lifecycle Assurance & Testing Engine       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Build Version : $BuildVersion" -ForegroundColor White
Write-Host "  Brand(s)      : $($Brands -join ', ')" -ForegroundColor White
Write-Host "  Skip Tests    : $SkipTests" -ForegroundColor White
Write-Host "  Skip Confluence: $SkipConfluence" -ForegroundColor White
Write-Host "  Skip Notify   : $SkipNotify" -ForegroundColor White
Write-Host ""

# Ensure directories exist
New-Item -ItemType Directory -Path $TestResultsDir -Force | Out-Null
New-Item -ItemType Directory -Path $ScreenshotsDir -Force | Out-Null

# ═══════════════════════════════════════════════════════════════
#  STAGE 1: Run Smoke Tests
# ═══════════════════════════════════════════════════════════════
$TestResults = @()

if (-not $SkipTests) {
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  ② RUNNING SMOKE TESTS ON LOCAL EMULATOR" -ForegroundColor Yellow
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""

    # Verify emulator is running
    $adbDevices = adb devices 2>&1
    if ($adbDevices -notmatch "emulator-\d+\s+device") {
        Write-Host "  ❌ No Android emulator detected! Start one first." -ForegroundColor Red
        Write-Host "     Run: emulator -avd Medium_Phone_API_36" -ForegroundColor Gray
        exit 1
    }
    Write-Host "  ✅ Emulator detected" -ForegroundColor Green

    # Load test data for env vars
    $TestDataPath = Join-Path $ProjectRoot "config\test_data.yaml"

    foreach ($b in $Brands) {
        Write-Host ""
        Write-Host "  ┌─────────────────────────────────────────────" -ForegroundColor Cyan
        Write-Host "  │ 🧪 $($b.ToUpper()) Smoke Suite" -ForegroundColor Cyan
        Write-Host "  └─────────────────────────────────────────────" -ForegroundColor Cyan

        $FlowDir = Join-Path $ProjectRoot "flows\$b\smoke"
        if (-not (Test-Path $FlowDir)) {
            Write-Host "    ⚠️  No smoke flows found at $FlowDir" -ForegroundColor Yellow
            continue
        }

        # Parse bundle ID from test_data.yaml
        $bundleId = python -c "import yaml; data=yaml.safe_load(open('$($TestDataPath -replace '\\','/')')); print(data['$b']['bundleId'])" 2>$null
        $zipCode  = python -c "import yaml; data=yaml.safe_load(open('$($TestDataPath -replace '\\','/')')); print(data['$b']['testLocations']['default']['zipCode'])" 2>$null
        $storeId  = python -c "import yaml; data=yaml.safe_load(open('$($TestDataPath -replace '\\','/')')); print(data['$b']['testLocations']['default']['storeId'])" 2>$null

        Write-Host "    Bundle: $bundleId | Zip: $zipCode | Store: $storeId" -ForegroundColor Gray

        $junitFile = Join-Path $TestResultsDir "$b-smoke.xml"

        # Run each smoke flow individually to capture pass/fail
        $FlowFiles = Get-ChildItem $FlowDir -Filter "*.yaml" | Sort-Object Name
        $brandPassed = 0
        $brandFailed = 0
        $brandStart = Get-Date

        foreach ($flow in $FlowFiles) {
            $flowName = $flow.BaseName
            Write-Host "    ▶ $flowName ... " -NoNewline

            $flowStart = Get-Date
            $result = & $MaestroBin test $flow.FullName `
                --env "BUNDLE_ID=$bundleId" `
                --env "LOCATION_ZIP=$zipCode" `
                --env "LOCATION_ID=$storeId" `
                --format junit `
                --output (Join-Path $TestResultsDir "$b-$flowName.xml") 2>&1

            $exitCode = $LASTEXITCODE
            $flowDuration = ((Get-Date) - $flowStart).TotalSeconds

            if ($exitCode -eq 0) {
                Write-Host "✅ PASSED ($([math]::Round($flowDuration,1))s)" -ForegroundColor Green
                $brandPassed++
            } else {
                Write-Host "❌ FAILED ($([math]::Round($flowDuration,1))s)" -ForegroundColor Red
                $brandFailed++
            }
        }

        $brandDuration = ((Get-Date) - $brandStart).TotalSeconds
        $brandStatus = if ($brandFailed -eq 0) { "passed" } else { "failed" }

        $TestResults += [PSCustomObject]@{
            Brand    = $b
            Total    = $brandPassed + $brandFailed
            Passed   = $brandPassed
            Failed   = $brandFailed
            Duration = [math]::Round($brandDuration, 1)
            Status   = $brandStatus
        }

        Write-Host "    ─────────────────────────────────────────────" -ForegroundColor Gray
        $icon = if ($brandFailed -eq 0) { "✅" } else { "❌" }
        Write-Host "    $icon $($b.ToUpper()): $brandPassed/$($brandPassed + $brandFailed) passed ($([math]::Round($brandDuration,1))s)" -ForegroundColor $(if ($brandFailed -eq 0) { "Green" } else { "Red" })
    }

    # Generate summary JSONs using CI script
    Write-Host ""
    Write-Host "  📊 Generating result summaries..." -ForegroundColor Cyan
    foreach ($b in $Brands) {
        $xmlFiles = Get-ChildItem $TestResultsDir -Filter "$b-*.xml" -ErrorAction SilentlyContinue
        if ($xmlFiles) {
            # Merge XMLs or use the first one
            $firstXml = $xmlFiles[0].FullName
            python (Join-Path $CiScripts "parse-junit-results.py") `
                --input $firstXml `
                --brand $b `
                --version $BuildVersion `
                --output (Join-Path $TestResultsDir "$b-summary.json") 2>$null
        }
    }
} else {
    Write-Host "  ⏭️  Skipping tests — using existing results in test-results/" -ForegroundColor Yellow
}

# ═══════════════════════════════════════════════════════════════
#  STAGE 2: Print Results Summary
# ═══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  📊 RESULTS SUMMARY" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""

if ($TestResults.Count -gt 0) {
    Write-Host "  Brand     Status   Total  Pass  Fail  Duration" -ForegroundColor White
    Write-Host "  ────────  ───────  ─────  ────  ────  ────────" -ForegroundColor Gray

    foreach ($r in $TestResults) {
        $icon = if ($r.Status -eq "passed") { "✅" } else { "❌" }
        $color = if ($r.Status -eq "passed") { "Green" } else { "Red" }
        Write-Host ("  {0,-9} {1}  {2,-5}  {3,-4}  {4,-4}  {5}s" -f $r.Brand.ToUpper(), $icon, $r.Total, $r.Passed, $r.Failed, $r.Duration) -ForegroundColor $color
    }

    $totalAll = ($TestResults | Measure-Object -Property Total -Sum).Sum
    $passedAll = ($TestResults | Measure-Object -Property Passed -Sum).Sum
    $failedAll = ($TestResults | Measure-Object -Property Failed -Sum).Sum
    Write-Host "  ────────  ───────  ─────  ────  ────  ────────" -ForegroundColor Gray
    $overallIcon = if ($failedAll -eq 0) { "✅" } else { "❌" }
    Write-Host ("  {0,-9} {1}  {2,-5}  {3,-4}  {4,-4}" -f "TOTAL", $overallIcon, $totalAll, $passedAll, $failedAll) -ForegroundColor $(if ($failedAll -eq 0) { "Green" } else { "Red" })
}

# ═══════════════════════════════════════════════════════════════
#  STAGE 3: Publish to Confluence
# ═══════════════════════════════════════════════════════════════
$ConfluenceUrl = ""

if (-not $SkipConfluence) {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  ③ PUBLISHING REPORT TO CONFLUENCE" -ForegroundColor Yellow
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""

    if (-not $env:CONFLUENCE_EMAIL -or -not $env:CONFLUENCE_API_TOKEN) {
        Write-Host "  ⚠️  CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN not set." -ForegroundColor Yellow
        Write-Host "  Set them as environment variables:" -ForegroundColor Gray
        Write-Host '    $env:CONFLUENCE_EMAIL = "user@example.com"' -ForegroundColor Gray
        Write-Host '    $env:CONFLUENCE_API_TOKEN = "your-token"' -ForegroundColor Gray
        Write-Host "  Skipping Confluence publish." -ForegroundColor Yellow
    } else {
        $confluenceResult = Join-Path $TestResultsDir "confluence-result.json"
        python (Join-Path $CiScripts "publish-confluence-report.py") `
            --results-dir $TestResultsDir `
            --screenshots-dir $ScreenshotsDir `
            --space-key $env:CONFLUENCE_SPACE_KEY `
            --parent-page-id "$($env:CONFLUENCE_PARENT_PAGE_ID)" `
            --base-url $env:CONFLUENCE_BASE_URL `
            --email $env:CONFLUENCE_EMAIL `
            --api-token $env:CONFLUENCE_API_TOKEN `
            --build-version $BuildVersion `
            --pipeline-url "local-run" `
            --output $confluenceResult

        if (Test-Path $confluenceResult) {
            $confluenceData = Get-Content $confluenceResult | ConvertFrom-Json
            $ConfluenceUrl = $confluenceData.url
            Write-Host "  ✅ Report published: $ConfluenceUrl" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Failed to publish Confluence report" -ForegroundColor Red
        }
    }
} else {
    Write-Host ""
    Write-Host "  ⏭️  Skipping Confluence publish" -ForegroundColor Yellow
}

# ═══════════════════════════════════════════════════════════════
#  STAGE 4: Notify Teams & Outlook
# ═══════════════════════════════════════════════════════════════
if (-not $SkipNotify) {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  ④ SENDING NOTIFICATIONS" -ForegroundColor Yellow
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""

    if (-not $env:TEAMS_WEBHOOK_URL) {
        Write-Host "  ⚠️  TEAMS_WEBHOOK_URL not set." -ForegroundColor Yellow
        Write-Host '    $env:TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook/..."' -ForegroundColor Gray
        Write-Host "  Skipping notifications." -ForegroundColor Yellow
    } else {
        $notifyConfUrl = if ($ConfluenceUrl) { $ConfluenceUrl } else { "https://your-tenant.atlassian.net/wiki" }
        python (Join-Path $CiScripts "notify.py") `
            --confluence-url $notifyConfUrl `
            --teams-webhook $env:TEAMS_WEBHOOK_URL `
            --outlook-webhook "$($env:OUTLOOK_WEBHOOK_URL)" `
            --brand $Brand `
            --build-version $BuildVersion `
            --pipeline-url "local-run" `
            --results-dir $TestResultsDir
    }
} else {
    Write-Host ""
    Write-Host "  ⏭️  Skipping notifications" -ForegroundColor Yellow
}

# ═══════════════════════════════════════════════════════════════
#  DONE
# ═══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   🍽️  Shuriken Pipeline Complete!                          ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
if ($ConfluenceUrl) {
    Write-Host "  📝 Confluence: $ConfluenceUrl" -ForegroundColor Cyan
}
Write-Host "  📁 Results:    $TestResultsDir" -ForegroundColor White
Write-Host "  📸 Screenshots: $ScreenshotsDir" -ForegroundColor White
Write-Host ""
