"""
i18n.py
Sistema di traduzione di TUF.

RICHIESTA: "implementiamo anche le lingue!" — dizionario Python custom
(niente QTranslator/Qt Linguist: scelta pragmatica, piu' semplice da
mantenere a mano per un'app di queste dimensioni, discussa e scelta
esplicitamente invece del sistema nativo Qt).

Lingue supportate: inglese (en), italiano (it), spagnolo (es),
francese (fr).

RICHIESTA: "il primo run deve essere in inglese e devi poter scegliere
la lingua da subito" — la lingua di default (prima che l'utente scelga
qualcosa, vedi ui/language_dialog.py mostrato al primissimo avvio) e'
"en", non "it": sia il testo di questo modulo prima di una scelta
esplicita, sia il valore di default in config.py, sono "en".

Uso:
    from filepilot.i18n import tr
    testo = tr("guide.welcome_title")
    testo_con_parametri = tr("tour.step_label", current=2, total=8)

La lingua attiva e' un semplice stato di modulo, impostato una volta
sola all'avvio (vedi main.py / main_window.py) con set_language(), e
letta da tutte le UI con get_language()/tr(). Non serve altro: TUF e'
un processo singolo, non ha bisogno di un sistema di contesti/locale
piu' complesso di cosi'.
"""
from __future__ import annotations

SUPPORTED_LANGUAGES: list[str] = ["en", "it", "es", "fr"]

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "it": "Italiano",
    "es": "Español",
    "fr": "Français",
}

_DEFAULT_LANGUAGE = "en"
_current_language = _DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    """Imposta la lingua attiva. Ignora silenziosamente valori non
    supportati (config.json corrotto/scritto a mano) invece di far
    crashare l'avvio: resta la lingua precedente."""
    global _current_language
    if lang in SUPPORTED_LANGUAGES:
        _current_language = lang


def get_language() -> str:
    return _current_language


