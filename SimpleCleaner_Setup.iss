; =====================================================================
;  Simple Cleaner - installer script for Inno Setup (6.7 or newer)
;  Put this file in the same folder as:
;     dist\Simple Cleaner ES.exe
;     dist\Simple Cleaner EN.exe
;     Simple_Cleaner_Logo_NOBG.ico
;     wizard_image.png
;     wizard_small.png
;  Then open it with Inno Setup and press F9 (Build > Compile).
;  The installer will be created in the "Output" folder.
; =====================================================================

#define MyAppName      "Simple Cleaner"
#define MyAppVersion   "1.0"
#define MyAppPublisher "Simple Cleaner"
#define MyAppExeName   "Simple Cleaner.exe"

[Setup]
AppId={{3A78585D-7D50-4E37-AEA6-45B9AB06D900}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; Installs for the current user by default (no admin needed). The user can
; choose "for all users" in a dialog at the start.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=Output
OutputBaseFilename=Simple_Cleaner_Setup
SetupIconFile=Simple_Cleaner_Logo_NOBG.ico
Compression=lzma2
SolidCompression=yes

; ---- Language selection: always ask at the start
ShowLanguageDialog=yes
UsePreviousLanguage=no

; ---- Look: dark theme with the app colors (needs Inno Setup 6.7+)
; If the compiler complains about "modern dark", use "modern dynamic".
WizardStyle=modern dark
WizardBackColor=#141414
WizardBackColorDynamicDark=#141414
WizardImageFile=wizard_image.png
WizardImageFileDynamicDark=wizard_image.png
WizardSmallImageFile=wizard_small.png
WizardSmallImageFileDynamicDark=wizard_small.png
WizardImageBackColor=#0C0C0C
WizardImageBackColorDynamicDark=#0C0C0C

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The program installed depends on the language chosen at the start.
; Both are installed with the same name, so shortcuts work the same.
Source: "dist\Simple Cleaner EN.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Languages: english; Flags: ignoreversion
Source: "dist\Simple Cleaner ES.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Languages: spanish; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
