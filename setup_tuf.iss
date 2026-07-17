; ============================================================
; setup_tuf.iss — crea un vero installer Windows (TUF_Installer.exe)
; a partire da dist\TUF.exe (generato prima da Crea_Installer_TUF.bat).
;
; COSA SERVE PRIMA DI USARE QUESTO FILE:
;   1. Aver gia' generato dist\TUF.exe con Crea_Installer_TUF.bat (vedi quel
;      file — deve girare senza errori prima di questo passaggio).
;      Crea_Installer_TUF.bat include gia' l'icona di TUF (filepilot/assets/
;      tuf_icon.ico) nell'eseguibile.
;   2. Installare Inno Setup (gratuito): https://jrsoftware.org/isdl.php
;
; COME SI USA:
;   1. Apri questo file (setup_tuf.iss) con Inno Setup Compiler
;      (di solito basta doppio click, se Inno Setup e' installato).
;   2. Premi "Compile" (F9, o il tasto Play in alto).
;   3. Trovi il risultato in Output\TUF_Installer.exe — QUELLO e' il
;      file da mandare/far scaricare a chiunque, gia' con l'icona di
;      TUF: doppio click, procedura guidata, icona sul Desktop creata
;      in automatico, e compare anche in "App installate" di Windows
;      con un disinstallatore vero (a differenza del singolo TUF.exe,
;      che va solo cancellato a mano). Nella cartella di installazione
;      resta un solo file, TUF.exe: Termini e Condizioni e Privacy
;      sono gia' impacchettati dentro, apribili dal programma stesso
;      (Impostazioni > Info).
;
; Va rifatto (ricompilato) ad ogni nuova versione di TUF: aggiorna
; AppVersion qui sotto con lo stesso numero di filepilot/__init__.py.
; ============================================================

#define MyAppName "TideUp File (TUF)"
#define MyAppVersion "0.41"
#define MyAppPublisher "TUF"
#define MyAppExeName "TUF.exe"

[Setup]
AppId={{B6E1B6C1-8B3C-4E9A-9A2F-TUFAPP000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Installazione nel profilo utente: non serve essere amministratore
; ne' cliccare "Si'" su nessun avviso di Windows per installare.
DefaultDirName={localappdata}\Programs\TUF
DefaultGroupName=TUF
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
; Icona del file installer stesso (quella che si vede su TUF_Installer.exe
; prima ancora di aprirlo, in Esplora risorse/sul Desktop) e di tutte le
; pagine della procedura guidata.
SetupIconFile=filepilot\assets\tuf_icon.ico
OutputDir=Output
; RICHIESTA: "il setup chiamarlo installer" — il file finale si chiama
; TUF_Installer.exe invece di TUF_Setup.exe.
OutputBaseFilename=TUF_Installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Se in futuro TUF.exe cresce molto (video/librerie pesanti), questo
; evita un singolo file installer enorme da scompattare in RAM.
DiskSpanning=no

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Spuntata di default: RICHIESTA esplicita "un'icona da tenere sul
; desktop subito dopo l'installazione" — l'utente puo' comunque
; togliere la spunta nella procedura guidata se non la vuole.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; RICHIESTA: "dopo l'estrazione quello e' l'unico file che vedi nella
; cartella" — TUF.exe e' l'UNICA cosa installata: Termini e Condizioni
; e Privacy sono gia' impacchettati DENTRO l'eseguibile da Crea_Installer_TUF.bat
; (--add-data), non copie separate sul disco. Il tasto "Termini e
; Condizioni"/"Privacy" nel programma li apre comunque, estraendoli al
; volo dalla stessa cartella temporanea da cui gira l'app.
Source: "dist\TUF.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offre di avviare TUF appena finita l'installazione, spuntato di
; default (l'utente puo' togliere la spunta nell'ultima schermata).
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
