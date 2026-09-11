param(
    [string]$Release = "Digital 26.12",
    [string]$ScopeProject = "DOVS",
    [string]$TestProject = "IQE",
    [int]$ReleasesBack = 5,
    [string[]]$Platforms = @("Web", "App"),
    [switch]$CreateExecutions
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = $PSScriptRoot
. "$scriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath

Write-Host "[1/6] Fetching release scope..."
& "$scriptRoot\fetch-release-scope.ps1" -Release $Release -ProjectKey $ScopeProject

Write-Host "[2/6] Mining defect patterns..."
& "$scriptRoot\mine-defect-patterns.ps1" -BaseRelease $Release -ReleasesBack $ReleasesBack -ProjectKey $ScopeProject

Write-Host "[3/6] Fetching test inventory..."
& "$scriptRoot\fetch-test-inventory.ps1" -ProjectKey $TestProject -Platforms $Platforms

$releaseSlug = $Release.Replace(" ", "_")
$defectCsv = Join-Path $reportsPath "defect_patterns_$releaseSlug.csv"
$inventoryCsv = Join-Path $reportsPath "test_inventory_by_component.csv"

Write-Host "[4/6] Assigning component tiers..."
& "$scriptRoot\assign-component-tiers.ps1" -DefectPatternCsv $defectCsv -InventorySummaryCsv $inventoryCsv -OutputName "component_tiers_$releaseSlug.csv"

Write-Host "[5/6] Building tier test pools..."
$tierCsv = Join-Path $reportsPath "component_tiers_$releaseSlug.csv"
$inventoryJson = Join-Path $reportsPath "test_inventory_raw.json"
& "$scriptRoot\build-tier-test-pools.ps1" -TierCsv $tierCsv -InventoryJson $inventoryJson -MaxPerComponent 30

Write-Host "[6/6] Planning or creating test executions..."
if ($CreateExecutions) {
    & "$scriptRoot\create-test-executions.ps1" -Release $Release -ProjectKey $TestProject -Execute
}
else {
    & "$scriptRoot\create-test-executions.ps1" -Release $Release -ProjectKey $TestProject
}

Write-Host "Regression planning pipeline completed."
Write-Host "Outputs: $reportsPath"
