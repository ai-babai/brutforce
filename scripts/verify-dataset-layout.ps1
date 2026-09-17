[CmdletBinding()]
param(
    [switch]$SkipHashes,
    [switch]$FullHash,
    [switch]$MetadataOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SkipHashes -and $FullHash) {
    throw 'SkipHashes and FullHash cannot be used together.'
}
if ($MetadataOnly -and $FullHash) {
    throw 'MetadataOnly and FullHash cannot be used together.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$datasetRoot = Join-Path $projectRoot 'Dataset'
$errors = [System.Collections.Generic.List[string]]::new()

$requiredFiles = @(
    'README.md',
    'CONTRACT.md',
    'REGISTRY.yaml',
    '00_raw/README.md',
    '01_svoe_vino_catalog/README.md',
    '02_rvk_telegram/README.md',
    '03_manual_store/README.md',
    '04_svoe_vino_web_enrichment/README.md',
    '05_retail_alcohol_detection/README.md',
    '06_wine_images_126k/README.md',
    '07_x_wines/README.md',
    '08_winesensed/README.md',
    '09_rf100_wine_labels/README.md',
    '10_open_food_facts_wine_ru/README.md',
    '11_mavt_ru_wines/README.md',
    '12_krasnoe_i_beloe_ru_wines/README.md',
    '13_winelab_ru_wines/README.md',
    '14_simplewine_ru_wines/README.md',
    '15_aromatny_mir_ru_wines/README.md',
    '16_alkoteka_ru_wines/README.md',
    '17_luding_ru_wines/README.md',
    '18_russian_wine_master/README.md',
    'REVIEW-ANNOTATION-CONTRACT.md',
    'PARSED-DATASET-TRANSFER.md',
    '90_splits/README.md',
    '90_splits/v1/SPLIT-CONTRACT.yaml',
    '90_splits/v1/SUMMARY.md',
    '91_manifests/README.md',
    '91_manifests/PARSED-DATASET-PACKAGE-SUMMARY.json',
    '92_reports/README.md',
    '99_quarantine/README.md'
)

if (-not $MetadataOnly) {
    $requiredFiles += @(
        '91_manifests/raw-source-files-v1.0.0.jsonl',
        '91_manifests/raw-source-files-v1.0.0.sha256'
    )
}

$requiredDirs = @(
    '00_raw',
    '01_svoe_vino_catalog',
    '02_rvk_telegram',
    '03_manual_store',
    '04_svoe_vino_web_enrichment',
    '05_retail_alcohol_detection',
    '06_wine_images_126k',
    '07_x_wines',
    '08_winesensed',
    '09_rf100_wine_labels',
    '10_open_food_facts_wine_ru',
    '11_mavt_ru_wines',
    '12_krasnoe_i_beloe_ru_wines',
    '13_winelab_ru_wines',
    '14_simplewine_ru_wines',
    '15_aromatny_mir_ru_wines',
    '16_alkoteka_ru_wines',
    '17_luding_ru_wines',
    '18_russian_wine_master',
    '90_splits/v1',
    '91_manifests',
    '92_reports',
    '99_quarantine'
)

if (-not $MetadataOnly) {
    $requiredDirs += @(
        '00_raw/01_svoe_vino_caseholder',
        '00_raw/02_rvk_telegram',
        '00_raw/03_manual_store',
        '00_raw/04_svoe_vino_web_snapshots',
        '00_raw/05_retail_alcohol_detection',
        '00_raw/06_wine_images_126k',
        '00_raw/07_x_wines',
        '00_raw/08_winesensed',
        '00_raw/09_rf100_wine_labels',
        '00_raw/10_open_food_facts_wine_ru',
        '00_raw/11_mavt_ru_wines',
        '00_raw/12_krasnoe_i_beloe_ru_wines',
        '00_raw/13_winelab_ru_wines',
        '00_raw/14_simplewine_ru_wines',
        '00_raw/15_aromatny_mir_ru_wines',
        '00_raw/16_alkoteka_ru_wines',
        '00_raw/17_luding_ru_wines'
    )
}

foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $datasetRoot $relativePath) -PathType Leaf)) {
        $errors.Add("Missing file: Dataset/${relativePath}")
    }
}

