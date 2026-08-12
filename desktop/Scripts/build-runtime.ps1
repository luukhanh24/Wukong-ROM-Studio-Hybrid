[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DestinationRoot,
    [string]$SourceRoot = '',
    [string]$DownloadCache = '',
    [switch]$IncludeBaseContent,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.IO.Compression.FileSystem
$scriptDirectory = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$SourceRoot = if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    (Resolve-Path (Join-Path $scriptDirectory '..\..')).Path
} else {
    $SourceRoot
}
$DownloadCache = if ([string]::IsNullOrWhiteSpace($DownloadCache)) {
    Join-Path $scriptDirectory '..\artifacts\downloads'
} else {
    $DownloadCache
}

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    if (Test-Path -LiteralPath $Destination) {
        $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -eq $Sha256.ToLowerInvariant()) {
            return $Destination
        }
        Remove-Item -LiteralPath $Destination -Force
    }
    $temporary = "$Destination.download"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $temporary
        $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $Sha256.ToLowerInvariant()) {
            throw "SHA-256 mismatch for $Url. Expected $Sha256, got $actual."
        }
        Move-Item -LiteralPath $temporary -Destination $Destination -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
    return $Destination
}

function Copy-Tree {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Required source directory is missing: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source '*') -Destination $Destination -Recurse -Force
    Get-ChildItem -LiteralPath $Destination -Recurse -Directory -Filter '__pycache__' |
        Sort-Object FullName -Descending |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    Get-ChildItem -LiteralPath $Destination -Recurse -File |
        Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

function Assert-FileHashMatch {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path -LiteralPath $Destination)) {
        throw "Staged file is missing: $Destination"
    }
    $sourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    $destinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
    if ($sourceHash -ne $destinationHash) {
        throw "Staged file hash mismatch: $Source -> $Destination"
    }
}

