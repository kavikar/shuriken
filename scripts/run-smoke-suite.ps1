# ─────────────────────────────────────────────────────────────────
#  run-smoke-suite.ps1 - Multi-Brand Smoke Suite Runner
#
#  Runs smoke tests for Brand Three, Brand One, and B2 (or a single brand).
#  Generates a summary report with pass/fail counts.
#
#  Usage:
#    .\scripts\run-smoke-suite.ps1                     # All 3 brands
#    .\scripts\run-smoke-suite.ps1 -Brand brand3        # Brand Three only
#    .\scripts\run-smoke-suite.ps1 -Brand Brand One        # Brand One only
#    .\scripts\run-smoke-suite.ps1 -Brand b2          # B2 only
#    .\scripts\run-smoke-suite.ps1 -Tests app-launch   # One test, all brands
# ─────────────────────────────────────────────────────────────────

param(
    [ValidateSet("all", "brand3", "Brand One", "b2")]
    [string]$Brand = "all",

    [ValidateSet("all", "app-launch", "store-search", "tab-navigation", "browse-menu")]
    [string]$Tests = "all"
)

$ErrorActionPreference = "Continue"
# Override with $env:MAESTRO_BIN; falls back to whatever is on PATH.
$MaestroBin = if ($env:MAESTRO_BIN) { $env:MAESTRO_BIN } else { "maestro" }

# ── Brand Configuration ──
$brands = @{
    brand3 = @{
        name      = "Brand Three"
        folder    = "projects/automation/maestro/flows/brand3/smoke"
        bundleId  = "com.example.brand3.uat"
    }
    Brand One = @{
        name      = "Brand One"
        folder    = "projects/automation/maestro/flows/brand1/smoke"
        bundleId  = "com.example.brand1.uat"
    }
    b2   = @{
        name      = "B2"
        folder    = "projects/automation/maestro/flows/b2/smoke"
        bundleId  = "com.example.brand2.uat"
    }
}

$smokeTests = @("app-launch", "store-search", "tab-navigation", "browse-menu")

# Filter brands
if ($Brand -eq "all") {
    $runBrands = @("brand3", "Brand One", "b2")
} else {
    $runBrands = @($Brand)
}

# Filter tests
if ($Tests -ne "all") {
    $smokeTests = @($Tests)
}

# ── Results Tracking ──
$results = @()
$totalPassed = 0
$totalFailed = 0
$totalSkipped = 0
$startTime = Get-Date

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SMOKE SUITE - Multi-Brand Test Runner" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Brands : $($runBrands -join ', ')" -ForegroundColor White
Write-Host "  Tests  : $($smokeTests -join ', ')" -ForegroundColor White
Write-Host "  Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

foreach ($brandKey in $runBrands) {
    $brandInfo = $brands[$brandKey]
    Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  BRAND: $($brandInfo.name) ($($brandInfo.bundleId))" -ForegroundColor Yellow
    Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

    foreach ($test in $smokeTests) {
        $flowFile = "$($brandInfo.folder)/$test.yaml"
        $fullPath = Join-Path (Get-Location) $flowFile

        # Check if flow file exists
        if (-not (Test-Path $fullPath)) {
            Write-Host "  [SKIP] $test - flow file not found" -ForegroundColor DarkGray
            $totalSkipped++
            $results += [PSCustomObject]@{
                Brand  = $brandInfo.name
                Test   = $test
                Status = "SKIPPED"
                Time   = "-"
            }
            continue
        }

        Write-Host "  [RUN]  $test ... " -ForegroundColor White -NoNewline

        $testStart = Get-Date

        # Run maestro test
        & $MaestroBin test $flowFile 2>&1 | Out-Null
        $exitCode = $LASTEXITCODE

        $testEnd = Get-Date
        $duration = [math]::Round(($testEnd - $testStart).TotalSeconds, 1)

        if ($exitCode -eq 0) {
            Write-Host "PASSED ($($duration)s)" -ForegroundColor Green
            $totalPassed++
            $results += [PSCustomObject]@{
                Brand  = $brandInfo.name
                Test   = $test
                Status = "PASSED"
                Time   = "$($duration)s"
            }
        } else {
            Write-Host "FAILED ($($duration)s)" -ForegroundColor Red
            $totalFailed++
            $results += [PSCustomObject]@{
                Brand  = $brandInfo.name
                Test   = $test
                Status = "FAILED"
                Time   = "$($duration)s"
            }
        }
    }
    Write-Host ""
}

# ── Summary Report ──
$endTime = Get-Date
$totalTime = [math]::Round(($endTime - $startTime).TotalSeconds, 1)
$totalTests = $totalPassed + $totalFailed + $totalSkipped

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SMOKE SUITE RESULTS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Results table
$results | Format-Table -Property Brand, Test, Status, Time -AutoSize

Write-Host "------------------------------------------------------------"
Write-Host "  Total : $totalTests tests" -ForegroundColor White
Write-Host "  Passed: $totalPassed" -ForegroundColor Green
Write-Host "  Failed: $totalFailed" -ForegroundColor $(if ($totalFailed -gt 0) { "Red" } else { "Green" })
Write-Host "  Skipped: $totalSkipped" -ForegroundColor $(if ($totalSkipped -gt 0) { "Yellow" } else { "White" })
Write-Host "  Time  : $($totalTime)s" -ForegroundColor White
Write-Host "------------------------------------------------------------"
Write-Host ""

# ── Save results to file ──
$reportFile = "test-results/smoke-suite-$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').txt"
$reportDir = Split-Path $reportFile -Parent
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}

$reportContent = @"
SMOKE SUITE RESULTS
==================
Date   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Brands : $($runBrands -join ', ')
Tests  : $($smokeTests -join ', ')
Total  : $totalTests | Passed: $totalPassed | Failed: $totalFailed | Skipped: $totalSkipped
Time   : $($totalTime)s

DETAILS
-------
"@

foreach ($r in $results) {
    $reportContent += "`n[$($r.Status)] $($r.Brand) - $($r.Test) ($($r.Time))"
}

$reportContent | Out-File -FilePath $reportFile -Encoding UTF8
Write-Host "  Report saved: $reportFile" -ForegroundColor DarkGray
Write-Host ""

# Exit with failure code if any tests failed
if ($totalFailed -gt 0) {
    exit 1
}