foreach ($relativePath in $requiredDirs) {
    if (-not (Test-Path -LiteralPath (Join-Path $datasetRoot $relativePath) -PathType Container)) {
        $errors.Add("Missing directory: Dataset/${relativePath}")
    }
}

if (Test-Path -LiteralPath (Join-Path $projectRoot 'data')) {
    $errors.Add('Legacy data/ directory still exists; Dataset/ must be the single data root.')
}

$registryPath = Join-Path $datasetRoot 'REGISTRY.yaml'
if (Test-Path -LiteralPath $registryPath) {
    $registry = Get-Content -LiteralPath $registryPath -Raw
    if ($registry -notmatch '(?m)^\s*commercial:\s*false\s*$') {
        $errors.Add('Registry does not fix project_use.commercial to false.')
    }
    foreach ($sourceId in @(
        'caseholder-svoe-vino-2026-09', 'rvk-telegram-2026-09-15',
        'manual-store-captures', 'svoe-vino-live-2026-09-15',
        'retail-alcohol-detection-kaggle', 'wine-images-126k-hf', 'x-wines',
        'winesensed-hf', 'rf100-wine-labels', 'open-food-facts-product-database',
        'mavt-ru-wines-2026-09-15', 'krasnoe-i-beloe-russian-wine-web',
        'winelab-russian-wine-web', 'simplewine-russian-wine-web',
        'aromatny-mir-russian-wine-web', 'alkoteka-russian-wine-web-2026-09-15-krasnodar',
        'luding-russian-wine-web', 'russian-wine-master-2026-09-15.1'
    )) {
        if ($registry -notmatch [regex]::Escape("id: ${sourceId}")) {
            $errors.Add("Registry misses source: ${sourceId}")
        }
    }
}

$sourceDatasetDirs = @(
    '01_svoe_vino_catalog', '02_rvk_telegram', '03_manual_store',
    '04_svoe_vino_web_enrichment', '05_retail_alcohol_detection',
    '06_wine_images_126k', '07_x_wines', '08_winesensed',
    '09_rf100_wine_labels', '10_open_food_facts_wine_ru',
    '11_mavt_ru_wines', '12_krasnoe_i_beloe_ru_wines',
    '13_winelab_ru_wines', '14_simplewine_ru_wines',
    '15_aromatny_mir_ru_wines', '16_alkoteka_ru_wines', '17_luding_ru_wines',
    '18_russian_wine_master'
)
if (-not $MetadataOnly) {
foreach ($datasetDir in $sourceDatasetDirs) {
    foreach ($reviewPath in @(
        'review/needs_verification/queue.jsonl',
        'review/needs_annotation/queue.jsonl',
        'review/STATUS.json'
    )) {
        $candidate = Join-Path $datasetRoot (Join-Path $datasetDir $reviewPath)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $errors.Add("Missing review workspace artifact: Dataset/${datasetDir}/${reviewPath}")
        }
    }
    foreach ($humanState in @('review/verified', 'review/rejected')) {
        $candidate = Join-Path $datasetRoot (Join-Path $datasetDir $humanState)
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            $errors.Add("Missing review workspace directory: Dataset/${datasetDir}/${humanState}")
        }
    }
}
}

