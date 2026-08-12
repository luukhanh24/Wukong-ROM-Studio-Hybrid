[CmdletBinding()]
param(
    [string]$SourceRoot = '',
    [string]$OutputRoot = '',
    [string]$PackVersion = '2026.07.1'
)

$ErrorActionPreference = 'Stop'
$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$SourceRoot = if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
} else {
    $SourceRoot
}
$OutputRoot = if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    Join-Path $scriptRoot '..\artifacts\content-packs'
} else {
    $OutputRoot
}
$builder = Join-Path $scriptRoot 'build-content-pack.ps1'
$packs = @(
    @{ Name = 'ColorOS_15.0.1'; Id = 'coloros-15.0.1'; Display = 'ColorOS 15.0.1 MOD Pack' },
    @{ Name = 'ColorOS_16.0.5'; Id = 'coloros-16.0.5'; Display = 'ColorOS 16.0.5 MOD Pack' },
    @{ Name = 'ColorOS_16.0.7'; Id = 'coloros-16.0.7'; Display = 'ColorOS 16.0.7 MOD Pack' },
    @{ Name = 'ColorOS_16.0.8'; Id = 'coloros-16.0.8'; Display = 'ColorOS 16.0.8 MOD Pack' },
    @{ Name = 'RealmeUI_16.0.7'; Id = 'realmeui-16.0.7'; Display = 'RealmeUI 16.0.7 MOD Pack' }
)
foreach ($pack in $packs) {
    & $builder `
        -SourceDirectory (Join-Path $SourceRoot "MOD\$($pack.Name)") `
        -Target "MOD/$($pack.Name)" `
        -Id $pack.Id `
        -DisplayName $pack.Display `
        -Version $PackVersion `
        -OutputPath (Join-Path $OutputRoot "$($pack.Id)-$PackVersion.zip")
}
