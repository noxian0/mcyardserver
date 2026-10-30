; Build with scripts/build_installer.py after scripts/build_windows.py.
#ifndef SourceRoot
  #define SourceRoot ".."
#endif
#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif

[Setup]
AppId={{7FE9EB78-3EA9-4A2F-91C1-23C41524BF61}
AppName=MCyard Server
AppVersion={#AppVersion}
AppPublisher=noxian0
AppPublisherURL=https://github.com/noxian0/mcyardserver
AppSupportURL=https://github.com/noxian0/mcyardserver/issues
LicenseFile={#SourceRoot}\LICENSE
DefaultDirName={localappdata}\Programs\MCyard Server
DefaultGroupName=MCyard Server
AllowNoIcons=yes
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#SourceRoot}
OutputBaseFilename=MCyard Server Setup
SetupIconFile={#SourceRoot}\resources\app.ico
UninstallDisplayIcon={app}\MCyard Server.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
SetupLogging=yes
; A running manager may own a Minecraft server. Never close it automatically.
CloseApplications=no
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "java25"; Description: "Java 25 (current Minecraft versions)"; GroupDescription: "Install Java if it is missing (requires internet):"
Name: "java21"; Description: "Java 21 (Minecraft 1.20.5 through 1.21.x)"; GroupDescription: "Install Java if it is missing (requires internet):"; Flags: unchecked
Name: "java17"; Description: "Java 17 (Minecraft 1.18 through 1.20.4)"; GroupDescription: "Install Java if it is missing (requires internet):"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\MCyard Server\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MCyard Server"; Filename: "{app}\MCyard Server.exe"; WorkingDir: "{app}"; Check: not WizardNoIcons
Name: "{userdesktop}\MCyard Server"; Filename: "{app}\MCyard Server.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\MCyard Server.exe"; Description: "Open MCyard Server"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent; Check: CanLaunchApp

[Code]
var
  PrerequisiteFailed: Boolean;
  FailedVersions: String;

function CanLaunchApp: Boolean;
begin
  Result := not PrerequisiteFailed;
end;

procedure InstallJava(Major: String);
var
  ResultCode: Integer;
  Started: Boolean;
begin
  if not WizardIsTaskSelected('java' + Major) then
    Exit;
  WizardForm.StatusLabel.Caption := 'Checking and installing Java ' + Major + '...';
  WizardForm.FilenameLabel.Caption := 'An existing compatible runtime will be reused.';
  Log('Checking Java ' + Major);
  Started := Exec(ExpandConstant('{app}\MCyard Server.exe'),
    '--install-java ' + Major, ExpandConstant('{app}'), SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  if (not Started) or (ResultCode <> 0) then
  begin
    PrerequisiteFailed := True;
    if FailedVersions <> '' then
      FailedVersions := FailedVersions + ', ';
    FailedVersions := FailedVersions + Major;
    Log(Format('Java %s setup failed; started=%d, exit=%d', [Major, Ord(Started), ResultCode]));
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallJava('25');
    InstallJava('21');
    InstallJava('17');
    if PrerequisiteFailed then
      SuppressibleMsgBox('MCyard Server is installed, but Java ' + FailedVersions +
        ' could not be set up.' + #13#10 + #13#10 +
        'Check your connection and run Setup again, or install Java from the server creation wizard.' + #13#10 +
        '' + #13#10 + 'Details: ' +
        ExpandConstant('{localappdata}\MCyard Server\prerequisites.log'),
        mbError, MB_OK, IDOK);
  end;
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := 0;
  if PrerequisiteFailed then
    Result := 10;
end;
