[CmdletBinding()]
param(
    [string]$PackageVersion = '2026-09-17',
    [string]$OutputDirectory = 'artifacts/dataset-transfer/2026-09-17',
    [switch]$InventoryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$global:PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$datasetRoot = Join-Path $repoRoot 'Dataset'
$repoPrefix = $repoRoot.TrimEnd('\') + '\'
$datasetPrefix = $datasetRoot.TrimEnd('\') + '\'

if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    $outputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
}
if (-not $outputRoot.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must stay inside the repository: $outputRoot"
}

$packageName = "Vino-parsed-dataset-$PackageVersion"
$archivePath = Join-Path $outputRoot "$packageName.7z"
$shaPath = "$archivePath.sha256"
$listPath = Join-Path $outputRoot "$packageName.filelist.txt"
$packageManifestPath = Join-Path $datasetRoot '91_manifests/PARSED-DATASET-PACKAGE-MANIFEST.jsonl'
$packageSummaryPath = Join-Path $datasetRoot '91_manifests/PARSED-DATASET-PACKAGE-SUMMARY.json'

function Add-PackageFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [System.Collections.Generic.Dictionary[string, string]]$Map
    )

    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($datasetPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Package file escaped Dataset: $full"
    }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "Referenced package file is missing: $full"
    }
    $relative = $full.Substring($repoPrefix.Length).Replace('\', '/')
    $Map[$relative] = $full
}

function Add-PackageTree {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [System.Collections.Generic.Dictionary[string, string]]$Map
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return
    }
    Get-ChildItem -LiteralPath $Path -Recurse -File -Force |
        Where-Object {
            $_.FullName -notmatch '\\cache\\' -and
            $_.FullName -notmatch '\\__pycache__\\' -and
            $_.Extension -ne '.pyc'
        } |
        ForEach-Object { Add-PackageFile -Path $_.FullName -Map $Map }
}

function Resolve-DatasetReference {
    param([Parameter(Mandatory)][string]$Value)

    $normalized = $Value.Trim().Replace('/', '\')
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return $null
    }
    if ([System.IO.Path]::IsPathRooted($normalized)) {
        return [System.IO.Path]::GetFullPath($normalized)
    }
    if ($normalized.StartsWith('Dataset\', [System.StringComparison]::OrdinalIgnoreCase)) {
        return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $normalized))
    }
    return [System.IO.Path]::GetFullPath((Join-Path $datasetRoot $normalized))
}

$files = [System.Collections.Generic.Dictionary[string, string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)

Get-ChildItem -LiteralPath $datasetRoot -File -Force |
    ForEach-Object { Add-PackageFile -Path $_.FullName -Map $files }

foreach ($number in 1..18) {
    $prefix = '{0:D2}_' -f $number
    $dataset = Get-ChildItem -LiteralPath $datasetRoot -Directory |
        Where-Object Name -Like "$prefix*" |
        Select-Object -First 1
    if ($null -ne $dataset) {
        Add-PackageTree -Path $dataset.FullName -Map $files
    }
}
foreach ($name in @('90_splits', '91_manifests', '92_reports', '99_quarantine')) {
    Add-PackageTree -Path (Join-Path $datasetRoot $name) -Map $files
}
Add-PackageFile -Path (Join-Path $datasetRoot '00_raw/README.md') -Map $files

$referenceTables = @(
    '01_svoe_vino_catalog/tables/media.jsonl',
    '02_rvk_telegram/tables/media.jsonl',
    '02_rvk_telegram/tables/pdf_documents.jsonl',
    '04_svoe_vino_web_enrichment/tables/new_live_media.jsonl',
    '05_retail_alcohol_detection/tables/media.jsonl',
    '07_x_wines/tables/media.jsonl',
    '07_x_wines/tables/slim_media.jsonl',
    '09_rf100_wine_labels/tables/media.jsonl',
    '10_open_food_facts_wine_ru/tables/media.jsonl',
    '11_mavt_ru_wines/tables/media.jsonl',
    '11_mavt_ru_wines/tables/out_of_scope_images.jsonl',
    '15_aromatny_mir_ru_wines/tables/media.jsonl',
    '16_alkoteka_ru_wines/tables/media.jsonl',
    '18_russian_wine_master/tables/media.jsonl'
)
$pathFields = @('relative_path', 'path', 'raw_path')
$referenceRows = 0
$referenceValues = 0
$rawDependencyFiles = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)

