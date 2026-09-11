param(
    [string]$DefectPatternCsv,
    [string]$InventorySummaryCsv,
    [string]$OutputName = "component_tiers.csv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath
if (-not $DefectPatternCsv) {
    $DefectPatternCsv = Join-Path $reportsPath "defect_patterns_Digital_26.12.csv"
}
if (-not $InventorySummaryCsv) {
    $InventorySummaryCsv = Join-Path $reportsPath "test_inventory_by_component.csv"
}

if (-not (Test-Path $DefectPatternCsv)) {
    throw "Defect pattern file not found: $DefectPatternCsv"
}
if (-not (Test-Path $InventorySummaryCsv)) {
    throw "Inventory summary file not found: $InventorySummaryCsv"
}

$defects = Import-Csv -Path $DefectPatternCsv
$inventory = Import-Csv -Path $InventorySummaryCsv

$inventoryMap = @{}
foreach ($row in $inventory) {
    $inventoryMap[$row.component] = [int]$row.total_tests
}

$criticalityMap = @{
    "GENERIC_Account_Management" = 1.00
    "GENERIC_Payments"           = 1.00
    "GENERIC_Ordering"           = 1.00
    "GENERIC_Loyalty"            = 0.90
    "GENERIC_Fulfillment"        = 0.80
    "GENERIC_Bag"                = 0.80
    "GENERIC_Order_History"      = 0.70
    "GENERIC_Menu"               = 0.70
    "GENERIC_Location"           = 0.60
    "GENERIC_POS_Integration"    = 0.50
    "GENERIC_Accessibility"      = 0.40
    "UNMAPPED"                = 0.50
}

$tiers = foreach ($row in $defects) {
    $component = [string]$row.component
    $bugCount = [int]$row.bug_count
    $testCount = 0
    if ($inventoryMap.ContainsKey($component)) {
        $testCount = $inventoryMap[$component]
    }

    $criticality = 0.50
    if ($criticalityMap.ContainsKey($component)) {
        $criticality = $criticalityMap[$component]
    }

    $frequencyScore = [Math]::Min(($bugCount / 15.0), 1.0)
    $inventoryCoverage = [Math]::Min(($testCount / 120.0), 1.0)
    $scarcityScore = 1.0 - $inventoryCoverage
    $riskScore = ($frequencyScore * 0.50) + ($criticality * 0.30) + ($scarcityScore * 0.20)
    $riskScore = [Math]::Round($riskScore, 3)

    $tier = if ($riskScore -ge 0.65) {
        "Tier1"
    }
    elseif ($riskScore -ge 0.40) {
        "Tier2"
    }
    else {
        "Tier3"
    }

    [pscustomobject]@{
        component      = $component
        bug_count      = $bugCount
        test_count     = $testCount
        criticality    = $criticality
        frequencyScore = [Math]::Round($frequencyScore, 3)
        scarcityScore  = [Math]::Round($scarcityScore, 3)
        risk_score     = $riskScore
        assigned_tier  = $tier
    }
}

$outputPath = Join-Path $reportsPath $OutputName
$tiers |
    Sort-Object risk_score -Descending |
    Export-Csv -NoTypeInformation -Encoding UTF8 -Path $outputPath

Write-Host "Component tiers exported: $outputPath"
Write-Host "Tier1 count: $((@($tiers | Where-Object { $_.assigned_tier -eq 'Tier1' })).Count)"
Write-Host "Tier2 count: $((@($tiers | Where-Object { $_.assigned_tier -eq 'Tier2' })).Count)"
Write-Host "Tier3 count: $((@($tiers | Where-Object { $_.assigned_tier -eq 'Tier3' })).Count)"
