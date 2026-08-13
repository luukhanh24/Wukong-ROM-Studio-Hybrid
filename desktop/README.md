# Wukong ROM Studio Desktop

Native WinUI 3/XAML client for the existing Flask ROM build backend. The
desktop app is unpackaged, x64-only, .NET 8 self-contained and Windows App SDK
self-contained. Flask remains a localhost-only internal API; the primary UI
does not use HTML or WebView2.

## Requirements

- .NET SDK 8.0.417 (locked by `global.json`).
- Visual Studio 2022 with WinUI Application Development, .NET Desktop
  Development, and Windows 10/11 SDK for IDE development.
- Inno Setup 6 only when building the installer.
- Windows 10 2004 or newer, x64.

## Build

```powershell
cd desktop
dotnet restore WukongStudio.sln
dotnet test WukongStudio.Tests\WukongStudio.Tests.csproj -c Release
dotnet build WukongStudio.App\WukongStudio.App.csproj -c Release
```

The executable is named `WukongStudio.exe`. A development build still needs a
prepared `C:\WukongROMStudio\Runtime` tree before the backend can start.

## Publish And Installer

Runtime versions and SHA-256 values are locked in
`Runtime\runtime-lock.json`. Python dependencies are locked with hashes in
`Runtime\requirements.lock`.

```powershell
# Prepare a self-contained staging tree without copying the large MOD folders.
.\Scripts\publish.ps1

# Include TWRP, OFX and copy-image base content, then compile Inno Setup.
.\Scripts\publish.ps1 -IncludeBaseContent -BuildInstaller
```

Generated files are written under `desktop\artifacts` and are ignored by Git.
The default installer output is:

```text
desktop\artifacts\installer\WukongStudio-Setup-x64-1.0.0-unsigned.exe
```

The installer always targets `C:\WukongROMStudio`. It installs `App` and
`Runtime` as read/execute content and grants normal users Modify permission
only to Content/Data/Workspace/output/temp/log/update/backup directories.
Normal uninstall preserves user data. Full removal is an explicit unchecked
option with a second confirmation.

## Content Packs

Build one pack:

```powershell
.\Scripts\build-content-pack.ps1 `
  -SourceDirectory ..\MOD\ColorOS_16.0.7 `
  -Target MOD/ColorOS_16.0.7 `
  -Id coloros-16.0.7 `
  -DisplayName "ColorOS 16.0.7 MOD Pack" `
  -Version 2026.07.1 `
  -OutputPath .\artifacts\content-packs\coloros-16.0.7-2026.07.1.zip
```

Build all known MOD packs with `Scripts\build-all-content-packs.ps1`.
Installation validates schema, target ownership, every file size/SHA-256,
absolute/traversal paths, duplicate paths, and symbolic links before atomic
activation. Previous pack content is backed up under `Backups\ContentPacks`.

## Runtime Layout

Desktop mode is enabled only when the WinUI host passes
`WUKONG_STUDIO_DESKTOP_MODE=1`. All managed paths then resolve under:

```text
C:\WukongROMStudio
```

Without desktop environment variables, `RUN.bat` and `RUN_UI.bat` retain the
legacy source-tree layout.

The device editor keeps the bundled `Runtime\Scripts\devices_sizes.json` as a
read-only template. The first confirmed change creates the writable catalog at
`C:\WukongROMStudio\Data\devices_sizes.json`; every mutation is validated,
backed up under `Backups\devices`, and atomically replaced. Legacy source mode
continues to edit the project-root `devices_sizes.json` directly.

## First Run

The native first-run screen checks write access, disk space, bundled Python,
Java and the backend. It can import legacy content through staging,
install local content-pack ZIPs, and encrypt Telegram credentials with DPAPI
CurrentUser. Legacy import is not selected automatically and never deletes the
source unless the destructive option is explicitly enabled.
