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

function Get-XrayAuthToken {
    $clientId = $env:XRAY_CLIENT_ID
    $clientSecret = $env:XRAY_CLIENT_SECRET
    
    if (-not $clientId) { throw "Missing env var XRAY_CLIENT_ID" }
    if (-not $clientSecret) { throw "Missing env var XRAY_CLIENT_SECRET" }
    
    Write-Host "  [Auth] Requesting Xray token..."
    
    $body = @{
        client_id     = $clientId
        client_secret = $clientSecret
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "https://xray.cloud.getxray.app/api/v1/authenticate" `
        -Method Post -ContentType "application/json" -Body $body
    
    if ($response -is [string]) {
        return $response.Trim('"')
    }
    if ($response.token) {
        return $response.token
    }
    return $response
}

function Get-XrayTestPlanTests {
    param([string]$TestPlanKey, [string]$Token)
    
    $headers = @{
        "Authorization" = "Bearer $Token"
        "Content-Type"  = "application/json"
    }
    
    Write-Host "    → Querying test plan $TestPlanKey..."
    
    $gqlQuery = @"
{
  testPlan(key: "$TestPlanKey") {
    key
    name
    tests {
      total
      results {
        key
        name
        components {
          name
        }
        status {
          name
        }
      }
    }
  }
}
"@
    
    $body = @{
        query = $gqlQuery
    } | ConvertTo-Json -Depth 10
    
    try {
        $response = Invoke-RestMethod -Uri "https://xray.cloud.getxray.app/api/v1/graphql" `
            -Method Post -Headers $headers -Body $body
        
        if ($response.errors) {
            throw "GraphQL error: $($response.errors | ConvertTo-Json)"
        }
        
        return $response.data.testPlan
    } catch {
        Write-Host "    ⚠️ Error: $($_.Exception.Message)"
        return $null
    }
}

$reportsPath = "$PSScriptRoot\..\..\reports\regression"
if (-not (Test-Path $reportsPath)) {
    New-Item -ItemType Directory -Path $reportsPath | Out-Null
}

Write-Host "[1/4] Extracting test cases from Test Plans (Xray API)..."
Write-Host ""

$token = $null
try {
    $token = Get-XrayAuthToken
    Write-Host "  ✓ Authentication successful"
} catch {
    Write-Host "✗ Authentication failed: $_"
    exit 1
}

Write-Host ""

$allTests = @()
$successCount = 0
$errorCount = 0

foreach ($release in ($TestPlanKeys.Keys | Sort-Object)) {
    Write-Host "  [$release] Fetching test plans..."
    
    foreach ($tpKey in $TestPlanKeys[$release]) {
        $testPlan = Get-XrayTestPlanTests -TestPlanKey $tpKey -Token $token
        
        if ($testPlan) {
            Write-Host "    ✓ $tpKey — $($testPlan.tests.total) tests"
            
            foreach ($test in $testPlan.tests.results) {
                $components = @()
                if ($test.components -and $test.components.Count -gt 0) {
                    $components = @($test.components | ForEach-Object { $_.name })
                } else {
                    $components = @("UNMAPPED")
                }
                
                $sep = [char]124
                $compStr = $components -join $sep
                
                $statusStr = "UNKNOWN"
                if ($test.status) {
                    $statusStr = $test.status.name
                }

                $allTests += [pscustomobject]@{
                    release     = $release
                    tp_key      = $tpKey
                    test_key    = $test.key
                    summary     = $test.name
                    components  = $compStr
                    status      = $statusStr
                }
            }
            $successCount++
        } else {
            $errorCount++
        }
    }
}

Write-Host ""
$outputPath = Join-Path $reportsPath "historical_test_plans_all_releases.csv"
$allTests | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $outputPath

Write-Host "✓ Extracted $($allTests.Count) tests from $successCount Test Plans"
if ($errorCount -gt 0) {
    Write-Host "⚠️  Failed to fetch $errorCount Test Plans"
}
Write-Host "→ Output: $outputPath"
