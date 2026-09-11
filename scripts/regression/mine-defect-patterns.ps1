param(
    [string]$BaseRelease = "Digital 26.12",
    [int]$ReleasesBack = 5,
    [string]$ProjectKey = "DOVS"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

function Get-ReleaseWindow {
    param(
        [string]$Release,
        [int]$Count
    )

    if ($Release -notmatch "^(.*?)(\d+)\.(\d+)$") {
        throw "Release format must look like 'Digital 26.12'."
    }

    $prefix = $Matches[1]
    $major = [int]$Matches[2]
    $minor = [int]$Matches[3]

    $window = @()
    for ($i = 0; $i -lt $Count; $i++) {
        $nextMinor = $minor - $i
        if ($nextMinor -lt 1) {
            break
        }
        $window += ("{0}{1}.{2}" -f $prefix, $major, $nextMinor)
    }
    return $window
}

$reportsPath = Get-RegressionReportsPath
$releaseWindow = Get-ReleaseWindow -Release $BaseRelease -Count $ReleasesBack
$allBugs = @()

foreach ($release in $releaseWindow) {
    $jql = "fixVersion = `"$release`" AND issueType = Bug AND project = $ProjectKey"
    $raw = Invoke-exampleMCP -Tool "jira_search_issues" -Params @{
        jql        = $jql
        fields     = "summary,components,priority,created,resolutiondate,fixVersion,status"
        maxResults = 200
    }
    $issues = Get-McpIssueArray -Payload $raw

    foreach ($issue in $issues) {
        $components = @($issue.fields.components | ForEach-Object { $_.name })
        if ($components.Count -eq 0) {
            $components = @("UNMAPPED")
        }

        foreach ($component in $components) {
            $allBugs += [pscustomobject]@{
                key        = $issue.key
                summary    = $issue.fields.summary
                component  = $component
                priority   = $issue.fields.priority.name
                status     = $issue.fields.status.name
                release    = $release
                created    = $issue.fields.created
                resolved   = $issue.fields.resolutiondate
            }
        }
    }
}

if ($allBugs.Count -eq 0) {
    throw "No bugs found in the selected release window."
}

$componentAgg = $allBugs |
    Group-Object component |
    ForEach-Object {
        $group = $_.Group
        $prioritySet = @($group.priority | Sort-Object -Unique)
        [pscustomobject]@{
            component         = $_.Name
            bug_count         = $group.Count
            releases_count    = (@($group.release | Sort-Object -Unique)).Count
            releases          = (@($group.release | Sort-Object -Unique) -join "|")
            priorities        = ($prioritySet -join "|")
            sample_keys       = (@($group.key | Select-Object -First 8) -join "|")
        }
    } |
    Sort-Object bug_count -Descending

$releaseSlug = $BaseRelease.Replace(" ", "_")
$bugsPath = Join-Path $reportsPath "defects_window_$releaseSlug.csv"
$aggPath = Join-Path $reportsPath "defect_patterns_$releaseSlug.csv"

$allBugs | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $bugsPath
$componentAgg | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $aggPath

Write-Host "Raw defect list exported: $bugsPath"
Write-Host "Component patterns exported: $aggPath"
Write-Host "Bug records: $($allBugs.Count)"
