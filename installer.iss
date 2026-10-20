#define MyAppName "CLI Conductor"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "CLI Conductor"
#define MyAppURL "https://example.com"
#define MyAppExeName "conductor.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\CLIConductor
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=CLIConductor-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "addtopath"; Description: "Add conductor to PATH (user)"; GroupDescription: "Environment:"; Flags: checkedonce

[Files]
Source: "dist\conductor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CLI Conductor Dashboard"; Filename: "{app}\{#MyAppExeName}"; Parameters: "ui"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\CLI Conductor"; Filename: "{app}\{#MyAppExeName}"; Parameters: "ui"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "doctor"; Description: "Run doctor"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  WM_SETTINGCHANGE = $001A;

function NeedGit(): Boolean;
var
  ResultCode: Integer;
begin
  if not Exec('cmd.exe', '/c git --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := False
  else
    Result := (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Path: String;
  AppDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('addtopath') then
    begin
      if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path) then
      begin
        AppDir := ExpandConstant('{app}');
        if Pos(AppDir, Path) = 0 then
        begin
          if (Path <> '') and (Path[Length(Path)] <> ';') then
            Path := Path + ';';
          Path := Path + AppDir;
          RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path);
        end;
      end;
    end;
    if not NeedGit() then
    begin
      MsgBox('Git for Windows was not detected. CLI Conductor requires git for worktree isolation. Please install Git for Windows from https://git-scm.com/download/win and re-run conductor doctor.', mbInformation, MB_OK);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Path: String;
  AppDir: String;
  P: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path) then
    begin
      AppDir := ExpandConstant('{app}');
      P := Pos(AppDir, Path);
      if P > 0 then
      begin
        Delete(Path, P, Length(AppDir));
        // remove trailing semicolon
        if (P <= Length(Path)) and (Path[P] = ';') then
          Delete(Path, P, 1);
        RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path);
      end;
    end;
  end;
end;