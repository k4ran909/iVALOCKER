; iVALOCKER installer (Inno Setup 6) - https://jrsoftware.org/isinfo.php
;
; Don't compile this directly; run:   python install_and_build/build.py --installer
; (it builds dist\iVALOCKER\ first and passes the version in).

#define AppName "iVALOCKER"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "k4ran909"
#define AppURL "https://github.com/k4ran909/iVALOCKER"
#define AppExeName "iVALOCKER.exe"

[Setup]
; AppId identifies the app for upgrades and uninstall. Never change it.
AppId={{6E3B9A52-1C4F-4D8E-9B27-5A0F3C8D71E4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; One-click install: no questions, no admin prompt. Installs for the current user
; (%LOCALAPPDATA%\Programs\iVALOCKER). Admins can run "setup.exe /ALLUSERS" for Program Files.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
OutputDir=..\dist
OutputBaseFilename=iVALOCKER_Setup_{#AppVersion}
SetupIconFile=..\web\favicon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Close a running iVALOCKER before installing / uninstalling (same mutex the app uses).
AppMutex=Local\iVALOCKER_k4ran909_single_instance
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\iVALOCKER\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove files from older versions so nothing stale is left behind on upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autoprograms}\{#AppName} (debug log)"; Filename: "{app}\{#AppExeName}"; Parameters: "--debug"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
; Start iVALOCKER as soon as it's installed.
Filename: "{app}\{#AppExeName}"; Flags: nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Ask whether to remove saved settings (favorites, backup agent, ...) on uninstall.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Do you also want to delete your iVALOCKER settings?', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
