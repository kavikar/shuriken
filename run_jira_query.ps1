$base = "https://your-tenant.atlassian.net"
$basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$($env:JIRA_EMAIL):$($env:JIRA_API_TOKEN)"))
$h = @{Authorization="Basic $basic"; 'Content-Type'='application/json'; Accept='application/json'}
function Flatten-ADF($node) {
    if (-not $node) { return "" }
    if ($node.text) { return $node.text }
    if ($node.content) {
        $parts = foreach ($c in $node.content) { Flatten-ADF $c }
        return $parts -join ""
    }
    return ""
}
$issueKeys = "PROJ-5467,PROJ-10274,PROJ-5471,PROJ-5470,PROJ-5469,PROJ-5468,PROJ-5473,PROJ-5472,PROJ-6659,PROJ-6662,PROJ-5465,PROJ-5466"
$r_issues = Invoke-RestMethod -Uri "$base/rest/api/3/search?jql=$([uri]::EscapeDataString("key in ($issueKeys)"))&fields=summary,status,assignee,updated,priority,issuetype" -Headers $h -Method GET
$r_epic = Invoke-RestMethod -Uri "$base/rest/api/3/search?jql=$([uri]::EscapeDataString("'Epic Link' = PROJ-5467 ORDER BY updated DESC"))&maxResults=20&fields=summary,status,updated" -Headers $h -Method GET

Write-Host "### Epic Health Summary ###"
$r_issues.issues | Where-Object { $_.fields.issuetype.name -eq "Epic" } | ForEach-Object { "[$($_.key)] $($_.fields.summary) - Status: $($_.fields.status.name)" }

Write-Host "`n### Child Issue Latest Updates (PROJ-5467) ###"
$r_epic.issues | Select-Object -First 5 | ForEach-Object { "$($_.key): $($_.fields.summary) | $($_.fields.status.name) | $($_.fields.updated)" }

Write-Host "`n### Critical Blockers / Open Tasks ###"
$r_issues.issues | Where-Object { $_.fields.status.name -notin @("Done", "Closed", "Resolved") } | ForEach-Object { "$($_.key) ($($_.fields.priority.name)): $($_.fields.summary) [$($_.fields.status.name)]" }

foreach ($k in @("PROJ-5467", "PROJ-10274")) {
    $r_comm = Invoke-RestMethod -Uri "$base/rest/api/3/issue/$k/comment?maxResults=3&orderBy=-created" -Headers $h -Method GET
    Write-Host "`n-- Recent Comments: $k --"
    $r_comm.comments | ForEach-Object { 
        $bt = Flatten-ADF $_.body
        $bt = if($bt.Length -gt 100){$bt.Substring(0,100)+"..."}else{$bt}
        "  $($_.created) [$($_.author.displayName)]: $bt"
    }
}

try {
    $r_conf = Invoke-RestMethod -Uri "$base/wiki/rest/api/content/000000000000?expand=version,history,space" -Headers $h -Method GET
    Write-Host "`n### Confluence Page Freshness ###"
    "Title: $($r_conf.title)"
    "Space: $($r_conf.space.key) | Version: $($r_conf.version.number)"
    "Last updated: $($r_conf.history.lastUpdated.when) by $($r_conf.history.lastUpdated.by.displayName)"
} catch { Write-Host "`n### Confluence Page Freshness ###"; "Page not accessible." }
