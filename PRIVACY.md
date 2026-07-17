# Privacy — TideUp File (TUF)

Questo documento spiega, senza giri di parole, cosa fa e cosa NON fa TUF
con i tuoi dati e i tuoi file. È il documento richiamato dalla Guida
rapida (primo avvio) e da Impostazioni > Info.

TUF è un programma che gira **interamente sul tuo computer**. Non ha un
server proprio, non fa account, non fa telemetria, non tiene una
cronologia di cosa apri o guardi.

## Cosa NON fa mai TUF

- Non salva mai il **contenuto** di nessun file che apri (foto, video,
  documento o altro).
- Non tiene una cronologia di quali file hai aperto o visualizzato.
- Le miniature/anteprime che vedi mentre usi il programma vivono solo
  in memoria: spariscono quando chiudi la finestra, non vengono mai
  scritte su disco in nessuna cache.
- Non manda **mai** i tuoi file, i loro nomi o i percorsi delle
  cartelle online — con le due sole eccezioni volontarie descritte più
  sotto, che riguardano solo dati che scegli tu di condividere.

## Cosa salva TUF, e dove

Tutto resta **in locale**, dentro una cartella di configurazione sul
tuo PC (su Windows: `%APPDATA%\FilePilot`). Nello specifico:

- **config.json** — le cartelle di destinazione che hai configurato
  (nome, percorso, numero, scorciatoia), il loro ordine, i formati di
  file abilitati, le tue scorciatoie personalizzate, il livello di
  dimensione delle cartelle, l'ordinamento scelto, il percorso
  dell'ultima cartella sorgente aperta (solo il percorso, non un
  elenco di file), e la data di accettazione dei Termini e Condizioni.
- **Cestino interno** (`%APPDATA%\FilePilot\Cestino`) — quando elimini
  un file, viene spostato qui (non copiato, non "loggato": è lo stesso
  file, recuperabile con Undo finché non chiudi il programma). Alla
  chiusura, TUF sposta il contenuto residuo nel Cestino di Windows.
- **crash_log.txt** — scritto solo se il programma va in errore
  inatteso, per poter correggere il problema. Non è un log di utilizzo:
  resta vuoto finché non capita un errore.
- **feedback.txt** / **format_requests.txt** — contengono solo il
  testo che scrivi volontariamente nei box "Hai altri consigli?" e "Ti
  serve un formato che non c'è?" in Impostazioni, salvato come backup
  locale oltre all'eventuale invio (vedi sotto).

Nessuno di questi file lascia il tuo computer da solo.

## Le due eccezioni esplicite

TUF ha solo due funzioni che mandano qualcosa online, **sempre solo
quando le usi volontariamente**:

1. **Comando vocale (facoltativo)** — se lo attivi, l'audio del
   microfono viene mandato al servizio gratuito di riconoscimento
   vocale di Google, per trascriverlo in testo. Viene mandato solo
   l'audio mentre il comando vocale è attivo, mai un elenco di file o
   altri dati. È del tutto facoltativo: TUF funziona identico anche
   solo con mouse e tastiera.
2. **Feedback e suggerimenti** — il testo che scrivi nei box "Hai
   altri consigli?" o "Ti serve un formato che non c'è?" viene mandato
   a un bot Telegram dello sviluppatore, così arriva subito senza
   bisogno di configurare un'email. Viene mandato **solo** quel testo
   (più nome/email se li compili tu): mai nomi di file, percorsi o
   cronologia d'uso.

## Controllo aggiornamenti

All'avvio, TUF controlla in background se su GitHub è disponibile una
versione più recente (una normale richiesta pubblica all'API di
GitHub). Non viene mandato nessun dato personale né alcun
identificativo del tuo PC: il confronto tra la versione installata e
l'ultima disponibile avviene in locale. Se manca la connessione, il
controllo fallisce in silenzio e TUF continua a funzionare come prima.

## Librerie di terze parti

TUF si appoggia ad alcune librerie open source per funzionalità come
l'apertura di anteprime, il riconoscimento dei duplicati e il Cestino
di sistema (PySide6, OpenCV, Pillow, PyMuPDF, python-docx, openpyxl,
imagehash, watchdog, SpeechRecognition, sounddevice, numpy,
Send2Trash). Vengono usate solo in locale per far funzionare il
programma: nessuna di loro manda dati online per conto proprio, a
parte SpeechRecognition, e solo per la funzione descritta sopra.

## Contatti

Per domande su questo documento o sui tuoi dati, puoi scrivere allo
sviluppatore tramite gli stessi box di feedback in Impostazioni.

## Nota

Questo documento descrive in buona fede il funzionamento tecnico di
TUF così com'è oggi. Non sostituisce una consulenza legale: per usi
professionali o su larga scala, valuta una revisione con un legale,
come indicato anche nei Termini e Condizioni.

*Ultimo aggiornamento: v0.41*
