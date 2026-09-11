param(
    [string]$Release = "Digital 26.12",
    [string]$ProjectKey = "DOVS",
    [string[]]$Statuses = @("Ready for E2E Testing")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$reportsPath = Get-RegressionReportsPath
$statusClause = ($Statuses | ForEach-Object { '"' + $_ + '"' }) -join ","
$jql = "fixVersion = `"$Release`" AND issueType in (Story,Bug) AND project = $ProjectKey AND status in ($statusClause)"

$raw = Invoke-exampleMCP -Tool "jira_search_issues" -Params @{
    jql        = $jql
    fields     = "summary,description,components,issuetype,labels,fixVersion,status,customfield_10845"
    maxResults = 200
}

$issues = Get-McpIssueArray -Payload $raw
if ($issues.Count -eq 0) {
    throw "No issues were returned for release '$Release'."
}

$rows = foreach ($issue in $issues) {
    $components = @($issue.fields.components | ForEach-Object { $_.name })
    [pscustomobject]@{
        key          = $issue.key
        summary      = $issue.fields.summary
        issueType    = $issue.fields.issuetype.name
        status       = $issue.fields.status.name
        components   = ($components -join "|")
        labels       = (@($issue.fields.labels) -join "|")
        fixVersion   = (@($issue.fields.fixVersion | ForEach-Object { $_.name }) -join "|")
        release      = $Release
        project      = $ProjectKey
    }
}

$csvPath = Join-Path $reportsPath "release_scope_$($Release.Replace(' ','_')).csv"
$jsonPath = Join-Path $reportsPath "release_scope_$($Release.Replace(' ','_')).json"

$rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csvPath
$issues | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 -Path $jsonPath

Write-Host "Release scope exported: $csvPath"
Write-Host "Raw payload exported:   $jsonPath"
Write-Host "Issue count: $($rows.Count)"
