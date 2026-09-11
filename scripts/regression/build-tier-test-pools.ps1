param(
    [string]$TierCsv,
    [string]$InventoryJson,
    [int]$MaxPerComponent = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath
if (-not $TierCsv) {
    $TierCsv = Join-Path $reportsPath "component_tiers.csv"
}
if (-not $InventoryJson) {
    $InventoryJson = Join-Path $reportsPath "test_inventory_raw.json"
}

if (-not (Test-Path $TierCsv)) {
    throw "Tier file not found: $TierCsv"
}
if (-not (Test-Path $InventoryJson)) {
    throw "Inventory JSON file not found: $InventoryJson"
}

$tiers = Import-Csv -Path $TierCsv
$tests = Get-Content -Raw -Path $InventoryJson | ConvertFrom-Json -Depth 100

$pool = @{
    Tier1 = @()
    Tier2 = @()
    Tier3 = @()
}

foreach ($tierRow in $tiers) {
    $component = [string]$tierRow.component
    $tier = [string]$tierRow.assigned_tier

    if (-not $pool.ContainsKey($tier)) {
        continue
    }

    $componentTests = @($tests | Where-Object {
        ($_.components -split "\|") -contains $component
    })

    if ($componentTests.Count -eq 0) {
        continue
    }

    $selected = $componentTests |
        Sort-Object @{ Expression = { if ($_.isAutomated -eq $true -or $_.isAutomated -eq "True") { 0 } else { 1 } } }, key |
        Select-Object -First $MaxPerComponent

    $pool[$tier] += $selected
}

# Remove duplicate test keys inside each tier.
foreach ($tierName in @("Tier1", "Tier2", "Tier3")) {
    $pool[$tierName] = @($pool[$tierName] | Group-Object key | ForEach-Object { $_.Group[0] })
}

$summary = foreach ($tierName in @("Tier1", "Tier2", "Tier3")) {
    $testsForTier = @($pool[$tierName])
    $automatedCount = @($testsForTier | Where-Object { $_.isAutomated -eq $true -or $_.isAutomated -eq "True" }).Count

    [pscustomobject]@{
        tier            = $tierName
        total_tests     = $testsForTier.Count
        automated_tests = $automatedCount
        manual_tests    = $testsForTier.Count - $automatedCount
        sample_keys     = (@($testsForTier.key | Select-Object -First 15) -join "|")
    }
}

$poolPath = Join-Path $reportsPath "tier_test_pools.json"
$summaryPath = Join-Path $reportsPath "tier_test_pools_summary.csv"

$pool | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 -Path $poolPath
$summary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $summaryPath

Write-Host "Tier test pools exported: $poolPath"
Write-Host "Tier summary exported:    $summaryPath"
