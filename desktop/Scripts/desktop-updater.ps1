[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][int]$ParentPid,
    [Parameter(Mandatory = $true)][string]$HealthToken,
    [int]$HealthTimeoutSeconds = 60,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath($InstallRoot)
$installer = [IO.Path]::GetFullPath($InstallerPath)
$updates = Join-Path $root 'Updates'
$backups = Join-Path $root 'Backups\Updates'
$app = Join-Path $root 'App'
$runtime = Join-Path $root 'Runtime'
$healthMarker = Join-Path $updates "health-$HealthToken.ok"
$log = Join-Path $updates 'update-helper.log'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdministrator) {
    if ($Elevated) {
        throw 'Update helper could not obtain administrator privileges.'
    }
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-InstallerPath', ('"{0}"' -f $installer),
        '-InstallRoot', ('"{0}"' -f $root),
        '-ParentPid', $ParentPid,
        '-HealthToken', $HealthToken,
        '-HealthTimeoutSeconds', $HealthTimeoutSeconds,
        '-Elevated'
    )
    try {
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $arguments | Out-Null
        exit 0
    }
    catch {
        Add-Content -LiteralPath $log -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')] Elevation cancelled: $($_.Exception.Message)" -Encoding UTF8
        exit 1
    }
}

function Write-UpdateLog([string]$Message) {
    New-Item -ItemType Directory -Force -Path $updates | Out-Null
    Add-Content -LiteralPath $log -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')] $Message" -Encoding UTF8
}

function Start-StudioAsUser([string]$ActivationUri) {
    Start-Process -FilePath 'explorer.exe' -ArgumentList $ActivationUri | Out-Null
}

function Wait-ProcessExit([int]$ProcessId, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Desktop process $ProcessId did not exit within $TimeoutSeconds seconds."
}

function Wait-ManagedProcessesExit([int]$TimeoutSeconds) {
    $managedRoots = @(
        ([IO.Path]::GetFullPath($app).TrimEnd('\') + '\'),
        ([IO.Path]::GetFullPath($runtime).TrimEnd('\') + '\')
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $managedProcesses = @(Get-CimInstance Win32_Process | Where-Object {
            $executable = $_.ExecutablePath
            $executable -and ($managedRoots | Where-Object {
                $executable.StartsWith($_, [StringComparison]::OrdinalIgnoreCase)
            })
        })
        if ($managedProcesses.Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    $names = $managedProcesses | ForEach-Object { "$($_.Name) ($($_.ProcessId))" }
    throw "Managed processes did not exit: $($names -join ', ')"
}

function Move-DirectoryWithRetry([string]$Source, [string]$Destination, [int]$TimeoutSeconds = 20) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            Move-Item -LiteralPath $Source -Destination $Destination
            return
        }
        catch [IO.IOException], [UnauthorizedAccessException] {
            if ((Get-Date) -ge $deadline) {
                throw
            }
            Start-Sleep -Milliseconds 500
        }
    } while ($true)
}

function Assert-ManagedPath([string]$Path, [string]$ManagedRoot) {
    $candidate = [IO.Path]::GetFullPath($Path)
    $managed = [IO.Path]::GetFullPath($ManagedRoot).TrimEnd('\')
    if (-not ($candidate.Equals($managed, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($managed + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw "Path escaped managed root: $candidate"
    }
}

function Restore-Backup([string]$BackupRoot, [string[]]$Components) {
    Write-UpdateLog "Rolling back from $BackupRoot"
    foreach ($name in $Components) {
        $target = Join-Path $root $name
        $backup = Join-Path $BackupRoot $name
        Assert-ManagedPath $target $root
        if (Test-Path -LiteralPath $backup) {
            if (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Recurse -Force
            }
            Move-DirectoryWithRetry $backup $target
        }
    }
    $oldApp = Join-Path $app 'WukongStudio.exe'
    if (Test-Path -LiteralPath $oldApp) {
        Start-StudioAsUser 'wukongstudio://rollback'
    }
}

Assert-ManagedPath $installer $updates
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "Update installer is missing: $installer"
}
if ($HealthToken -notmatch '^[A-Za-z0-9_-]{16,128}$') {
    throw 'Health token is invalid.'
}

Write-UpdateLog "Waiting for desktop process $ParentPid"
Wait-ProcessExit $ParentPid 90
Wait-ManagedProcessesExit 30

$backupRoot = Join-Path $backups (Get-Date -Format 'yyyyMMdd-HHmmssfff')
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$movedComponents = [Collections.Generic.List[string]]::new()
$updateStarted = $false
try {
    foreach ($name in @('App', 'Runtime')) {
        $source = Join-Path $root $name
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Installed component is missing: $source"
        }
        Move-DirectoryWithRetry $source (Join-Path $backupRoot $name)
        $movedComponents.Add($name)
    }

    Write-UpdateLog "Launching verified installer $installer"
    $updateStarted = $true
    $installerProcess = Start-Process -FilePath $installer -Verb RunAs -PassThru -Wait -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', '/UPDATEONLY',
        "/LOG=$updates\update-installer.log"
    )
    if ($installerProcess.ExitCode -ne 0) {
        throw "Installer exited with code $($installerProcess.ExitCode)."
    }

    $newApp = Join-Path $app 'WukongStudio.exe'
    if (-not (Test-Path -LiteralPath $newApp -PathType Leaf)) {
        throw 'Updated WukongStudio.exe is missing.'
    }
    Remove-Item -LiteralPath $healthMarker -Force -ErrorAction SilentlyContinue
    Write-UpdateLog 'Starting updated app for health validation.'
    Start-StudioAsUser "wukongstudio://health/$HealthToken"
    $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $healthMarker) {
            Write-UpdateLog "Update health validation passed. Backup retained at $backupRoot"
            exit 0
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Updated app did not pass health validation within $HealthTimeoutSeconds seconds."
}
catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    if ($updateStarted) {
        Get-Process WukongStudio -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        try {
            Wait-ManagedProcessesExit 15
        }
        catch {
            Write-UpdateLog "Process cleanup warning: $($_.Exception.Message)"
        }
    }
    if ($movedComponents.Count -gt 0) {
        Restore-Backup $backupRoot $movedComponents.ToArray()
    }
    exit 1
}
