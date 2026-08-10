; ShopMonitor 选品监控 安装包脚本（Inno Setup 6）
#define MyAppName "ShopMonitor 选品监控"
#define MyAppVersion "1.0.0"
#define MyAppExe "启动-选品监控.bat"

[Setup]
AppId={{B0A1C0DE-5EEC-4F52-9A11-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\ShopMonitor
DefaultGroupName=ShopMonitor
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ShopMonitor安装程序
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\assets\logo.ico

[Files]
Source: "..\dist\ShopMonitor分享版\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\ShopMonitor 选品监控"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\assets\logo.ico"; WorkingDir: "{app}"
Name: "{autoprograms}\ShopMonitor\ShopMonitor 选品监控"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\assets\logo.ico"; WorkingDir: "{app}"
Name: "{autoprograms}\ShopMonitor\卸载 ShopMonitor"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "立即启动 ShopMonitor 选品监控"; Flags: nowait postinstall skipifsilent
