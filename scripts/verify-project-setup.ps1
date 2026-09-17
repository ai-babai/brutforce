[CmdletBinding()]
param(
    [switch]$FullData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$errors = [System.Collections.Generic.List[string]]::new()

$requiredFiles = @(
    'AGENTS.md',
    'INDEX.md',
    'PROJECT.md',
    'ARCHITECTURE.md',
    'PLAN.md',
    'TASKS.md',
    'ERRORS.md',
    'README.md',
    '.codex/config.toml',
    '.codex/README.md',
    'agents-os/BOOTSTRAP.md',
    'agents-os/INDEX.md',
    'agents-os/MEMORY.md',
    'agents-os/SOUL.md',
    'agents-os/memory/WORKING.md',
    'agents-os/memory/FACTS.md',
    'agents-os/memory/KEY-MOMENTS.md',
    'agents-os/memory/PROCEDURES.md',
    'agents-os/protocols/HANDOFF.md',
    'agents-os/protocols/MEMORY-LIFECYCLE.md',
    'agents-os/protocols/DATA-LIFECYCLE.md',
    'agents-os/roles/INDEX.md',
    'docs/product/ACCEPTANCE-MATRIX.md',
    'docs/data/DATA-CONTRACT.md',
    'docs/data/COLLECTION-RUNBOOK.md',
    'docs/data/SOURCE-REGISTRY.md',
    'docs/data/EXTERNAL-DATASETS-ASSESSMENT.md',
    'docs/evaluation/EVALUATION-PROTOCOL.md',
    'Dataset/README.md',
    'Dataset/CONTRACT.md',
    'Dataset/REGISTRY.yaml',
    'scripts/build-raw-source-manifest.ps1',
    'scripts/verify-dataset-layout.ps1'
)

if ($FullData) {
    $requiredFiles += @(
        'Dataset/91_manifests/raw-source-files-v1.0.0.jsonl',
        'Dataset/91_manifests/raw-source-files-v1.0.0.sha256'
    )
}

$requiredDirs = @(
    '.codex/agents',
    'Dataset/00_raw',
    'Dataset/01_svoe_vino_catalog',
    'Dataset/02_rvk_telegram',
    'Dataset/03_manual_store',
    'Dataset/04_svoe_vino_web_enrichment',
    'Dataset/05_retail_alcohol_detection',
    'Dataset/06_wine_images_126k',
    'Dataset/07_x_wines',
    'Dataset/08_winesensed',
    'Dataset/09_rf100_wine_labels',
    'Dataset/10_open_food_facts_wine_ru',
    'Dataset/90_splits/v1',
    'Dataset/91_manifests',
    'Dataset/92_reports',
    'Dataset/99_quarantine',
    'docs/adr',
    'docs/testing',
    'runs'
)

foreach ($relativePath in $requiredFiles) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        $errors.Add("Missing file: ${relativePath}")
    }
}

if ($FullData -and @(Get-ChildItem -LiteralPath $projectRoot -File -Filter '*.pdf').Count -lt 1) {
    $errors.Add('Missing private source PDF in the project root.')
}

foreach ($relativePath in $requiredDirs) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Container)) {
        $errors.Add("Missing directory: ${relativePath}")
    }
}

$workingPath = Join-Path $projectRoot 'agents-os/memory/WORKING.md'
if (Test-Path -LiteralPath $workingPath -PathType Leaf) {
    $workingLines = @(Get-Content -LiteralPath $workingPath).Count
    if ($workingLines -gt 250) {
        $errors.Add("WORKING.md exceeds the hard limit: ${workingLines} lines")
    }
}

$agentsPath = Join-Path $projectRoot '.codex/agents'
$agentFiles = @(Get-ChildItem -LiteralPath $agentsPath -Filter '*.toml' -File)
if ($agentFiles.Count -lt 1) {
    $errors.Add('No project custom agents found')
}

foreach ($agentFile in $agentFiles) {
    $content = Get-Content -Raw -LiteralPath $agentFile.FullName
    foreach ($field in 'name', 'description', 'developer_instructions') {
        if ($content -notmatch "(?m)^${field}\s*=") {
            $errors.Add("Agent $($agentFile.Name) misses required field ${field}")
        }
    }
}

$datasetVerifier = Join-Path $PSScriptRoot 'verify-dataset-layout.ps1'
if (Test-Path -LiteralPath $datasetVerifier -PathType Leaf) {
    $datasetOutput = if ($FullData) {
        & $datasetVerifier 2>&1
    }
    else {
        & $datasetVerifier -MetadataOnly 2>&1
    }
    if (-not $?) {
        $errors.Add("Dataset verification failed: $($datasetOutput -join ' | ')")
    }
}

$markdownFiles = Get-ChildItem -LiteralPath $projectRoot -Filter '*.md' -File -Recurse |
    Where-Object { $_.FullName -notmatch '[\\/]agents-os[\\/]memory[\\/]archive[\\/]' }

$linkPattern = [regex]'\[[^\]]+\]\(([^)]+)\)'
foreach ($markdownFile in $markdownFiles) {
    $content = Get-Content -Raw -LiteralPath $markdownFile.FullName
    foreach ($match in $linkPattern.Matches($content)) {
        $target = $match.Groups[1].Value.Trim()
        if ($target -match '^(https?://|#|mailto:)' -or $target.Contains('<')) {
            continue
        }
        $pathOnly = ($target -split '#', 2)[0]
        if ([string]::IsNullOrWhiteSpace($pathOnly)) {
            continue
        }
        $resolved = Join-Path $markdownFile.DirectoryName $pathOnly
        if (-not (Test-Path -LiteralPath $resolved)) {
            $relativeFile = [System.IO.Path]::GetRelativePath($projectRoot, $markdownFile.FullName)
            $errors.Add("Broken link in ${relativeFile}: ${target}")
        }
    }
}

if ($errors.Count -gt 0) {
    foreach ($message in $errors) {
        Write-Error $message
    }
    exit 1
}

Write-Output "PASS: Vino project bootstrap is structurally consistent."
Write-Output "Custom agents: $($agentFiles.Count)"
Write-Output "Working memory lines: $workingLines"
Write-Output "Data mode: $(if ($FullData) { 'full local dataset' } else { 'Git metadata only' })"
