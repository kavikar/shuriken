Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ShurikenRoot {
    $root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    return $root.Path
}

function Get-RegressionReportsPath {
    $reportsPath = Join-Path (Get-ShurikenRoot) "Reports\regression"
    if (-not (Test-Path $reportsPath)) {
        New-Item -ItemType Directory -Path $reportsPath | Out-Null
    }
    return $reportsPath
}

function Get-exampleMcpEndpoint {
    if ($env:example_MCP_ENDPOINT -and $env:example_MCP_ENDPOINT.Trim()) {
        return $env:example_MCP_ENDPOINT.Trim()
    }
    return "https://example-mcp.dev.staging.example/mcp"
}

function Get-exampleMcpHeaders {
    $jiraEmail = $env:JIRA_EMAIL
    $jiraToken = $env:JIRA_API_TOKEN
    $gitlabToken = $env:GITLAB_TOKEN
    $jiraBase = $env:JIRA_BASE_URL
    $PlannerToken = $env:Planner_TOKEN

    if (-not $jiraEmail) { throw "Missing env var JIRA_EMAIL." }
    if (-not $jiraToken) { throw "Missing env var JIRA_API_TOKEN." }
    if (-not $gitlabToken) { throw "Missing env var GITLAB_TOKEN." }
    if (-not $jiraBase) { throw "Missing env var JIRA_BASE_URL." }

    $headers = @{
        "Content-Type"    = "application/json"
        "Accept"          = "application/json, text/event-stream"
        "X-Jira-Email"    = $jiraEmail
        "X-Jira-Token"    = $jiraToken
        "X-GitLab-Token"  = $gitlabToken
        "X-Jira-Base-URL" = $jiraBase
    }

    if ($PlannerToken) {
        $headers["Planner_token"] = $PlannerToken
    }

    return $headers
}

function Resolve-McpResult {
    param(
        [Parameter(Mandatory = $true)]
        $Result
    )

    if ($null -eq $Result) {
        return $null
    }

    if ($Result.PSObject.Properties.Name -contains "content") {
        $content = @($Result.content)
        if ($content.Count -eq 0) {
            return $null
        }

        $decoded = @()
        foreach ($item in $content) {
            if ($item.PSObject.Properties.Name -contains "json") {
                $decoded += $item.json
                continue
            }

            if ($item.PSObject.Properties.Name -contains "text") {
                $text = [string]$item.text
                if (-not $text.Trim()) {
                    continue
                }
                try {
                    $decoded += ($text | ConvertFrom-Json -Depth 50)
                }
                catch {
                    $decoded += $text
                }
                continue
            }

            $decoded += $item
        }

        if ($decoded.Count -eq 1) {
            return $decoded[0]
        }

        return ,$decoded
    }

    if ($Result.PSObject.Properties.Name -contains "structuredContent") {
        return $Result.structuredContent
    }

    return $Result
}

function ConvertFrom-McpSsePayload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $events = @()
    $lines = $Content -split "`r?`n"
    foreach ($line in $lines) {
        if (-not $line.StartsWith("data:")) {
            continue
        }

        $data = $line.Substring(5).Trim()
        if (-not $data -or $data -eq "[DONE]") {
            continue
        }

        try {
            $events += ($data | ConvertFrom-Json -Depth 50)
        }
        catch {
            # Ignore non-JSON event chunks.
        }
    }

    if ($events.Count -eq 0) {
        throw "No parseable JSON payload was found in SSE response." 
    }

    return $events[-1]
}

function Invoke-exampleMCP {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Tool,

        [Parameter(Mandatory = $false)]
        [hashtable]$Params = @{},

        [Parameter(Mandatory = $false)]
        [string]$Endpoint
    )

    if (-not $Endpoint) {
        $Endpoint = Get-exampleMcpEndpoint
    }

    $headers = Get-exampleMcpHeaders
    $requestBody = @{
        jsonrpc = "2.0"
        id      = [guid]::NewGuid().ToString()
        method  = "tools/call"
        params  = @{
            name      = $Tool
            arguments = $Params
        }
    }

    $json = $requestBody | ConvertTo-Json -Depth 100
    $response = Invoke-WebRequest -Uri $Endpoint -Method POST -Headers $headers -Body $json

    $contentType = ""
    if ($response.Headers["Content-Type"]) {
        $contentType = $response.Headers["Content-Type"]
    }

    if ($contentType -like "*text/event-stream*") {
        $payload = ConvertFrom-McpSsePayload -Content $response.Content
    }
    else {
        $payload = $response.Content | ConvertFrom-Json -Depth 100
    }

    if ($payload.error) {
        throw "MCP error calling '$Tool': $($payload.error.message)"
    }

    if ($payload.result) {
        return (Resolve-McpResult -Result $payload.result)
    }

    return $payload
}

function Get-McpIssueArray {
    param(
        [Parameter(Mandatory = $true)]
        $Payload
    )

    if ($Payload -is [array]) {
        return @($Payload)
    }
    if ($Payload.issues) {
        return @($Payload.issues)
    }
    if ($Payload.data -and $Payload.data.issues) {
        return @($Payload.data.issues)
    }
    if ($Payload.result -and $Payload.result.issues) {
        return @($Payload.result.issues)
    }

    return @()
}

function Get-McpTestArray {
    param(
        [Parameter(Mandatory = $true)]
        $Payload
    )

    if ($Payload -is [array]) {
        return @($Payload)
    }
    if ($Payload.tests) {
        return @($Payload.tests)
    }
    if ($Payload.data -and $Payload.data.tests) {
        return @($Payload.data.tests)
    }
    if ($Payload.results) {
        return @($Payload.results)
    }

    return @()
}
