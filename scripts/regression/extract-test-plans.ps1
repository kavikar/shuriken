param(
    [hashtable]$TestPlanKeys = @{
        "26.11" = @("TE-10114", "TE-10115", "TE-10113")
        "26.10" = @("TE-10099", "TE-10100", "TE-10112")
        "26.9"  = @("TE-10090", "TE-10097", "TE-10098")
        "26.8"  = @("TE-10089", "TE-10088", "TE-10116")
    }
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath
Write-Host "[1/4] Extracting test cases from Test Plans..."

$allTests = @()

foreach ($release in $TestPlanKeys.Keys) {
    foreach ($tpKey in $TestPlanKeys[$release]) {
        Write-Host "  [$release] Fetching $tpKey..."
        
        try {
            $raw = Invoke-exampleMCP -Tool "xray_get_test_plan" -Params @{
                testPlanKey = $tpKey
                includeTests = $true
            }
            
            $tests = Get-McpTestArray -Payload $raw
            
            foreach ($test in $tests) {
                $components = @($test.fields.components | ForEach-Object { $_.name })
                if ($components.Count -eq 0) {
                    $components = @("UNMAPPED")
                }

                $allTests += [pscustomobject]@{
                    release     = $release
                    tp_key      = $tpKey
                    test_key    = $test.key
                    summary     = $test.fields.summary
                    components  = ($components -join "|")
                    status      = if ($test.fields.status) { $test.fields.status.name } else { "UNKNOWN" }
                }
            }
        } catch {
            Write-Host "    ⚠️ Error: $_"
        }
    }
}

$outputPath = Join-Path $reportsPath "historical_test_plans_all_releases.csv"
$allTests | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $outputPath
Write-Host "✓ Extracted $($allTests.Count) tests → $outputPath"
