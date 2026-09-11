param(
    [string]$ScopeCsvPath = "$PSScriptRoot\..\..\projects\jira\xray-regression-planner\data-csv-exports\release-tickets.csv",
    [string]$DefectsCsvPath = "$PSScriptRoot\..\..\projects\jira\xray-regression-planner\data-csv-exports\prod-defects.csv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath

Write-Host "[2/4] Loading scope and defect data..."

# Load data
$scope = Import-Csv -Path $ScopeCsvPath
$defects = Import-Csv -Path $DefectsCsvPath
$testPlans = Import-Csv -Path (Join-Path $reportsPath "historical_test_plans_all_releases.csv")

# Extract release from fix versions
$releaseMap = @{}
foreach ($issue in $scope) {
    if ($issue.'Fix versions') {
        $release = $issue.'Fix versions' -replace 'Digital ', ''
        $releaseMap[$issue.'Issue key'] = @{
            release = $release
            summary = $issue.Summary
            type    = $issue.'Issue Type'
        }
    }
}

# Extract release and component from defects
$defectsByComponentRelease = @{}
foreach ($defect in $defects) {
    if ($defect.'Fix versions' -and $defect.'Issue key') {
        $release = $defect.'Fix versions' -replace 'Digital ', ''
        $key = $defect.'Issue key'
        
        if (-not $defectsByComponentRelease["`"]) {
            $defectsByComponentRelease["$release"] = @()
        }
        
        $defectsByComponentRelease["$release"] += [pscustomobject]@{
            key     = $key
            summary = $defect.Summary
            release = $release
        }
    }
}

Write-Host "  Scope: $($scope.Count) issues"
Write-Host "  Defects: $($defects.Count) issues"
Write-Host "  Test Plans: $($testPlans.Count) tests"

Write-Host "[3/4] Cross-referencing and classifying escapes..."

# Build analysis
$leakageAnalysis = @()

foreach ($release in @("26.11", "26.10", "26.9", "26.8")) {
    $releaseTests = @($testPlans | Where-Object { $_.release -eq $release })
    $releaseDefects = if ($defectsByComponentRelease["$release"]) { $defectsByComponentRelease["$release"] } else { @() }
    $releaseScope = @($scope | Where-Object { $_.'Fix versions' -like "*$release*" })
    
    $testedComponents = @($releaseTests.components -split '\|' | Sort-Object -Unique)
    $escapedDefectCount = $releaseDefects.Count
    
    foreach ($defect in $releaseDefects) {
        $wasTestedInTP = $false
        foreach ($test in $releaseTests) {
            if (($test.components -split '\|') -contains $defect.key.Substring(0, 5)) {
                $wasTestedInTP = $true
                break
            }
        }
        
        $gapType = if ($wasTestedInTP) { "False Negative" } else { "Coverage Gap" }
        
        $leakageAnalysis += [pscustomobject]@{
            release              = $release
            defect_key           = $defect.key
            defect_summary       = $defect.summary
            gap_type             = $gapType
            tested_in_tp         = $wasTestedInTP
            scope_count          = $releaseScope.Count
            tested_components    = $testedComponents.Count
            total_defects        = $escapedDefectCount
        }
    }
}

$outputPath = Join-Path $reportsPath "historical_leakage_analysis.csv"
$leakageAnalysis | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $outputPath

Write-Host "✓ Leakage analysis generated → $outputPath"
Write-Host "[4/4] Done!"

# Summary
Write-Host "
=== HISTORICAL LEAKAGE SUMMARY ==="
$leakageAnalysis | Group-Object release | ForEach-Object {
    $rls = $_.Name
    $falseNegs = @($_.Group | Where-Object { $_.gap_type -eq 'False Negative' }).Count
    $coverageGaps = @($_.Group | Where-Object { $_.gap_type -eq 'Coverage Gap' }).Count
    Write-Host "$rls: $($_.Count) escapes (False Neg: $falseNegs, Coverage Gap: $coverageGaps)"
}
