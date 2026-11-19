; Inno-Setup-Skript fuer den Windows-Installer von AutoApplication.
; Build: ISCC.exe /DAppVersion=1.0.15 packaging\installer.iss
; Erwartet das PyInstaller-Ergebnis in dist\AutoApplication (build_windows.ps1).

#ifndef AppVersion
  #define AppVersion "1.0.15"
#endif

#define AppName "AutoApplication"
#define AppPublisher "AutoApplication"
#define AppExe "AutoApplication.exe"

[Setup]
; Eigene AppId: Updates ersetzen die bestehende Installation.
AppId={{B7A61E2C-1D4F-4E2A-9A3B-6F0C2D8E4A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AutoApplication-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=autoapplication.ico
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\AutoApplication\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Ohne skipifsilent: auch das stille Update oeffnet AutoApplication nach dem
; Einbau wieder. Der Aufruf laeuft ohne Warten, der Installer endet danach.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait
