; ============================================================
;  Meeting Recorder LLT — Inno Setup Installer Script
;  Skapar MeetingRecorderLLT-Setup.exe
; ============================================================

#define AppName "Meeting Recorder LLT"
#define AppVersion "1.0.0"
#define AppPublisher "Liljedahl Advisory AB"
#define AppURL "https://liljedahladvisory.se"
#define AppExeName "Meeting Recorder LLT.exe"

[Setup]
AppId={{A3F2C1B4-8E7D-4F9A-B2C3-D4E5F6A7B8C9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=MeetingRecorderLLT-Setup
SetupIconFile=MeetingRecorder.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "swedish"; MessagesFile: "compiler:Languages\Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Skapa genväg på skrivbordet"; GroupDescription: "Ytterligare ikoner:"; Flags: unchecked
Name: "startmenuicon"; Description: "Skapa genväg i startmenyn"; GroupDescription: "Ytterligare ikoner:"; Flags: checked

[Files]
; Main app (all files from PyInstaller output)
Source: "dist\Meeting Recorder LLT\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Starta {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\MeetingRecorderLLT"
