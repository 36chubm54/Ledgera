#define MyAppName "Финансовый учет"
#define MyAppInternalName "FinAccountingApp"
#define MyAppPublisher "36chubm54"
#define MyAppExeName "FinAccountingApp.exe"
#define MyBundleDir AddBackslash(SourcePath) + "dist\FinAccountingApp"
#define MyBundleExe MyBundleDir + "\" + MyAppExeName
#define MyIconFile AddBackslash(SourcePath) + "gui\assets\icons\app.ico"

#ifnexist MyBundleExe
  #error "PyInstaller bundle not found. Build dist\FinAccountingApp first."
#endif

#define MyAppVersion GetStringFileInfo(MyBundleExe, "ProductVersion")

[Setup]
AppId={{A6A7D7E2-0DD4-4D44-8E0A-91DA9D76C8D5}
AppName={#MyAppName}
AppVerName={#MyAppName} {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Uninstall removes installed files and shortcuts only; user data remains in AppData.
AppUserModelID=36chubm54.FinAccountingApp
DefaultDirName={autopf}\{#MyAppInternalName}
UsePreviousAppDir=no
UsePreviousLanguage=no
UsePreviousPrivileges=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AlwaysShowDirOnReadyPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#SourcePath}\installer_dist
OutputBaseFilename=FinAccountingApp-{#MyAppVersion}-setup
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#MyBundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
