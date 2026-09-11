param(
    [switch]$ExtractTestPlans,
    [switch]$AnalyzeLeakage,
    [switch]$Full
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = $PSScriptRoot

if ($ExtractTestPlans -or $Full) {
    Write-Host "═══════════════════════════════════════════"
    Write-Host "STEP 1: Extract Test Cases from Test Plans"
    Write-Host "═══════════════════════════════════════════"
    & "$scriptRoot\extract-test-plans.ps1"
}

if ($AnalyzeLeakage -or $Full) {
    Write-Host "
═══════════════════════════════════════════"
    Write-Host "STEP 2: Analyze Historical Leakage"
    Write-Host "═══════════════════════════════════════════"
    & "$scriptRoot\analyze-historical-leakage.ps1"
}

Write-Host "
✓ Historical analysis pipeline complete"
