"""
config.py
Gestione della configurazione persistente di FilePilot (TUF).

RICHIESTA ESPLICITA ("deve essere un'app NO LOG, cioe' non tiene o
salva nessun file visualizzato, deve essere chiaro nel codice"):
questo e' L'UNICO file che scrive dati persistenti su disco per conto
dell'utente (oltre al cestino interno, vedi trash_dir() qui sotto, e
ai due file di testo facoltativi per suggerimenti/consigli scritti
volontariamente dall'utente in Impostazioni). Tutto quello che salva
e' elencato qui, per intero, cosi' non c'e' bisogno di leggere il
resto del codice per saperlo:

  - cartelle di destinazione configurate (numero, nome, percorso, tasto)
  - ordine/posizione delle cartelle
  - formati/estensioni abilitati (Impostazioni > Formati)
  - livello dimensione cartelle (il cursore nel pannello cartelle)
  - geometria finestra e stato dello splitter (solo all'avvio, vedi
    main_window.py per il perche' NON viene piu' ripristinata la
    posizione/dimensione)
  - ordinamento scelto (nome/dimensione/data)
  - percorso dell'ULTIMA cartella sorgente aperta (solo il percorso
    della cartella, per farla ripartire da li' la volta dopo — non un
    elenco di quali file sono stati aperti/guardati al suo interno)

QUELLO CHE TUF NON SALVA MAI, DA NESSUNA PARTE, IN NESSUN FORMATO:
  - il CONTENUTO di nessun file (foto/video/documento/altro)
  - una cronologia di QUALI file sono stati aperti/visualizzati
  - le miniature/anteprime: vivono SOLO in memoria (dizionari Python
    di processo, vedi preview_widget.py e duplicate_review_dialog.py)
    e spariscono quando la finestra/il pannello si chiude — non
    vengono mai scritte su disco, in nessuna cache
  - nessun dato viene mai mandato online: TUF non ha un server/
    backend proprio e non fa nessuna telemetria. L'UNICA eccezione e'
    il comando vocale, che usa il servizio gratuito di Google per la
    trascrizione (richiede internet, vedi core/voice_control.py) —
    manda solo l'audio del microfono mentre e' attivo, mai un elenco
    di file

Le uniche altre scritture su disco in tutto il programma sono:
  - il cestino interno di TUF (trash_dir() qui sotto): i file eliminati
    vengono SPOSTATI li' (non copiati, non "loggati" — sono gli stessi
    file, recuperabili con Undo), sempre visibile e apribile come una
    cartella normale
  - un log di crash locale (main.py, crash_log.txt): scrive il
    traceback SOLO se il programma va in errore inatteso, utile per
    correggere i bug — non e' un log di utilizzo, si attiva solo sugli
    errori
  - i due file di testo facoltativi in Impostazioni ("suggerisci un
    formato", "Hai altri consigli?"): contengono SOLO il testo scritto
    volontariamente dall'utente in quelle caselle, mai altro
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
    else:
        base = str(Path.home() / ".config")
    d = Path(base) / "FilePilot"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = _config_dir() / "config.json"


def trash_dir() -> Path:
    """Cartella 'cestino' interna di TideUp File. I file eliminati
    vengono spostati qui (invece che nel Cestino di Windows) proprio
    per permettere l'Undo istantaneo: Windows non offre un modo
    semplice per far ripristinare a un programma un file dal Cestino
    di sistema, quindi TUF usa un proprio cestino recuperabile."""
    d = _config_dir() / "Cestino"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class FolderTarget:
    number: int
    name: str
    path: str
    shortcut: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "FolderTarget":
        return FolderTarget(
            number=int(d.get("number", 0)),
            name=d.get("name", ""),
            path=d.get("path", ""),
            shortcut=d.get("shortcut", ""),
        )


# RICHIESTA: "sarebbe carico che il cestino, il comando doppio numero
# e tutte le shortcut create possano essere personalizzabili in
# impostazioni" — scorciatoie RIMAPPABILI da Impostazioni > Scorciatoie
# (vedi ui/settings_dialog.py e main_window._install_custom_shortcuts).
# I tasti numero 1-9 (cartelle) e lo "0" del tastierino NON sono qui:
# restano sempre fissi perche' legati al numero stesso di ogni
# cartella (digitare "3" sposta sempre nella cartella numero 3) — non
# avrebbe senso renderli rimappabili singolarmente. "delete" qui sotto
# e' invece il tasto Canc, una scorciatoia SEPARATA e aggiuntiva per
# eliminare (stessa identica azione dello "0"), quella si' rimappabile.
DEFAULT_SHORTCUTS: dict[str, str] = {
    "delete": "Del",
    "double_digit_prefix": "\\",
    "undo": "Ctrl+Z",
    "voice_command": "C",
    "reset_zoom": "Ctrl+0",
    "next": "Right",
    "back": "Left",
    "play_pause": "Space",
}

# Etichette in italiano mostrate in Impostazioni > Scorciatoie, stesso
# ordine di DEFAULT_SHORTCUTS.
SHORTCUT_LABELS: dict[str, str] = {
    "delete": "Elimina (cestino) — tasto Canc",
    "double_digit_prefix": "Prefisso doppia cifra (cartelle 10+)",
    "undo": "Annulla ultima azione (Undo)",
    "voice_command": "Attiva/disattiva comando vocale",
    "reset_zoom": "Ripristina zoom anteprima",
    "next": "File successivo",
    "back": "File precedente",
    "play_pause": "Play / pausa video",
}

DEFAULTS: dict[str, Any] = {
    "folders": [],              # list[FolderTarget.to_dict()]
    "text_size": 11,            # pt
    "row_height": 34,           # px
    "row_spacing": 4,           # px
    "window_geometry": None,    # base64 QByteArray hex
    "window_state": None,
    "last_source_folder": "",
    "splitter_state": None,     # posizione divisore preview/cartelle
    "sort_mode": "name",        # name | size | date
    "shortcuts": {},            # solo le VOCI CAMBIATE rispetto a DEFAULT_SHORTCUTS
    # RICHIESTA: "implementiamo anche le lingue!" / "il primo run deve
    # essere in inglese e devi poter scegliere la lingua da subito" —
    # lingua attiva dell'interfaccia (vedi filepilot/i18n.py). Default
    # "en": e' quella mostrata finche' l'utente non sceglie
    # esplicitamente nel dialogo di primo avvio (ui/language_dialog.py,
    # vedi anche "language_chosen" qui sotto).
    "language": "en",
    # True solo DOPO che l'utente ha scelto esplicitamente una lingua
    # nel dialogo di primo avvio (non basta il default "en" sopra):
    # serve a distinguere "non ha ancora scelto" da "ha scelto inglese
    # apposta", cosi' il dialogo di scelta lingua compare una volta
    # sola, come guide_seen per la guida rapida.
    "language_chosen": False,
    # RICHIESTA: "possiamo 'rendere unica' ogni copia?" — un ID casuale
    # generato UNA VOLA in locale al primo avvio (vedi
    # ConfigManager.get_install_id() sotto), SOLO per dare un'identita'
    # a ogni installazione. Non e' una licenza, non blocca nulla, non
    # viene mai mandato online automaticamente (resta coerente con la
    # politica no-log): e' visibile in Impostazioni > Info e l'utente
    # puo' copiarlo e includerlo VOLONTARIAMENTE in un feedback via
    # Telegram, esattamente come gia' succede per nome/email in quel
    # modulo (vedi core/feedback_sender.py). Stringa vuota finche' non
    # viene generato (vedi get_install_id).
    "install_id": "",
}


class ConfigManager:
    """Carica e salva la configurazione dell'app su disco (JSON)."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # ---------------------------------------------------------- IO
    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = dict(DEFAULTS)
                merged.update(loaded)
                # RICHIESTA: "il primo run deve essere in inglese" — il
                # default "en" (vedi DEFAULTS sopra) vale per chi installa
                # TUF da zero. Chi invece aveva GIA' un config.json da
                # prima che esistesse questa chiave (guide_seen=True, ma
                # "language" assente: versioni precedenti erano solo in
                # italiano) riparte in italiano invece che in inglese —
                # non e' un "primo avvio", e' una migrazione di chi la
                # usa gia' cosi'. Resta comunque cambiabile in un click
                # da Impostazioni.
                if "language" not in loaded and loaded.get("guide_seen"):
                    merged["language"] = "it"
                    merged["language_chosen"] = True
                self.data = merged
            except (json.JSONDecodeError, OSError):
                self.data = dict(DEFAULTS)
        else:
            self.data = dict(DEFAULTS)

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ------------------------------------------------ folder helpers
    def get_folders(self) -> list[FolderTarget]:
        return [FolderTarget.from_dict(d) for d in self.data.get("folders", [])]

    def set_folders(self, folders: list[FolderTarget]) -> None:
        folders_sorted = sorted(folders, key=lambda f: f.number)
        self.data["folders"] = [f.to_dict() for f in folders_sorted]

    # ---------------------------------------------- shortcut helpers
    def get_shortcuts(self) -> dict[str, str]:
        """Predefinite (DEFAULT_SHORTCUTS) con sopra le sole voci che
        l'utente ha effettivamente cambiato in Impostazioni. Cosi' se
        in futuro aggiungiamo una nuova azione rimappabile, chi ha gia'
        salvato una config vecchia la trova comunque con un valore di
        default sensato, invece di un buco."""
        saved = self.data.get("shortcuts", {}) or {}
        merged = dict(DEFAULT_SHORTCUTS)
        merged.update({k: v for k, v in saved.items() if k in DEFAULT_SHORTCUTS})
        return merged

    def set_shortcuts(self, shortcuts: dict[str, str]) -> None:
        self.data["shortcuts"] = dict(shortcuts)

    # ------------------------------------------------ generic access
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    # ------------------------------------------------- install id
    def get_install_id(self) -> str:
        """ID casuale univoco per questa installazione (vedi nota su
        "install_id" in DEFAULTS sopra). Generato pigramente alla prima
        richiesta e salvato subito, cosi' resta lo stesso per tutta la
        vita di questa installazione (a meno che l'utente non cancelli
        config.json)."""
        current = self.data.get("install_id", "")
        if not current:
            current = uuid.uuid4().hex
            self.data["install_id"] = current
            self.save()
        return current
