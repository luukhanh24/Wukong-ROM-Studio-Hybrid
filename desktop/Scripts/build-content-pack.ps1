[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourceDirectory,
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string]$Id,
    [Parameter(Mandatory = $true)][string]$DisplayName,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$MinStudioVersion = '1.0.0',
    [string]$Type = 'mod-version'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-RelativeFilePath {
    param([string]$BasePath, [string]$FilePath)
    $baseFull = [IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $baseUri = [Uri]::new($baseFull)
    $fileUri = [Uri]::new([IO.Path]::GetFullPath($FilePath))
    return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($fileUri).ToString()).Replace('/', '\')
}

$source = [IO.Path]::GetFullPath($SourceDirectory)
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Content source does not exist: $source"
}
if ([IO.Path]::IsPathRooted($Target) -or $Target -match '(^|[\\/])\.\.([\\/]|$)') {
    throw "Unsafe content target: $Target"
}

$output = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $output) | Out-Null
$temporary = "$output.tmp"
if (Test-Path -LiteralPath $temporary) {
    Remove-Item -LiteralPath $temporary -Force
}

$files = @()
Get-ChildItem -LiteralPath $source -Recurse -File | Sort-Object FullName | ForEach-Object {
    if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Content pack cannot include a reparse point: $($_.FullName)"
    }
    $relative = (Get-RelativeFilePath $source $_.FullName).Replace('\', '/')
    $packPath = ($Target.Trim('/\') + '/' + $relative).Replace('\', '/')
    $files += [ordered]@{
        path = $packPath
        size = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
if ($files.Count -eq 0) {
    throw 'Content pack source is empty.'
}

$manifest = [ordered]@{
    schemaVersion = 1
    id = $Id
    displayName = $DisplayName
    version = $Version
    minStudioVersion = $MinStudioVersion
    type = $Type
    target = $Target.Replace('\', '/')
    files = $files
}

$stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew)
try {
    $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File | Sort-Object FullName) {
            $relative = (Get-RelativeFilePath $source $file.FullName).Replace('\', '/')
            $entryName = ($Target.Trim('/\') + '/' + $relative).Replace('\', '/')
            $entry = $archive.CreateEntry($entryName, [IO.Compression.CompressionLevel]::Optimal)
            $input = [IO.File]::OpenRead($file.FullName)
            $outputStream = $entry.Open()
            try { $input.CopyTo($outputStream) }
            finally { $outputStream.Dispose(); $input.Dispose() }
        }
        $manifestEntry = $archive.CreateEntry('content-pack.json', [IO.Compression.CompressionLevel]::Optimal)
        $writer = [IO.StreamWriter]::new($manifestEntry.Open(), [Text.UTF8Encoding]::new($false))
        try { $writer.Write(($manifest | ConvertTo-Json -Depth 8)) }
        finally { $writer.Dispose() }
    }
    finally { $archive.Dispose() }
}
finally { $stream.Dispose() }

Move-Item -LiteralPath $temporary -Destination $output -Force
Write-Host "Created $output"
Write-Host "SHA-256: $((Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant())"
