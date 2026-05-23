#define MyAppName "Ledgera"
#define MyAppInternalName "Ledgera"
#define MyAppInstallDirName "Ledgera"
#define MyAppPublisher "36chubm54"
#define MyAppExeName "Ledgera.exe"
#define MyBundleDir AddBackslash(SourcePath) + "dist\Ledgera"
#define MyBundleExe MyBundleDir + "\" + MyAppExeName
#define MyIconFile AddBackslash(SourcePath) + "gui\assets\icons\app.ico"

#ifnexist MyBundleExe
  #error "PyInstaller bundle not found. Build dist\Ledgera first."
#endif

#define MyAppVersion GetStringFileInfo(MyBundleExe, "ProductVersion")
#define MyAppVersionNumbers GetVersionNumbersString(MyBundleExe)

[Setup]
AppId={{A6A7D7E2-0DD4-4D44-8E0A-91DA9D76C8D5}
AppName={#MyAppName}
AppVerName={#MyAppName} {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Uninstall removes installed files and shortcuts only; user data remains in AppData.
DefaultDirName={autopf}\{#MyAppInstallDirName}
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
OutputBaseFilename=Ledgera-{#MyAppVersion}-setup
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersionNumbers}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#MyBundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{app}\FinAccountingApp.exe"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