foreach ($relativeTable in $referenceTables) {
    $tablePath = Join-Path $datasetRoot $relativeTable
    if (-not (Test-Path -LiteralPath $tablePath -PathType Leaf)) {
        throw "Required reference table is missing: $relativeTable"
    }
    foreach ($line in [System.IO.File]::ReadLines($tablePath, [System.Text.UTF8Encoding]::new($false))) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $row = $line | ConvertFrom-Json
        $referenceRows++
        $values = [System.Collections.Generic.List[string]]::new()
        foreach ($field in $pathFields) {
            $property = $row.PSObject.Properties[$field]
            if ($null -ne $property -and $property.Value -is [string]) {
                $values.Add($property.Value)
            }
        }
        $rawPaths = $row.PSObject.Properties['raw_paths']
        if ($null -ne $rawPaths -and $null -ne $rawPaths.Value) {
            foreach ($value in @($rawPaths.Value)) {
                if ($value -is [string]) {
                    $values.Add($value)
                }
            }
        }
        foreach ($value in $values) {
            $referenceValues++
            $resolved = Resolve-DatasetReference -Value $value
            if ($null -eq $resolved) {
                continue
            }
            Add-PackageFile -Path $resolved -Map $files
            if ($resolved.StartsWith((Join-Path $datasetRoot '00_raw').TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
                $null = $rawDependencyFiles.Add($resolved)
            }
        }
    }
}

$files.Remove('Dataset/91_manifests/PARSED-DATASET-PACKAGE-MANIFEST.jsonl') | Out-Null
$files.Remove('Dataset/91_manifests/PARSED-DATASET-PACKAGE-SUMMARY.json') | Out-Null

$sortedPaths = @($files.Keys | Sort-Object)
$totalBytes = [int64](($sortedPaths | ForEach-Object { (Get-Item -LiteralPath $files[$_]).Length } | Measure-Object -Sum).Sum)
$rawBytes = [int64](($rawDependencyFiles | ForEach-Object { (Get-Item -LiteralPath $_).Length } | Measure-Object -Sum).Sum)
$referencedCacheFiles = @($sortedPaths | Where-Object { $_ -match '/cache/' })

$inventory = [ordered]@{
    package_name = $packageName
    payload_files_before_package_metadata = $sortedPaths.Count
    payload_bytes_before_package_metadata = $totalBytes
    selected_raw_dependency_files = $rawDependencyFiles.Count
    selected_raw_dependency_bytes = $rawBytes
    directly_referenced_cache_files = $referencedCacheFiles.Count
    parsed_reference_rows = $referenceRows
    parsed_reference_values = $referenceValues
}

if ($InventoryOnly) {
    $inventory | ConvertTo-Json -Depth 3
    return
}

if ((Test-Path -LiteralPath $archivePath) -or (Test-Path -LiteralPath $shaPath)) {
    throw "Refusing to overwrite an existing dataset artifact: $archivePath"
}

$forbiddenName = '(?i)(^|[._-])(id_rsa|id_ed25519|private[-_]?key|credential|password)([._-]|$)|\.(pem|key)$|(^|\\)\.env($|\.)'
$forbiddenContent = @(
    '-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
    'gh[pousr]_[A-Za-z0-9]{20,}',
    'AKIA[0-9A-Z]{16}'
)
$scanExtensions = @('.md', '.txt', '.json', '.jsonl', '.yaml', '.yml', '.toml', '.csv', '.tsv')
foreach ($relative in $sortedPaths) {
    if ($relative -match $forbiddenName) {
        throw "Secret-like filename is not allowed: $relative"
    }
    $extension = [System.IO.Path]::GetExtension($relative).ToLowerInvariant()
    $source = $files[$relative]
    if ($extension -in $scanExtensions -and (Get-Item -LiteralPath $source).Length -le 16MB) {
        $content = [System.IO.File]::ReadAllText($source)
        foreach ($pattern in $forbiddenContent) {
            if ($content -match $pattern) {
                throw "Secret-like content detected in: $relative"
            }
        }
    }
}

