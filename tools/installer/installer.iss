[Setup]
AppId={{74D87A84-83E9-467E-8FBA-05AED3EAC5E3}}
AppName=Expo Studio
SetupIconFile=C:\Users\jbm329\PycharmProjects\expo-studio\src\expo_jbm329\workbench\icon\app.ico
WizardSmallImageFile=C:\Users\jbm329\PycharmProjects\expo-studio\src\expo_jbm329\workbench\splash\wizard-small.bmp
WizardImageFile=C:\Users\jbm329\PycharmProjects\expo-studio\src\expo_jbm329\workbench\splash\wizard.bmp
LicenseFile=C:\Users\jbm329\PycharmProjects\expo-studio\LICENSE.txt
InfoAfterFile=C:\Users\jbm329\PycharmProjects\expo-studio\RELEASE-NOTES.txt
AppVersion=1.0.0
AppPublisher=Jonas Brännström
DefaultDirName={autopf}\Expo Studio
DisableProgramGroupPage=yes
DefaultGroupName=Expo Studio
UninstallDisplayIcon={app}\expo.exe
OutputDir=C:\Users\jbm329\PycharmProjects\expo-studio\release
OutputBaseFilename=ExpoStudio-1.0.0-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
swedish.desktopicon=Skapa genväg på skrivbordet
swedish.launch=Starta Expo Studio
english.desktopicon=Create desktop shortcut
english.launch=Launch Expo Studio

[Tasks]
Name: "desktopicon"; Description: "{cm:desktopicon}"; Flags: unchecked

[Files]
Source: "C:\Users\jbm329\PycharmProjects\expo-studio\dist\expo\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "C:\Users\jbm329\PycharmProjects\expo-studio\README.md"; DestDir: "{app}"
Source: "C:\Users\jbm329\PycharmProjects\expo-studio\CHANGELOG.md"; DestDir: "{app}"
Source: "C:\Users\jbm329\PycharmProjects\expo-studio\LICENSE.txt"; DestDir: "{app}"
Source: "C:\Users\jbm329\PycharmProjects\expo-studio\RELEASE-NOTES.txt"; DestDir: "{app}"


[Icons]
Name: "{group}\Expo Studio"; Filename: "{app}\expo.exe"
Name: "{autodesktop}\Expo Studio"; Filename: "{app}\expo.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\expo.exe"; Description: "{cm:launch}"; Flags: nowait postinstall skipifsilent
