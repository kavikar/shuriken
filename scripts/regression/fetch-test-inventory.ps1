param(
    [string]$ProjectKey = "IQE",
    [string[]]$Platforms = @("Web", "App"),
    [int]$MaxResults = 1000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath
$allTests = @()

foreach ($platform in $Platforms) {
    $jql = "project = $ProjectKey AND labels = $platform"
    $raw = Invoke-exampleMCP -Tool "xray_search_tests" -Params @{
        jql        = $jql
        fields     = "summary,components,labels,status,priority,description,customfield_isautomated"
        maxResults = $MaxResults
    }

    $tests = Get-McpTestArray -Payload $raw

    foreach ($test in $tests) {
        $components = @($test.fields.components | ForEach-Object { $_.name })
        if ($components.Count -eq 0) {
            $components = @("UNMAPPED")
        }

        $isAutomated = $false
        if ($test.fields.PSObject.Properties.Name -contains "customfield_isautomated") {
            $rawAutomationValue = [string]$test.fields.customfield_isautomated
            $isAutomated = ($rawAutomationValue -match "(?i)true|yes|automated")
        }

        $allTests += [pscustomobject]@{
            key         = $test.key
            summary     = $test.fields.summary
            platform    = $platform
            components  = ($components -join "|")
            status      = $test.fields.status.name
            priority    = $test.fields.priority.name
            isAutomated = $isAutomated
            labels      = (@($test.fields.labels) -join "|")
        }
    }
}

if ($allTests.Count -eq 0) {
    throw "No tests found for project '$ProjectKey' and selected platforms."
}

$componentAgg = @()
foreach ($test in $allTests) {
    foreach ($component in ($test.components -split "\|")) {
        $componentAgg += [pscustomobject]@{
            component   = $component
            key         = $test.key
            platform    = $test.platform
            isAutomated = $test.isAutomated
        }
    }
}

$componentSummary = $componentAgg |
    Group-Object component |
    ForEach-Object {
        $group = $_.Group
        [pscustomobject]@{
            component       = $_.Name
            total_tests     = $group.Count
            web_tests       = (@($group | Where-Object { $_.platform -eq "Web" })).Count
            app_tests       = (@($group | Where-Object { $_.platform -eq "App" })).Count
            automated_tests = (@($group | Where-Object { $_.isAutomated })).Count
            sample_keys     = (@($group.key | Select-Object -First 10) -join "|")
        }
    } |
    Sort-Object total_tests -Descending

$rawPath = Join-Path $reportsPath "test_inventory_raw.csv"
$summaryPath = Join-Path $reportsPath "test_inventory_by_component.csv"
$jsonPath = Join-Path $reportsPath "test_inventory_raw.json"

$allTests | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $rawPath
$componentSummary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $summaryPath
$allTests | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 -Path $jsonPath

Write-Host "Raw test inventory exported: $rawPath"
Write-Host "Component summary exported:  $summaryPath"
Write-Host "Raw JSON exported:           $jsonPath"
Write-Host "Test records: $($allTests.Count)"
