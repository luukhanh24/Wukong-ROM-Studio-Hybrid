#define AppName "Wukong ROM Studio"
#define AppVersion "1.0.0"
#ifndef SourceRoot
  #define SourceRoot "..\artifacts\staging\WukongROMStudio"
#endif
#ifndef InstallerOutputDir
  #define InstallerOutputDir "..\artifacts\installer"
#endif
#ifndef InstallerOutputBaseFilename
  #define InstallerOutputBaseFilename "WukongStudio-Setup-x64-1.0.0-unsigned"
#endif

[Setup]
AppId={{B16B5D54-5A03-48FD-9E61-B87CF985E9A7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Wukong ROM Studio
DefaultDirName=C:\WukongROMStudio
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#InstallerOutputDir}
OutputBaseFilename={#InstallerOutputBaseFilename}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\App\WukongStudio.exe
SetupIconFile={#SourceRoot}\App\Assets\WukongStudio.ico
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Dirs]
Name: "{app}"; Permissions: users-readexec
Name: "{app}\Content"; Permissions: users-modify
Name: "{app}\Content\MOD"; Permissions: users-modify
Name: "{app}\Content\STARK"; Permissions: users-modify
Name: "{app}\Content\TWRP"; Permissions: users-modify
Name: "{app}\Content\OFX"; Permissions: users-modify
Name: "{app}\Content\copy-image"; Permissions: users-modify
Name: "{app}\Data"; Permissions: users-modify
Name: "{app}\Data\Jobs"; Permissions: users-modify
Name: "{app}\Data\Recipes"; Permissions: users-modify
Name: "{app}\Data\Secrets"; Permissions: users-modify
Name: "{app}\Workspace"; Permissions: users-modify
Name: "{app}\ROM_BUILD_DONE"; Permissions: users-modify
Name: "{app}\Temp"; Permissions: users-modify
Name: "{app}\Temp\Packages"; Permissions: users-modify
Name: "{app}\Temp\Downloads"; Permissions: users-modify
Name: "{app}\Temp\Extraction"; Permissions: users-modify
Name: "{app}\Logs"; Permissions: users-modify
Name: "{app}\Logs\crash"; Permissions: users-modify
Name: "{app}\Updates"; Permissions: users-modify
Name: "{app}\Backups"; Permissions: users-modify

[Files]
Source: "{#SourceRoot}\App\*"; DestDir: "{app}\App"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\Runtime\*"; DestDir: "{app}\Runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\Content\*"; DestDir: "{app}\Content"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist uninsneveruninstall; Check: IsFreshInstall

[InstallDelete]
Type: filesandordirs; Name: "{app}\App\WebView2"
Type: files; Name: "{app}\Runtime\Config\wk_manager_system_policy.cil"
Type: filesandordirs; Name: "{app}\Runtime\STARK"

[Icons]
Name: "{autoprograms}\Wukong ROM Studio"; Filename: "{app}\App\WukongStudio.exe"; WorkingDir: "{app}\App"; AppUserModelID: "WukongROMStudio.Desktop"
Name: "{autodesktop}\Wukong ROM Studio"; Filename: "{app}\App\WukongStudio.exe"; WorkingDir: "{app}\App"; AppUserModelID: "WukongROMStudio.Desktop"

[Registry]
Root: HKA; Subkey: "Software\Classes\wukongstudio"; ValueType: string; ValueName: ""; ValueData: "URL:Wukong ROM Studio Protocol"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\wukongstudio"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\wukongstudio\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\App\WukongStudio.exe,0"
Root: HKA; Subkey: "Software\Classes\wukongstudio\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\App\WukongStudio.exe"" ""%1"""

[Run]
Filename: "{sys}\icacls.exe"; Parameters: """{app}\App"" /reset /T /C"; Flags: runhidden waituntilterminated
Filename: "{sys}\icacls.exe"; Parameters: """{app}\App"" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX"; Flags: runhidden waituntilterminated
Filename: "{sys}\icacls.exe"; Parameters: """{app}\Runtime"" /reset /T /C"; Flags: runhidden waituntilterminated
Filename: "{sys}\icacls.exe"; Parameters: """{app}\Runtime"" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX"; Flags: runhidden waituntilterminated
Filename: "{sys}\icacls.exe"; Parameters: """{app}\Content\STARK"" /grant:r *S-1-5-32-545:(OI)(CI)M"; Flags: runhidden waituntilterminated
Filename: "{sys}\icacls.exe"; Parameters: """{app}\Runtime\Flash_script"" /grant:r *S-1-5-32-545:(OI)(CI)M"; Flags: runhidden waituntilterminated
Filename: "{app}\App\WukongStudio.exe"; Description: "Khởi động Wukong ROM Studio"; Flags: postinstall nowait skipifsilent runasoriginaluser

[Code]
var
  RemoveAllDataCheckBox: TNewCheckBox;
  WasExistingInstall: Boolean;

function IsFreshInstall(): Boolean;
begin
  Result := not WasExistingInstall;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  OldStark: String;
  NewStark: String;
  BackupStark: String;
begin
  Result := '';
  WasExistingInstall := FileExists(ExpandConstant('{app}\App\WukongStudio.exe'));
  OldStark := ExpandConstant('{app}\Runtime\STARK');
  NewStark := ExpandConstant('{app}\Content\STARK');
  if DirExists(OldStark) then
  begin
    if not DirExists(NewStark) then
    begin
      ForceDirectories(ExpandConstant('{app}\Content'));
      if not RenameFile(OldStark, NewStark) then
        Result := 'Không thể chuyển dữ liệu STARK cũ sang Content\STARK. ' +
          'Hãy đóng Wukong ROM Studio và thử cài đặt lại.';
    end
    else
    begin
      ForceDirectories(ExpandConstant('{app}\Backups'));
      BackupStark := ExpandConstant('{app}\Backups\runtime-stark-retired-') +
        GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
      if not RenameFile(OldStark, BackupStark) then
        Result := 'Không thể lưu bản sao Runtime\STARK cũ vào Backups. ' +
          'Hãy đóng Wukong ROM Studio và thử cài đặt lại.';
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

procedure InitializeUninstallProgressForm();
begin
  RemoveAllDataCheckBox := TNewCheckBox.Create(UninstallProgressForm);
  RemoveAllDataCheckBox.Parent := UninstallProgressForm.InnerPage;
  RemoveAllDataCheckBox.Left := UninstallProgressForm.StatusLabel.Left;
  RemoveAllDataCheckBox.Top := UninstallProgressForm.StatusLabel.Top + ScaleY(42);
  RemoveAllDataCheckBox.Width := UninstallProgressForm.InnerPage.ClientWidth - ScaleX(32);
  RemoveAllDataCheckBox.Height := ScaleY(34);
  RemoveAllDataCheckBox.Caption := 'Xóa toàn bộ C:\WukongROMStudio (Content, Data, Workspace, ROM và Logs)';
  RemoveAllDataCheckBox.Checked := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and RemoveAllDataCheckBox.Checked then
  begin
    if MsgBox(
      'Xác nhận xóa vĩnh viễn toàn bộ dữ liệu trong C:\WukongROMStudio?',
      mbConfirmation,
      MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{app}'), True, True, True);
    end;
  end;
end;
