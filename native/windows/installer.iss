; Build only on CI. No elevation, auto-launch, or bundled browser runtime.
[Setup]
AppId={{EC2F5547-357B-46B2-AB27-7EF5DA3B07BC}
AppName=Relic
AppVersion={#AppVersion}
AppPublisher=Hongyi Du
DefaultDirName={localappdata}\Programs\Relic
DefaultGroupName=Relic
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Relic-Windows-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\Relic.exe
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Relic"; Filename: "{app}\Relic.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Relic"; Filename: "{app}\Relic.exe"; WorkingDir: "{app}"
