; Inno Setup script for VirtualCom
#define MyAppName "VirtualCom"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "VirtualCom Team"
#define MyAppURL "https://example.local/virtualcom"
#if FileExists("dist\VirtualCom.exe")
  #define MyAppExeName "VirtualCom.exe"
#else
  #if FileExists("dist\vicom.exe")
    #define MyAppExeName "vicom.exe"
  #else
    #error "Missing dist\\VirtualCom.exe or dist\\vicom.exe. Build EXE first (build_installer.bat or PyInstaller)."
  #endif
#endif

[Setup]
AppId={{E4F3F693-896A-45E0-AE14-7CB06F6F6B2A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=VirtualCom_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
