#ifndef PayloadDir
  #error PayloadDir must be supplied by build.py
#endif
[Setup]
AppId={{B2D41370-CC83-47E6-89C7-82B736D7C726}
AppName=LMT Studio V3
AppVersion=3.3.0
AppPublisher=LMT Studio
DefaultDirName={localappdata}\Programs\LMTStudioV3
DefaultGroupName=LMT Studio V3
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..\dist\windows
OutputBaseFilename=LMT-Studio-V3-Setup-x64
Compression=lzma2/fast
SolidCompression=yes
UninstallDisplayIcon={app}\LMTStudioV3.exe
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start V3 after Windows sign-in"; GroupDescription: "Background work:"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LMT Studio V3"; Filename: "{app}\LMTStudioV3.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\LMT Studio V3"; Filename: "{app}\LMTStudioV3.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LMTStudioV3"; ValueData: """{app}\LMTStudioV3.exe"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\LMTStudioV3.exe"; Description: "Set up and open LMT Studio V3"; Flags: nowait postinstall skipifsilent
