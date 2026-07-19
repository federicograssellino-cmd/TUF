"""
core/update_check.py
Controllo aggiornamenti di TUF, in background, senza toccare la
politica no-log dell'app.

RICHIESTA: "vorrei... rilasciare gli aggiornamenti su software
installati su altri pc" — scelta fatta insieme all'utente: SOLO
avviso + link (non download/installazione automatica). TUF, poco dopo
l'avvio, controlla se su GitHub Releases esiste una versione piu'
recente di quella installata; se si', mostra un pulsante cliccabile
che apre la pagina di download nel browser. L'utente resta sempre
libero di ignorare l'avviso e continuare a usare la versione che ha.

COSA VIENE MANDATO A GITHUB: nient'altro che una normale richiesta
HTTP GET pubblica all'API di GitHub (nessun dato personale, nessun
identificativo dell'utente o del PC, nessuna versione installata
comunicata al server — il confronto versione corrente/ultima versione
avviene qui, in locale, non lato server). Se manca la connessione a
internet o GitHub non risponde, il controllo fallisce in silenzio: non
compare nessun popup di errore, TUF continua a funzionare normalmente
com'era gia' prima di questo controllo.
"""
from __future__ import annotations

import json
import re
import urllib.request
from urllib.error import URLError

from PySide6.QtCore import QThread, Signal

# Repository GitHub dove vengono pubblicate le release di TUF (formato
# "utente/repository"). SOSTITUIRE con il proprio username/repo reale
# una volta creato su GitHub — finche' resta il valore segnaposto qui
# sotto, il controllo aggiornamenti fallisce silenziosamente (nessun
# errore visibile, semplicemente non trova mai nulla di nuovo).
UPDATE_REPO = "federicograssellino-cmd/TUF"

_API_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
_TIMEOUT_SECONDS = 6


def _parse_version(text: str) -> tuple[int, ...]:
    """Converte una stringa tipo 'v0.42' o '0.42.1' in una tupla di
    interi (0, 42) / (0, 42, 1), cosi' si possono confrontare due
    versioni numericamente (0.9 < 0.10) invece che come testo puro
    (dove "0.9" > "0.10" alfabeticamente, un errore comune)."""
    cleaned = text.strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


class UpdateCheckWorker(QThread):
    """Esegue il controllo in un thread separato, cosi' l'avvio di TUF
    non resta in attesa della rete (che puo' essere lenta o assente)."""

    update_available = Signal(str, str)  # (nuova_versione, url_pagina_release)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self) -> None:
        if not UPDATE_REPO or UPDATE_REPO == "OWNER/REPO":
            return  # repo non ancora configurato: nessun controllo
        try:
            req = urllib.request.Request(
                _API_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "TUF-update-check"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (URLError, OSError, json.JSONDecodeError, ValueError):
            return  # nessuna connessione / GitHub irraggiungibile: si ignora, niente popup

        tag = data.get("tag_name", "")
        release_url = data.get("html_url", "")
        if not tag or not release_url:
            return

        if _parse_version(tag) > _parse_version(self.current_version):
            self.update_available.emit(tag, release_url)
