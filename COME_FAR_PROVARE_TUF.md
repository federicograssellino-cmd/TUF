# Come far provare TUF a un amico

TUF oggi è distribuito come **codice sorgente Python** (la cartella `filepilot` dentro lo zip), non come un programma pronto — per questo, prima di mandarlo a qualcuno, va creato tu il pacchetto finale, una volta sola, su un PC Windows (io non posso generarlo da qui, perché deve girare direttamente su Windows).

## Opzione 1 — Due file, doppio click e via (consigliata)

Chi riceve TUF deve avere **solo due file**, sempre insieme nella stessa cartella (es. sulla stessa chiavetta USB):

- **`TUF.exe`** — l'app vera e propria, contiene tutto.
- **`Installa_TUF.exe`** — il piccolo installer, con l'icona di TUF: chi lo riceve fa doppio click **solo su questo**. Copia TUF nel suo profilo utente, crea l'icona sul Desktop e la voce nel menu Start da solo, e alla fine offre di avviare TUF subito. Non serve essere amministratore, non serve installare nulla.

Per crearli:

1. Scompatta lo zip di TUF su un PC Windows (il tuo).
2. Fai doppio click su `Crea_Installer_TUF.bat`, nella cartella principale. Lo script:
   - installa da solo tutto il necessario (incluso PyInstaller);
   - genera dentro una nuova cartella `dist` sia `TUF.exe` che `Installa_TUF.exe`.
3. Prendi **entrambi** i file dentro `dist` (insieme, stessa cartella) e mandali al tuo amico (email, WeTransfer, chiavetta USB...).
4. Lui fa doppio click su `Installa_TUF.exe` — non su `TUF.exe` direttamente — e segue le due domande a schermo (procedere? avviare subito?).

La prima volta la creazione può richiedere qualche minuto ed è l'unico passaggio "tecnico" — dopo, questi due file puoi ridarli a chiunque, quante volte vuoi, anche in futuro (basta rifare questo passaggio ad ogni nuova versione che ti preparo).

### Nota su Windows Defender / SmartScreen

I file `.exe` creati con PyInstaller, la prima volta che li apri su un altro PC, a volte fanno comparire un avviso di Windows Defender ("Windows ha protetto il tuo PC") semplicemente perché non sono firmati digitalmente — è normale per un programma nuovo/non pubblicato, non vuol dire che ci sia qualcosa di sbagliato. Il tuo amico può cliccare "Ulteriori informazioni" → "Esegui comunque" (vale sia per `TUF.exe` che per `Installa_TUF.exe`).

### Nota su "Python non è stato trovato" durante Crea_Installer_TUF.bat

Se lo script si blocca subito con un messaggio tipo *"Python non è stato trovato; eseguire senza argomenti da installare dal Microsoft Store"*, non è un problema di TUF: è un alias finto che Windows crea di suo per reindirizzare al Microsoft Store. Si risolve così, una volta sola:

1. Impostazioni → App → Impostazioni app avanzate → Alias di esecuzione app (o cerca direttamente "alias di esecuzione" nella barra di ricerca di Windows).
2. Disattiva **"Python (default)" (python.exe)** e **"Python (default windowed)" (pythonw.exe)**.
3. Se dopo la disattivazione dice ancora "non trovato", installa Python vero da https://www.python.org/downloads/ spuntando "Add python.exe to PATH" durante l'installazione.
4. Riprova `Crea_Installer_TUF.bat`.

## Opzione 2 — Il modo più veloce per un test rapido, ma richiede Python sul PC dell'amico

Se il tuo amico è già "smanettone" o ha Python installato, e ti serve solo un test veloce prima ancora di preparare i due file dell'Opzione 1:

1. Mandagli lo zip di TUF e fagli scompattare tutto in una cartella.
2. Deve aprire un terminale (Prompt dei comandi) dentro quella cartella ed eseguire:
   ```
   pip install -r requirements.txt
   python -m filepilot.main
   ```
3. TUF si apre.

Scomodo per chi non è pratico di computer: se digita male un comando o non ha Python, si blocca subito. Per chiunque altro, meglio l'Opzione 1.

## Opzione 3 — Un installer "vero", con voce in "App installate" e disinstallatore (avanzata, facoltativa)

L'Opzione 1 copre già la maggior parte dei casi. Questa è solo per chi vuole qualcosa di ancora più simile a un software commerciale: compare in "App installate" di Windows con un disinstallatore vero (invece di dover cancellare a mano la cartella), tramite un tool esterno gratuito (Inno Setup).

1. Prima crea `dist\TUF.exe` come nell'Opzione 1 qui sopra (`Crea_Installer_TUF.bat`).
2. Installa **Inno Setup** (gratuito): https://jrsoftware.org/isdl.php
3. Apri il file `setup_tuf.iss` (nella stessa cartella di `Crea_Installer_TUF.bat`) con Inno Setup Compiler — di solito basta doppio click.
4. Premi **Compile** (F9, o il tasto ▶ in alto).
5. Trovi il risultato in `Output\TUF_Installer.exe`: un unico file, già con l'icona di TUF, da mandare o far scaricare a chiunque — doppio click, procedura guidata, icona sul Desktop creata in automatico.

Va ricompilato (basta ripetere i passaggi 4-5) ad ogni nuova versione — e va aggiornato anche il numero `AppVersion` dentro `setup_tuf.iss`, per farlo coincidere con quello di `filepilot/__init__.py`.

## Nota per i test: guida rapida e tour non ripartono da soli

La guida al primo avvio e il tour interattivo si mostrano **una sola volta per PC**, non ad ogni installazione: TUF ricorda di averli già mostrati in un file di configurazione salvato in `%APPDATA%\FilePilot\config.json`, che resta lì anche reinstallando/aggiornando TUF. Se stai testando tu stesso su un PC dove TUF era già stato avviato prima, guida e tour non ripartiranno da soli — è normale, non un bug: su un PC dove TUF non è mai stato aperto (es. quello di un amico) ripartiranno regolarmente al primo avvio vero.

Per testare di nuovo tu stesso il primo avvio "pulito": chiudi TUF, cancella (o rinomina) la cartella `%APPDATA%\FilePilot`, e riapri TUF.

In qualsiasi momento, comunque, guida e tour restano richiamabili a mano da **Impostazioni → Info → "Guida rapida"** e **"Tour interattivo"**, senza dover cancellare nulla.