function Expand-ZipClean {
    param([string]$Archive, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    [System.IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

$destination = [IO.Path]::GetFullPath($DestinationRoot)
$source = [IO.Path]::GetFullPath($SourceRoot)
$cache = [IO.Path]::GetFullPath($DownloadCache)
$desktopRoot = [IO.Path]::GetFullPath((Join-Path $scriptDirectory '..'))
$lock = Get-Content -LiteralPath (Join-Path $desktopRoot 'Runtime\runtime-lock.json') -Raw | ConvertFrom-Json

if ($Clean -and (Test-Path -LiteralPath $destination)) {
    if ($destination.Length -lt 10 -or $destination -eq [IO.Path]::GetPathRoot($destination)) {
        throw "Refusing to clean unsafe destination: $destination"
    }
    Remove-Item -LiteralPath $destination -Recurse -Force
}

$paths = @(
    'App', 'Runtime\Python', 'Runtime\Java', 'Runtime\Scripts', 'Runtime\Bin',
    'Runtime\Config', 'Runtime\Flash_script', 'Runtime\STARK', 'Runtime\Web',
    'Content\MOD', 'Content\TWRP', 'Content\OFX', 'Content\copy-image',
    'Data\Jobs', 'Data\Recipes', 'Data\Secrets', 'Workspace', 'ROM_BUILD_DONE',
    'Temp\Packages', 'Temp\Downloads', 'Temp\Extraction', 'Logs\crash',
    'Updates', 'Backups'
)
foreach ($relative in $paths) {
    New-Item -ItemType Directory -Force -Path (Join-Path $destination $relative) | Out-Null
}

$scriptRoot = Join-Path $destination 'Runtime\Scripts'
Get-ChildItem -LiteralPath $source -File -Filter '*.py' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $scriptRoot -Force
}
Copy-Item -LiteralPath (Join-Path $source 'devices_sizes.json') -Destination $scriptRoot -Force
Copy-Item -LiteralPath (Join-Path $scriptDirectory 'desktop-updater.ps1') -Destination $scriptRoot -Force
Copy-Tree (Join-Path $source 'src') (Join-Path $scriptRoot 'src')
Copy-Tree (Join-Path $source 'platform_external_avb-master') (Join-Path $scriptRoot 'platform_external_avb-master')
Copy-Tree (Join-Path $source 'bin') (Join-Path $destination 'Runtime\Bin')
Copy-Tree (Join-Path $source 'config') (Join-Path $destination 'Runtime\Config')
Copy-Tree (Join-Path $source 'Flash_script') (Join-Path $destination 'Runtime\Flash_script')
Copy-Tree (Join-Path $source 'STARK') (Join-Path $destination 'Runtime\STARK')
Copy-Tree (Join-Path $source 'studio_static') (Join-Path $destination 'Runtime\Web')
Copy-Tree (Join-Path $source 'wukong') (Join-Path $scriptRoot 'wukong')
Copy-Tree (Join-Path $source 'tools') (Join-Path $scriptRoot 'tools')
Copy-Tree (Join-Path $source 'content-packs') (Join-Path $scriptRoot 'content-packs')
foreach ($document in @('LICENSE', 'THIRD_PARTY_NOTICES.md', 'HYBRID_SETUP.md', 'LEGACY_PROVENANCE.md')) {
    Copy-Item -LiteralPath (Join-Path $source $document) -Destination $scriptRoot -Force
}

Get-ChildItem -LiteralPath $source -File -Filter '*.py' | ForEach-Object {
    Assert-FileHashMatch $_.FullName (Join-Path $scriptRoot $_.Name)
}

$pythonArchive = Get-VerifiedDownload `
    -Url $lock.python.url `
    -Sha256 $lock.python.sha256 `
    -Destination (Join-Path $cache "python-$($lock.python.version)-embed-amd64.zip")
$pythonRoot = Join-Path $destination 'Runtime\Python'
Expand-ZipClean $pythonArchive $pythonRoot
$pth = Get-ChildItem -LiteralPath $pythonRoot -Filter 'python*._pth' | Select-Object -First 1
if (-not $pth) {
    throw 'Python embedded _pth file is missing.'
}
$pthContent = Get-Content -LiteralPath $pth.FullName
$pthContent = $pthContent | Where-Object { $_ -notin @('..\Scripts', 'Lib\site-packages', 'import site', '#import site') }
$pthContent += '..\Scripts'
$pthContent += 'Lib\site-packages'
$pthContent += 'import site'
Set-Content -LiteralPath $pth.FullName -Value $pthContent -Encoding ASCII
$sitePackages = Join-Path $pythonRoot 'Lib\site-packages'
New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null
$requirementsLock = Join-Path $desktopRoot 'Runtime\requirements.lock'
& python -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: --target $sitePackages -r $requirementsLock
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install locked Python dependencies.'
}

$javaArchive = Get-VerifiedDownload `
    -Url $lock.java.url `
    -Sha256 $lock.java.sha256 `
    -Destination (Join-Path $cache "temurin-jre-$($lock.java.version)-windows-x64.zip")
$javaExtract = Join-Path $destination 'Temp\Extraction\java-runtime'
Expand-ZipClean $javaArchive $javaExtract
$javaHome = Get-ChildItem -LiteralPath $javaExtract -Directory | Select-Object -First 1
if (-not $javaHome -or -not (Test-Path -LiteralPath (Join-Path $javaHome.FullName 'bin\java.exe'))) {
    throw 'Temurin archive does not contain a valid JRE.'
}
Copy-Tree $javaHome.FullName (Join-Path $destination 'Runtime\Java')
Remove-Item -LiteralPath $javaExtract -Recurse -Force

$rcloneArchive = Get-VerifiedDownload `
    -Url $lock.rclone.url `
    -Sha256 $lock.rclone.sha256 `
    -Destination (Join-Path $cache "rclone-$($lock.rclone.version)-windows-amd64.zip")
$rcloneExtract = Join-Path $destination 'Temp\Extraction\rclone-runtime'
Expand-ZipClean $rcloneArchive $rcloneExtract
$rcloneExecutable = Get-ChildItem -LiteralPath $rcloneExtract -Recurse -File -Filter 'rclone.exe' | Select-Object -First 1
if (-not $rcloneExecutable) {
    throw 'rclone archive does not contain rclone.exe.'
}
Copy-Item -LiteralPath $rcloneExecutable.FullName -Destination (Join-Path $destination 'Runtime\Bin\Windows\AMD64\rclone.exe') -Force
Remove-Item -LiteralPath $rcloneExtract -Recurse -Force

if ($IncludeBaseContent) {
    Copy-Tree (Join-Path $source 'TWRP') (Join-Path $destination 'Content\TWRP')
    Copy-Tree (Join-Path $source 'OFX') (Join-Path $destination 'Content\OFX')
    Copy-Tree (Join-Path $source 'copy-image') (Join-Path $destination 'Content\copy-image')
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
& (Join-Path $pythonRoot 'python.exe') -c "import flask, requests, google.protobuf, zstandard; import studio_server, studio_core, wukong; print('runtime smoke import: OK')"
if ($LASTEXITCODE -ne 0) {
    throw 'Bundled Python smoke import failed.'
}

Write-Host "Runtime staged at $destination"
