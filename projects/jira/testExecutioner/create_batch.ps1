$sourceFile = "..\testCaseFullMeal\reports\comet-offers\comet\te-10118-web-non-points-continuous-2026-05-18.txt"
$targetFile = "..\testCaseFullMeal\reports\comet-offers\comet\te-10118-web-non-points-todo-batch-2026-05-18.txt"
$keysToInclude = "TE-10101", "TE-10102", "TE-10103", "TE-10104", "TE-10105", "TE-10106", "TE-10107", "TE-10108", "TE-10109", "TE-10110"

if (Test-Path $sourceFile) {
    $content = Get-Content $sourceFile -Raw
    $blocks = [regex]::Split($content, "(?=Comet Offer Prompt — TE-)")
    $foundMap = @{}
    foreach ($block in $blocks) {
        if ($block -match "Comet Offer Prompt — (TE-\d+)") {
            $key = $matches[1]
            $foundMap[$key] = $block.Trim()
        }
    }
    $outputLines = @()
    $outputLines += "TE TEST BATCH - Batch 01 - Count: 10"
    $outputLines += "TODO Only | Non-Points | TE: TE-10111"
    $outputLines += "=" * 80
    $foundKeys = @()
    $missingKeys = @()
    foreach ($key in $keysToInclude) {
        if ($foundMap.ContainsKey($key)) {
            $outputLines += $foundMap[$key]
            $outputLines += ""
            $foundKeys += $key
        } else {
            $missingKeys += $key
        }
    }
    $finalOutput = $outputLines -join "`r`n"
    Set-Content -Path $targetFile -Value $finalOutput -Encoding UTF8
    "Created file path: $targetFile"
    "Included keys actually found: $($foundKeys -join ', ')"
    "Any missing keys: $(if ($missingKeys.Count -eq 0) { 'none' } else { $missingKeys -join ', ' })"
    "`nFirst 20 lines preview:"
    Get-Content $targetFile -TotalCount 20
} else {
    "Source file not found at $sourceFile"
}