$manifestLines = [System.Collections.Generic.List[string]]::new()
$manifestBytes = [int64]0
foreach ($relative in $sortedPaths) {
    $source = $files[$relative]
    $item = Get-Item -LiteralPath $source
    $manifestBytes += $item.Length
    $record = [ordered]@{
        relative_path = $relative
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifestLines.Add(($record | ConvertTo-Json -Compress))
}
[System.IO.File]::WriteAllLines($packageManifestPath, $manifestLines, [System.Text.UTF8Encoding]::new($false))
$manifestHash = (Get-FileHash -LiteralPath $packageManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()

$summary = [ordered]@{
    package_version = $PackageVersion
    package_name = $packageName
    purpose = 'Internal parsed Vino dataset transfer'
    manifest_records = $sortedPaths.Count
    manifest_payload_bytes = $manifestBytes
    manifest_sha256 = $manifestHash
    selected_raw_dependency_files = $rawDependencyFiles.Count
    selected_raw_dependency_bytes = $rawBytes
    parsed_reference_rows = $referenceRows
    parsed_reference_values = $referenceValues
    raw_policy = 'Only media/PDF files directly referenced by normalized tables, plus 00_raw/README.md'
    directly_referenced_cache_files = $referencedCacheFiles.Count
    cache_policy = 'Excluded by default; directly referenced media retained to avoid broken paths'
    project_files_included = $false
    frozen_split_ready = $false
    usage_scope = 'internal_noncommercial_research_rights_status_per_source'
}
[System.IO.File]::WriteAllText(
    $packageSummaryPath,
    (($summary | ConvertTo-Json -Depth 4) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false)
)

Add-PackageFile -Path $packageManifestPath -Map $files
Add-PackageFile -Path $packageSummaryPath -Map $files
$archivePaths = @($files.Keys | Sort-Object)

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
[System.IO.File]::WriteAllLines($listPath, $archivePaths, [System.Text.UTF8Encoding]::new($false))

$sevenZipCandidates = @(
    'C:\Program Files\7-Zip\7z.exe',
    'C:\Program Files\NVIDIA Corporation\NVIDIA App\7z.exe'
)
$sevenZip = $sevenZipCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if ($null -eq $sevenZip) {
    $command = Get-Command 7z -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw '7-Zip executable was not found'
    }
    $sevenZip = $command.Source
}

Push-Location $repoRoot
try {
    & $sevenZip a '-t7z' '-mx=1' '-mmt=on' '-scsUTF-8' $archivePath ("@$listPath")
    if ($LASTEXITCODE -ne 0) {
        throw "7-Zip archive creation failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

& $sevenZip t $archivePath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "7-Zip integrity test failed with exit code $LASTEXITCODE"
}

$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$sidecarText = "$archiveHash  $([System.IO.Path]::GetFileName($archivePath))$([Environment]::NewLine)"
$temporarySidecar = Join-Path $outputRoot "$packageName.sha256.tmp"
[System.IO.File]::WriteAllText($temporarySidecar, $sidecarText, [System.Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporarySidecar -Destination $shaPath
$writtenHash = ((Get-Content -LiteralPath $shaPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($writtenHash -ne $archiveHash) {
    throw 'SHA-256 sidecar verification failed after writing'
}

[ordered]@{
    archive = $archivePath
    archive_bytes = (Get-Item -LiteralPath $archivePath).Length
    archive_sha256 = $archiveHash
    archive_entries = $archivePaths.Count
    manifest_records = $sortedPaths.Count
    manifest_payload_bytes = $manifestBytes
    selected_raw_dependency_files = $rawDependencyFiles.Count
    directly_referenced_cache_files = $referencedCacheFiles.Count
    integrity_test = 'passed'
    secret_scan = 'passed'
} | ConvertTo-Json -Depth 3
