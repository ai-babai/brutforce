[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$datasetRoot = Join-Path $projectRoot 'Dataset'
$outputPath = Join-Path $datasetRoot '91_manifests/raw-source-files-v1.0.0.jsonl'
$sidecarPath = Join-Path $datasetRoot '91_manifests/raw-source-files-v1.0.0.sha256'
$temporaryPath = "${outputPath}.tmp"

$sources = @(
    [pscustomobject]@{
        SourceId = 'caseholder-svoe-vino-2026-09'
        CaptureId = 'capture_20260915_001'
        RelativeRoot = '00_raw/01_svoe_vino_caseholder'
        Kind = 'single_zip'
    },
    [pscustomobject]@{
        SourceId = 'rvk-telegram-2026-09-15'
        CaptureId = 'capture_20260915_002'
        RelativeRoot = '00_raw/02_rvk_telegram/ChatExport_2026-09-15'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'svoe-vino-live-2026-09-15'
        CaptureId = 'capture_20260915_004'
        RelativeRoot = '00_raw/04_svoe_vino_web_snapshots/2026-09-15'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'retail-alcohol-detection-kaggle'
        CaptureId = 'capture_20260915_005'
        RelativeRoot = '00_raw/05_retail_alcohol_detection'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'wine-images-126k-hf'
        CaptureId = 'capture_20260915_006'
        RelativeRoot = '00_raw/06_wine_images_126k'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'x-wines'
        CaptureId = 'capture_20260915_007'
        RelativeRoot = '00_raw/07_x_wines'
        Kind = 'directory'
        ExcludeParts = @('.git')
    },
    [pscustomobject]@{
        SourceId = 'winesensed-hf'
        CaptureId = 'capture_20260915_008'
        RelativeRoot = '00_raw/08_winesensed'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'rf100-wine-labels'
        CaptureId = 'capture_20260915_009'
        RelativeRoot = '00_raw/09_rf100_wine_labels'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'open-food-facts-product-database'
        CaptureId = 'capture_20260915_010'
        RelativeRoot = '00_raw/10_open_food_facts_wine_ru'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'mavt-ru-wines-2026-09-15'
        CaptureId = 'mavt-capture-20260915'
        RelativeRoot = '00_raw/11_mavt_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'krasnoe-i-beloe-russian-wine-web'
        CaptureId = 'capture_20260915_012'
        RelativeRoot = '00_raw/12_krasnoe_i_beloe_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'winelab-russian-wine-web'
        CaptureId = 'capture_20260915_013'
        RelativeRoot = '00_raw/13_winelab_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'simplewine-russian-wine-web'
        CaptureId = 'capture_20260915_014'
        RelativeRoot = '00_raw/14_simplewine_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'aromatny-mir-russian-wine-web'
        CaptureId = 'amwine_20260915_001'
        RelativeRoot = '00_raw/15_aromatny_mir_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'alkoteka-russian-wine-web-2026-09-15-krasnodar'
        CaptureId = 'capture_alkoteka_517d4364d655df114754'
        RelativeRoot = '00_raw/16_alkoteka_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    },
    [pscustomobject]@{
        SourceId = 'luding-russian-wine-web'
        CaptureId = 'capture_20260915_017'
        RelativeRoot = '00_raw/17_luding_ru_wines'
        Kind = 'directory'
        ExcludeParts = @()
    }
)

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$writer = [System.IO.StreamWriter]::new($temporaryPath, $false, $utf8NoBom)
$recordCount = 0

try {
    foreach ($source in $sources) {
        $sourcePath = Join-Path $datasetRoot ($source.RelativeRoot -replace '/', [System.IO.Path]::DirectorySeparatorChar)
        if (-not (Test-Path -LiteralPath $sourcePath)) {
            throw "Raw source is missing: $($source.RelativeRoot)"
        }

        $files = if ($source.Kind -eq 'file') {
            @(Get-Item -LiteralPath $sourcePath)
        }
        elseif ($source.Kind -eq 'single_zip') {
            $archives = @(Get-ChildItem -LiteralPath $sourcePath -File -Filter '*.zip')
            if ($archives.Count -ne 1) {
                throw "Expected exactly one ZIP in $($source.RelativeRoot), found $($archives.Count)."
            }
            $archives
        }
        else {
            @(Get-ChildItem -LiteralPath $sourcePath -File -Recurse | Where-Object {
                $candidate = $_
                -not @($source.ExcludeParts | Where-Object {
                    $candidate.FullName.Split([System.IO.Path]::DirectorySeparatorChar) -contains $_
                }).Count
            } | Sort-Object FullName)
        }

        foreach ($file in $files) {
            $relativePath = [System.IO.Path]::GetRelativePath($datasetRoot, $file.FullName).Replace('\', '/')
            $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $record = [ordered]@{
                manifest_version = '1.0.0'
                source_id = $source.SourceId
                source_capture_id = $source.CaptureId
                relative_path = $relativePath
                bytes = $file.Length
                sha256 = $hash
                last_write_time_utc = $file.LastWriteTimeUtc.ToString('o')
                received_at = '2026-09-15'
                role = 'raw_source'
            }
            $writer.WriteLine(($record | ConvertTo-Json -Compress))
            $recordCount++
        }
    }
}
finally {
    $writer.Dispose()
}

Move-Item -LiteralPath $temporaryPath -Destination $outputPath -Force
$manifestHash = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText(
    $sidecarPath,
    "${manifestHash}  raw-source-files-v1.0.0.jsonl`n",
    $utf8NoBom
)

Write-Output "PASS: raw source manifest rebuilt."
Write-Output "Records: $recordCount"
Write-Output "Manifest: Dataset/91_manifests/raw-source-files-v1.0.0.jsonl"
Write-Output "SHA-256: $manifestHash"
