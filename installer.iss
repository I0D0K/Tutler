#define MyAppName "Tutler"
#define MyAppVersion "0.1.2"
#define MyAppPublisher "Your Name"
#define MyAppExeName "Tutler.exe"

[Setup]
AppId={{8F3B2A1C-4D5E-4F60-9A7B-1234567890AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Tutler-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
; 允许安装向导弹出语言选择对话框（默认就是 yes，这里显式写出来）
ShowLanguageDialog=yes
; 根据系统 UI 语言决定对话框中预选的语言；匹配不上时回退到 [Languages] 第一项（中文）
LanguageDetectionMethod=uilanguage

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english";           MessagesFile: "compiler:Default.isl"

[CustomMessages]
; 让安装向导中其余中文文案也有英文版本
chinesesimplified.CreateDesktopIcon=创建桌面快捷方式
chinesesimplified.AdditionalTasks=附加任务：
chinesesimplified.LaunchApp=立即运行 {#MyAppName}
english.CreateDesktopIcon=Create a desktop shortcut
english.AdditionalTasks=Additional tasks:
english.LaunchApp=Launch {#MyAppName} now

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked

[Files]
Source: "dist\Tutler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 根据用户在语言选择框中的选择，写入 Tutler 的 QSettings 语言键。
; QSettings("GameShelf", "GameShelf") 在 Windows 上的路径即 HKCU\Software\GameShelf\GameShelf
Root: HKCU; Subkey: "Software\GameShelf\GameShelf"; ValueType: string; ValueName: "language"; ValueData: "zh_CN"; Languages: chinesesimplified; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\GameShelf\GameShelf"; ValueType: string; ValueName: "language"; ValueData: "en_US"; Languages: english;           Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent