; RevisorJudicial_Installer.iss

#define MyAppName "Revisor Judicial"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Cordoba y Abogados SAS"
#define MyAppURL "https://cordobayabogados.com"
#define MyAppExeName "RevisorJudicial.exe"

[Setup]
AppId={{8B3F3D2A-4A7E-4C8F-9B1A-2D3E4F5A6B7C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

SetupIconFile=resources\icons\icono.ico

OutputDir=Output
OutputBaseFilename=RevisorJudicial_Setup_v{#MyAppVersion}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

DisableProgramGroupPage=yes
DisableReadyPage=no
DisableWelcomePage=no

MinVersion=10.0

LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\RevisorJudicial\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "resources\warp\Cloudflare_WARP_Release-x64.msi"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
; Sin IconFilename: usa el icono embebido en el .exe (siempre en sync)
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "msiexec.exe"; Parameters: "/i ""{tmp}\Cloudflare_WARP_Release-x64.msi"" /qn /norestart ACCEPTED_TOS=1"; StatusMsg: "Instalando Cloudflare WARP (opcional, 30 segundos)..."; Flags: runhidden waituntilterminated; Check: IsAdmin

Filename: "{app}\{#MyAppExeName}"; Description: "Lanzar {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\capturas"
Type: filesandordirs; Name: "{app}\busquedas_anteriores"
Type: filesandordirs; Name: "{app}\respaldos_radicados"
Type: filesandordirs; Name: "{app}\excels_pendientes"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function ChromeEstaInstalado(): Boolean;
var
  Ruta: String;
begin
  Result := False;

  if RegQueryStringValue(
      HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
      '', Ruta) then
  begin
    if FileExists(Ruta) then
    begin
      Result := True;
      Exit;
    end;
  end;

  if RegQueryStringValue(
      HKLM, 'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
      '', Ruta) then
  begin
    if FileExists(Ruta) then
    begin
      Result := True;
      Exit;
    end;
  end;

  if RegQueryStringValue(
      HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
      '', Ruta) then
  begin
    if FileExists(Ruta) then
    begin
      Result := True;
      Exit;
    end;
  end;

  if FileExists(ExpandConstant('{pf64}\Google\Chrome\Application\chrome.exe')) then
  begin
    Result := True;
    Exit;
  end;

  if FileExists(ExpandConstant('{pf32}\Google\Chrome\Application\chrome.exe')) then
  begin
    Result := True;
    Exit;
  end;

  if FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe')) then
  begin
    Result := True;
    Exit;
  end;
end;


function InitializeSetup(): Boolean;
var
  Mensaje: String;
begin
  Result := True;

  if not ChromeEstaInstalado() then
  begin
    Mensaje := 'No se detecto Google Chrome instalado en tu computador.' + Chr(13) + Chr(10) +
               Chr(13) + Chr(10) +
               'Revisor Judicial lo necesita para funcionar.' + Chr(13) + Chr(10) +
               Chr(13) + Chr(10) +
               'Deseas continuar de todos modos?' + Chr(13) + Chr(10) +
               '(Puedes instalar Chrome despues desde google.com/chrome)';
    if MsgBox(Mensaje, mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;


function NextButtonClick(CurPageID: Integer): Boolean;
var
  Mensaje: String;
begin
  Result := True;

  if CurPageID = wpReady then
  begin
    if not IsAdmin then
    begin
      Mensaje := 'No estas ejecutando el instalador como administrador.' + Chr(13) + Chr(10) +
                 Chr(13) + Chr(10) +
                 'Revisor Judicial se instalara correctamente, pero Cloudflare WARP ' +
                 'NO se podra instalar automaticamente.' + Chr(13) + Chr(10) +
                 Chr(13) + Chr(10) +
                 'WARP mejora la estabilidad de las consultas evitando bloqueos del ' +
                 'portal de la Rama Judicial.' + Chr(13) + Chr(10) +
                 Chr(13) + Chr(10) +
                 'Puedes instalarlo mas tarde desde:' + Chr(13) + Chr(10) +
                 '   Configuracion - Estabilidad de consultas' + Chr(13) + Chr(10) +
                 Chr(13) + Chr(10) +
                 'Deseas continuar sin instalar WARP?' + Chr(13) + Chr(10) +
                 '(Pulsa NO para cerrar y volver a ejecutar como administrador)';
      if MsgBox(Mensaje, mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
      end;
    end;
  end;
end;