def tr(key: str, **kwargs) -> str:
    """Restituisce la stringa tradotta per la lingua attiva. Se la
    chiave non esiste, restituisce la chiave stessa (cosi' un testo
    non ancora tradotto e' comunque visibile/segnalabile invece di
    far sparire il controllo o crashare). Se manca la traduzione per
    la lingua attiva, ripiega sull'inglese e poi sull'italiano."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current_language) or entry.get("en") or entry.get("it") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


# ---------------------------------------------------------------------
# Dizionario stringhe. Copertura attuale (fase 1, vedi TUF_HANDOFF):
# dialogo scelta lingua, guida rapida + accettazione Termini, tour
# interattivo, selettore lingua in Impostazioni. Il resto dell'app
# (schede di Impostazioni, revisione doppioni, pannello cartelle,
# filtri, ecc.) resta in italiano fisso: fase 2 successiva.
# ---------------------------------------------------------------------
_STRINGS: dict[str, dict[str, str]] = {

    # ---- dialogo scelta lingua (language_dialog.py) ----
    "lang_dialog.window_title": {
        "en": "Welcome to TUF",
        "it": "Benvenuto/a in TUF",
        "es": "Bienvenido/a a TUF",
        "fr": "Bienvenue dans TUF",
    },
    "lang_dialog.title": {
        "en": "Choose your language",
        "it": "Scegli la lingua",
        "es": "Elige tu idioma",
        "fr": "Choisissez votre langue",
    },
    "lang_dialog.subtitle": {
        "en": "You can change this anytime later from Settings.",
        "it": "Puoi cambiarla in qualsiasi momento da Impostazioni.",
        "es": "Puedes cambiarlo cuando quieras desde Ajustes.",
        "fr": "Vous pourrez la changer à tout moment depuis les Paramètres.",
    },
    "lang_dialog.continue_btn": {
        "en": "Continue",
        "it": "Continua",
        "es": "Continuar",
        "fr": "Continuer",
    },

    # ---- guida rapida (quick_guide_dialog.py) ----
    "guide.window_title": {
        "en": "Quick guide — TUF",
        "it": "Guida rapida — TUF",
        "es": "Guía rápida — TUF",
        "fr": "Guide rapide — TUF",
    },
    "guide.welcome_title": {
        "en": "Welcome to TUF",
        "it": "Benvenuto/a in TUF",
        "es": "Bienvenido/a a TUF",
        "fr": "Bienvenue dans TUF",
    },
    "guide.welcome_subtitle": {
        "en": "How it works, in two minutes.",
        "it": "Come funziona, in due minuti.",
        "es": "Cómo funciona, en dos minutos.",
        "fr": "Comment ça marche, en deux minutes.",
    },
    "guide.what_is_title": {
        "en": "What is TUF",
        "it": "Cos'è TUF",
        "es": "Qué es TUF",
        "fr": "Qu'est-ce que TUF",
    },
    "guide.what_is_body": {
        "en": "TUF helps you browse, sort and clean up photos, videos, documents and "
              "many other formats inside a folder, and also finds duplicate files. "
              "It runs entirely on your computer: it never saves the content of the "
              "files you open and never sends anything online (see \"no log\" in the "
              "Info tab of Settings).",
        "it": "TUF ti aiuta a scorrere, catalogare e ripulire foto, video, documenti e "
              "molti altri formati dentro una cartella, trovando anche i file duplicati. "
              "Gira tutto sul tuo computer: non salva mai il contenuto dei file che apri e "
              "non manda niente online (vedi \"no log\" nella scheda Info di Impostazioni).",
        "es": "TUF te ayuda a explorar, clasificar y limpiar fotos, vídeos, documentos y "
              "muchos otros formatos dentro de una carpeta, y también encuentra archivos "
              "duplicados. Funciona por completo en tu ordenador: nunca guarda el "
              "contenido de los archivos que abres ni envía nada a internet (consulta "
              "\"no log\" en la pestaña Info de Ajustes).",
        "fr": "TUF vous aide à parcourir, trier et nettoyer photos, vidéos, documents et "
              "de nombreux autres formats dans un dossier, et trouve aussi les fichiers "
              "en double. Tout fonctionne sur votre ordinateur : il n'enregistre jamais le "
              "contenu des fichiers ouverts et n'envoie rien en ligne (voir « no log » "
              "dans l'onglet Infos des Paramètres).",
    },
    "guide.how_start_title": {
        "en": "Getting started",
        "it": "Come iniziare",
        "es": "Cómo empezar",
        "fr": "Comment commencer",
    },
    "guide.how_start_body": {
        "en": "1. Open a folder to explore (folder button at the top).<br>"
              "2. Choose the formats you care about in <b>Settings &gt; Formats</b>, or "
              "on the fly from the <b>Filters</b> dropdown at the bottom left.<br>"
              "3. Browse files with the <b>forward/back</b> keys (arrows, mouse or voice "
              "command).<br>"
              "4. If you don't need a file, use the <b>trash</b> button: it goes to TUF's "
              "internal Recycle Bin, recoverable with <b>Undo</b> until you empty it.",
        "it": "1. Apri una cartella da esplorare (pulsante cartella in alto).<br>"
              "2. Scegli i formati che ti interessano in <b>Impostazioni &gt; Formati</b>, "
              "oppure al volo dalla tendina <b>Filtri</b> in basso a sinistra.<br>"
              "3. Scorri i file con i tasti <b>avanti/indietro</b> (frecce, mouse o "
              "comando vocale).<br>"
              "4. Se un file non ti serve, usa il tasto <b>cestino</b>: va nel Cestino "
              "interno di TUF, recuperabile con <b>Annulla</b> finché non lo svuoti.",
        "es": "1. Abre una carpeta para explorar (botón de carpeta arriba).<br>"
              "2. Elige los formatos que te interesan en <b>Ajustes &gt; Formatos</b>, o "
              "al vuelo desde el menú <b>Filtros</b> abajo a la izquierda.<br>"
              "3. Recorre los archivos con las teclas <b>adelante/atrás</b> (flechas, "
              "ratón o comando de voz).<br>"
              "4. Si no necesitas un archivo, usa el botón de la <b>papelera</b>: va a la "
              "Papelera interna de TUF, recuperable con <b>Deshacer</b> hasta que la "
              "vacíes.",
        "fr": "1. Ouvrez un dossier à explorer (bouton dossier en haut).<br>"
              "2. Choisissez les formats qui vous intéressent dans <b>Paramètres &gt; "
              "Formats</b>, ou à la volée depuis le menu <b>Filtres</b> en bas à "
              "gauche.<br>"
              "3. Parcourez les fichiers avec les touches <b>suivant/précédent</b> "
              "(flèches, souris ou commande vocale).<br>"
              "4. Si un fichier ne vous sert pas, utilisez le bouton <b>corbeille</b> : il "
              "va dans la Corbeille interne de TUF, récupérable avec <b>Annuler</b> tant "
              "que vous ne la videz pas.",
    },
    "guide.duplicates_title": {
        "en": "Finding duplicates",
        "it": "Trovare i duplicati",
        "es": "Encontrar duplicados",
        "fr": "Trouver les doublons",
    },
    "guide.duplicates_body": {
        "en": "Press <b>Find duplicates</b>: TUF groups them and shows them side by "
              "side. You can keep them all, delete the copies (keeping the first one), "
              "delete a whole group, or pick column by column with the \"select/deselect "
              "column\" buttons. Nothing disappears without you seeing it: files marked "
              "for deletion stay visible but flagged, until you confirm.",
        "it": "Premi <b>Cerca duplicati</b>: TUF li raggruppa e te li mostra fianco a "
              "fianco. Puoi tenerli tutti, cancellare le copie (tenendo la prima), "
              "cancellare tutto un gruppo, oppure scegliere colonna per colonna con i "
              "pulsanti \"seleziona/deseleziona colonna\". Niente sparisce senza che tu lo "
              "veda: i file segnati per l'eliminazione restano visibili ma marcati, "
              "finché non confermi.",
        "es": "Pulsa <b>Buscar duplicados</b>: TUF los agrupa y te los muestra uno junto "
              "a otro. Puedes conservarlos todos, borrar las copias (conservando el "
              "primero), borrar un grupo entero, o elegir columna por columna con los "
              "botones \"seleccionar/deseleccionar columna\". Nada desaparece sin que lo "
              "veas: los archivos marcados para borrar siguen visibles pero señalados, "
              "hasta que confirmes.",
        "fr": "Appuyez sur <b>Rechercher les doublons</b> : TUF les regroupe et les "
              "affiche côte à côte. Vous pouvez tous les garder, supprimer les copies (en "
              "gardant le premier), supprimer tout un groupe, ou choisir colonne par "
              "colonne avec les boutons « sélectionner/désélectionner la colonne ». Rien "
              "ne disparaît sans que vous le voyiez : les fichiers marqués pour "
              "suppression restent visibles mais signalés, jusqu'à confirmation.",
    },
    "guide.voice_title": {
        "en": "Voice command (optional)",
        "it": "Comando vocale (facoltativo)",
        "es": "Comando de voz (opcional)",
        "fr": "Commande vocale (facultatif)",
    },
    "guide.voice_body": {
        "en": "If you turn it on, you can say \"next\", \"back\", \"trash\" or \"undo\" "
              "to navigate hands-free. It uses Google's free service to understand you "
              "(the only exception to fully local operation — see Terms and Conditions "
              "and Privacy, in Settings &gt; Info, for details). It's entirely optional: "
              "TUF works exactly the same with just mouse and keyboard.",
        "it": "Se lo attivi, puoi dire \"avanti\", \"indietro\", \"cestino\" o \"annulla\" "
              "per navigare senza mouse. Usa il servizio gratuito di Google per capire "
              "cosa dici (unica eccezione al funzionamento locale — vedi Termini e "
              "Condizioni e Privacy, in Impostazioni &gt; Info, per i dettagli). È del "
              "tutto facoltativo: TUF funziona identico anche solo con mouse e tastiera.",
        "es": "Si lo activas, puedes decir \"adelante\", \"atrás\", \"papelera\" o "
              "\"deshacer\" para navegar sin usar las manos. Usa el servicio gratuito de "
              "Google para entenderte (la única excepción al funcionamiento local — "
              "consulta Términos y Condiciones y Privacidad, en Ajustes &gt; Info, para "
              "más detalles). Es totalmente opcional: TUF funciona igual solo con ratón y "
              "teclado.",
        "fr": "Si vous l'activez, vous pouvez dire « suivant », « précédent », "
              "« corbeille » ou « annuler » pour naviguer sans les mains. Utilise le "
              "service gratuit de Google pour vous comprendre (seule exception au "
              "fonctionnement local — voir Conditions Générales et Confidentialité, dans "
              "Paramètres &gt; Infos, pour les détails). C'est entièrement facultatif : "
              "TUF fonctionne à l'identique avec seulement la souris et le clavier.",
    },
    "guide.more_title": {
        "en": "Where to find the rest",
        "it": "Dove trovare il resto",
        "es": "Dónde encontrar el resto",
        "fr": "Où trouver le reste",
    },
    "guide.more_body": {
        "en": "The <b>⚙ Settings</b> button, next to the logo at the top, has "
              "everything else: recognized formats, app info (Info tab, including Terms "
              "and Conditions), and a place to leave suggestions or missing formats.",
        "it": "Il tasto <b>⚙ Impostazioni</b>, accanto al logo in alto, ha tutto il "
              "resto: i formati riconosciuti, le informazioni sull'app (scheda Info, con "
              "anche i Termini e Condizioni), e uno spazio per scriverci consigli o "
              "formati mancanti.",
        "es": "El botón <b>⚙ Ajustes</b>, junto al logo arriba, tiene todo lo demás: los "
              "formatos reconocidos, la información de la app (pestaña Info, con los "
              "Términos y Condiciones), y un espacio para dejar sugerencias o formatos "
              "que falten.",
        "fr": "Le bouton <b>⚙ Paramètres</b>, à côté du logo en haut, contient tout le "
              "reste : les formats reconnus, les informations sur l'app (onglet Infos, "
              "avec les Conditions Générales), et un espace pour laisser des suggestions "
              "ou signaler des formats manquants.",
    },
    "guide.footer_note": {
        "en": "This guide reopens anytime from Settings &gt; Info.",
        "it": "Questa guida si riapre in qualsiasi momento da Impostazioni &gt; Info.",
        "es": "Esta guía se vuelve a abrir en cualquier momento desde Ajustes &gt; Info.",
        "fr": "Ce guide se rouvre à tout moment depuis Paramètres &gt; Infos.",
    },
    "guide.terms_checkbox": {
        "en": "I have read and accept the Terms and Conditions",
        "it": "Ho letto e accetto i Termini e Condizioni",
        "es": "He leído y acepto los Términos y Condiciones",
        "fr": "J'ai lu et j'accepte les Conditions Générales",
    },
    "guide.read_terms_btn": {
        "en": "Read the Terms",
        "it": "Leggi i Termini",
        "es": "Leer los Términos",
        "fr": "Lire les Conditions",
    },
    "guide.ok_btn": {
        "en": "Got it, let's start",
        "it": "Ho capito, inizia",
        "es": "Entendido, empezar",
        "fr": "Compris, commencer",
    },
    "guide.terms_missing_title": {
        "en": "Terms and Conditions",
        "it": "Termini e Condizioni",
        "es": "Términos y Condiciones",
        "fr": "Conditions Générales",
    },
    "guide.terms_missing_body": {
        "en": "Can't find the TERMINI_E_CONDIZIONI.pdf file in the program folder.",
        "it": "Non trovo il file TERMINI_E_CONDIZIONI.pdf nella cartella del programma.",
        "es": "No se encuentra el archivo TERMINI_E_CONDIZIONI.pdf en la carpeta del "
              "programa.",
        "fr": "Impossible de trouver le fichier TERMINI_E_CONDIZIONI.pdf dans le dossier "
              "du programme.",
    },

    # ---- tour interattivo (onboarding_tour.py) ----
    "tour.step_label": {
        "en": "STEP {current} OF {total}",
        "it": "PASSO {current} DI {total}",
        "es": "PASO {current} DE {total}",
        "fr": "ÉTAPE {current} SUR {total}",
    },
    "tour.skip_btn": {
        "en": "Skip tour",
        "it": "Salta tour",
        "es": "Saltar recorrido",
        "fr": "Passer la visite",
    },
    "tour.next_btn": {
        "en": "Next",
        "it": "Avanti",
        "es": "Siguiente",
        "fr": "Suivant",
    },
    "tour.finish_btn": {
        "en": "Done, let's go!",
        "it": "Fine, inizia!",
        "es": "¡Listo, empezar!",
        "fr": "Terminé, c'est parti !",
    },
    "tour.step1.title": {"en": "Open a folder", "it": "Apri una cartella",
                          "es": "Abre una carpeta", "fr": "Ouvrir un dossier"},
    "tour.step1.text": {
        "en": "Start here: open the folder with your photos, videos, documents (or "
              "almost any other format).",
        "it": "Si parte da qui: apri la cartella con le tue foto, video, documenti (o "
              "quasi qualunque altro formato).",
        "es": "Empieza aquí: abre la carpeta con tus fotos, vídeos, documentos (o casi "
              "cualquier otro formato).",
        "fr": "Ça commence ici : ouvrez le dossier avec vos photos, vidéos, documents "
              "(ou presque tout autre format).",
    },
    "tour.step2.title": {"en": "Preview", "it": "Anteprima",
                          "es": "Vista previa", "fr": "Aperçu"},
    "tour.step2.text": {
        "en": "Files show up here one at a time. Scroll with the ◀ ▶ arrows on the "
              "bottom bar (or the keyboard).",
        "it": "I file compaiono qui uno alla volta. Scorri con le frecce ◀ ▶ della "
              "barra in basso (o con la tastiera).",
        "es": "Los archivos aparecen aquí de uno en uno. Navega con las flechas ◀ ▶ de "
              "la barra inferior (o con el teclado).",
        "fr": "Les fichiers apparaissent ici un par un. Naviguez avec les flèches ◀ ▶ "
              "de la barre du bas (ou au clavier).",
    },
    "tour.step3.title": {"en": "Destination folders", "it": "Cartelle di destinazione",
                          "es": "Carpetas de destino", "fr": "Dossiers de destination"},
    "tour.step3.text": {
        "en": "Click a folder (or press its number on the keyboard) to move the file "
              "you're viewing there right away. The ✏ button lets you reorder or "
              "renumber them by dragging.",
        "it": "Clicca una cartella (o premi il suo numero sulla tastiera) per spostarci "
              "subito il file che stai guardando. Il tasto ✏ permette di riordinarle o "
              "rinumerarle trascinandole.",
        "es": "Haz clic en una carpeta (o pulsa su número en el teclado) para mover ahí "
              "mismo el archivo que estás viendo. El botón ✏ permite reordenarlas o "
              "renumerarlas arrastrándolas.",
        "fr": "Cliquez sur un dossier (ou appuyez sur son numéro au clavier) pour y "
              "déplacer immédiatement le fichier affiché. Le bouton ✏ permet de les "
              "réorganiser ou renuméroter par glisser-déposer.",
    },
    "tour.step4.title": {"en": "Add folders", "it": "Aggiungi cartelle",
                          "es": "Añadir carpetas", "fr": "Ajouter des dossiers"},
    "tour.step4.text": {
        "en": "Add new destination folders from here. You can also drag one directly "
              "from File Explorer.",
        "it": "Da qui aggiungi nuove cartelle di destinazione. Puoi anche trascinarne "
              "una direttamente da Esplora risorse.",
        "es": "Desde aquí añades nuevas carpetas de destino. También puedes arrastrar "
              "una directamente desde el Explorador de archivos.",
        "fr": "Ajoutez ici de nouveaux dossiers de destination. Vous pouvez aussi en "
              "glisser un directement depuis l'Explorateur de fichiers.",
    },
    "tour.step5.title": {"en": "Delete", "it": "Elimina",
                          "es": "Eliminar", "fr": "Supprimer"},
    "tour.step5.text": {
        "en": "Moves the current file to TUF's internal Recycle Bin: recoverable with "
              "Undo until you close the program.",
        "it": "Sposta il file corrente nel Cestino interno di TUF: resta recuperabile "
              "con Undo finché non chiudi il programma.",
        "es": "Mueve el archivo actual a la Papelera interna de TUF: se puede "
              "recuperar con Deshacer hasta que cierres el programa.",
        "fr": "Déplace le fichier actuel vers la Corbeille interne de TUF : "
              "récupérable avec Annuler tant que vous ne fermez pas le programme.",
    },
    "tour.step6.title": {"en": "Undo", "it": "Annulla (Undo)",
                          "es": "Deshacer", "fr": "Annuler"},
    "tour.step6.text": {
        "en": "If you move or delete something by mistake, this button undoes the "
              "last action.",
        "it": "Se sposti o elimini per sbaglio, questo tasto annulla l'ultima azione.",
        "es": "Si mueves o eliminas algo por error, este botón deshace la última "
              "acción.",
        "fr": "Si vous déplacez ou supprimez quelque chose par erreur, ce bouton "
              "annule la dernière action.",
    },
    "tour.step7.title": {"en": "Voice command (optional)",
                          "it": "Comando vocale (facoltativo)",
                          "es": "Comando de voz (opcional)",
                          "fr": "Commande vocale (facultatif)"},
    "tour.step7.text": {
        "en": "You can also say \"next\", \"back\", \"trash\" or a folder's name to "
              "navigate hands-free. Entirely optional: it works exactly the same "
              "without it.",
        "it": "Puoi anche dire \"avanti\", \"indietro\", \"cestino\" o il nome di una "
              "cartella per navigare senza mouse. Del tutto facoltativo: funziona "
              "identico anche senza.",
        "es": "También puedes decir \"adelante\", \"atrás\", \"papelera\" o el nombre "
              "de una carpeta para navegar sin usar las manos. Totalmente opcional: "
              "funciona igual sin usarlo.",
        "fr": "Vous pouvez aussi dire « suivant », « précédent », « corbeille » ou le "
              "nom d'un dossier pour naviguer sans les mains. Entièrement facultatif : "
              "fonctionne à l'identique sans.",
    },
    "tour.step8.title": {"en": "Settings", "it": "Impostazioni",
                          "es": "Ajustes", "fr": "Paramètres"},
    "tour.step8.text": {
        "en": "Here you'll find recognized formats, customizable shortcuts, this "
              "guide and the tour, and a place to leave suggestions or report missing "
              "formats.",
        "it": "Qui trovi i formati riconosciuti, le scorciatoie personalizzabili, "
              "questa guida e il tour, e uno spazio per lasciare consigli o segnalare "
              "formati mancanti.",
        "es": "Aquí encuentras los formatos reconocidos, los atajos personalizables, "
              "esta guía y el recorrido, y un espacio para dejar sugerencias o "
              "reportar formatos que falten.",
        "fr": "Vous trouverez ici les formats reconnus, les raccourcis "
              "personnalisables, ce guide et la visite, ainsi qu'un espace pour "
              "laisser des suggestions ou signaler des formats manquants.",
    },

    # ---- selettore lingua in Impostazioni (settings_dialog.py) ----
    "settings.language_label": {
        "en": "Language",
        "it": "Lingua",
        "es": "Idioma",
        "fr": "Langue",
    },
    "settings.language_restart_note": {
        "en": "Takes effect the next time you open TUF.",
        "it": "Ha effetto al prossimo avvio di TUF.",
        "es": "Se aplica la próxima vez que abras TUF.",
        "fr": "Prend effet au prochain démarrage de TUF.",
    },

    # ---- ID installazione (settings_dialog.py) ----
    "settings.install_id_label": {
        "en": "Installation ID",
        "it": "ID installazione",
        "es": "ID de instalación",
        "fr": "ID d'installation",
    },
    "settings.install_id_note": {
        "en": "A random local ID, unique to this installation. Never sent "
              "anywhere automatically — you can copy it and include it "
              "yourself in a Telegram feedback message if you ever need to.",
        "it": "Un ID casuale locale, univoco per questa installazione. Non "
              "viene mai mandato online automaticamente — puoi copiarlo e "
              "includerlo tu in un feedback via Telegram, se mai ti serve.",
        "es": "Un ID local aleatorio, único para esta instalación. Nunca se "
              "envía automáticamente a ningún sitio — puedes copiarlo e "
              "incluirlo tú mismo en un feedback por Telegram si alguna vez "
              "lo necesitas.",
        "fr": "Un identifiant local aléatoire, unique à cette installation. "
              "Jamais envoyé automatiquement — vous pouvez le copier et "
              "l'inclure vous-même dans un message de feedback Telegram si "
              "besoin.",
    },
    "settings.install_id_copy_btn": {
        "en": "Copy",
        "it": "Copia",
        "es": "Copiar",
        "fr": "Copier",
    },
    "settings.install_id_copied": {
        "en": "Copied!",
        "it": "Copiato!",
        "es": "¡Copiado!",
        "fr": "Copié !",
    },
}