if (-not $MetadataOnly) {
$caseRoot = Join-Path $datasetRoot '00_raw/01_svoe_vino_caseholder'
$caseArchives = @(
    if (Test-Path -LiteralPath $caseRoot -PathType Container) {
        Get-ChildItem -LiteralPath $caseRoot -File -Filter '*.zip'
    }
)
$caseArchive = if ($caseArchives.Count -eq 1) { $caseArchives[0].FullName } else { $null }
$telegramRoot = Join-Path $datasetRoot '00_raw/02_rvk_telegram/ChatExport_2026-09-15'
$telegramAnchor = Join-Path $telegramRoot 'messages.html'

if ($caseArchives.Count -ne 1) {
    $errors.Add("Expected exactly one caseholder ZIP in immutable raw zone, found $($caseArchives.Count).")
}
elseif ((Get-Item -LiteralPath $caseArchive).Length -ne 2252013652) {
    $errors.Add('Caseholder archive size differs from intake record.')
}

if (-not (Test-Path -LiteralPath $telegramAnchor -PathType Leaf)) {
    $errors.Add('Telegram messages.html is missing from immutable raw zone.')
}
elseif (@(Get-ChildItem -LiteralPath $telegramRoot -File -Recurse).Count -ne 561) {
    $errors.Add('Telegram raw file count differs from intake record (561).')
}

if (-not $SkipHashes) {
    if ($caseArchive -and (Test-Path -LiteralPath $caseArchive -PathType Leaf)) {
        $actual = (Get-FileHash -LiteralPath $caseArchive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne 'b01a1b9ff65c195ca5cb34d0aaa4d0d447749fbd3ef9fe72b2be37cdef5d92f8') {
            $errors.Add('Caseholder archive SHA-256 differs from intake record.')
        }
    }
    if (Test-Path -LiteralPath $telegramAnchor -PathType Leaf) {
        $actual = (Get-FileHash -LiteralPath $telegramAnchor -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne 'b54b40370c5aa1f7bd5c86c2f53e53e1739eea3e395d855dca220420b8604dde') {
            $errors.Add('Telegram messages.html SHA-256 differs from intake record.')
        }
    }
}
}

$manifestPath = Join-Path $datasetRoot '91_manifests/raw-source-files-v1.0.0.jsonl'
if (-not $MetadataOnly -and (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    $sidecarPath = Join-Path $datasetRoot '91_manifests/raw-source-files-v1.0.0.sha256'
    if (Test-Path -LiteralPath $sidecarPath -PathType Leaf) {
        $storedManifestHash = ((Get-Content -LiteralPath $sidecarPath -Raw).Trim() -split '\s+')[0]
        $actualManifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($storedManifestHash -ne $actualManifestHash) {
            $errors.Add('Raw manifest SHA-256 sidecar is stale or invalid.')
        }
    }
    $records = @(Get-Content -LiteralPath $manifestPath | ForEach-Object { $_ | ConvertFrom-Json })
    if ($records.Count -lt 2910) {
        $errors.Add("Raw manifest record count is $($records.Count), below the audited 2910-file baseline.")
    }
    $duplicates = @($records | Group-Object relative_path | Where-Object Count -gt 1)
    if ($duplicates.Count -gt 0) {
        $errors.Add("Raw manifest contains duplicate relative paths: $($duplicates.Count).")
    }
    foreach ($record in $records) {
        $recordPath = Join-Path $datasetRoot ($record.relative_path -replace '/', [System.IO.Path]::DirectorySeparatorChar)
        if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
            $errors.Add("Manifest references missing file: $($record.relative_path)")
            continue
        }
        $file = Get-Item -LiteralPath $recordPath
        if ($file.Length -ne $record.bytes) {
            $errors.Add("Manifest size mismatch: $($record.relative_path)")
        }
        if ($FullHash) {
            $actual = (Get-FileHash -LiteralPath $recordPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $record.sha256) {
                $errors.Add("Manifest hash mismatch: $($record.relative_path)")
            }
        }
    }
}

if ($errors.Count -gt 0) {
    foreach ($message in $errors) {
        Write-Error $message
    }
    exit 1
}

$hashMode = if ($MetadataOnly) { 'not applicable (Git metadata only)' } elseif ($SkipHashes) { 'skipped' } elseif ($FullHash) { 'all manifest files' } else { 'intake anchors' }
Write-Output 'PASS: Dataset layout and source boundaries are consistent.'
$registeredSources = ([regex]::Matches((Get-Content -LiteralPath $registryPath -Raw), '(?m)^  - id:')).Count
Write-Output "Registered sources: ${registeredSources}"
$manifestRecords = if (Test-Path -LiteralPath $manifestPath -PathType Leaf) { @(Get-Content -LiteralPath $manifestPath).Count } else { 'external package' }
Write-Output "Raw manifest records: ${manifestRecords}"
Write-Output "Hash verification: ${hashMode}"
