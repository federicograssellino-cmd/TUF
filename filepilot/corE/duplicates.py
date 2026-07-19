"""
core/duplicates.py
Individuazione dei file duplicati in tre fasi (economica -> costosa):
1) raggruppamento per dimensione in byte (istantaneo)
2) hash veloce campionato (perceptual hash per immagini, campionamento
   a blocchi per gli altri tipi) solo sui candidati con stessa dimensione
3) CONFERMA con hash dell'intero file, ma solo sui pochissimi
   candidati che hanno gia' combaciato al passo 2 — cosi' il controllo
   e' sia veloce (si legge tutto il file solo per i veri sospetti, non
   per l'intera libreria) sia sicuro al 100% (nessun falso duplicato).
Il progresso include anche una stima del tempo rimanente, calcolata
dalla velocita' media dall'inizio della scansione.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from filepilot.models import FileItem, FileCategory

try:
    import imagehash
    from PIL import Image
    _HAS_IMAGEHASH = True
except ImportError:
    _HAS_IMAGEHASH = False


SAMPLE_CHUNK = 256 * 1024  # 256 KB per blocco campionato
N_SAMPLES = 8              # blocchi distribuiti lungo il file + 1 finale

# Intervallo minimo tra un ricalcolo della velocita'/ETA e l'altro.
# BUG RISOLTO ("il counter del tempo scorre velocissimo"): prima la
# velocita' si ricalcolava ad ogni singolo file, usando SOLO il tempo
# trascorso dall'inizio della scansione. Con tanti file piccoli
# processati in rapidissima successione, "done" poteva salire di
# molto in una frazione di secondo: la velocita' istantanea risultava
# enormemente sovrastimata e la stima del tempo rimanente crollava in
# modo innaturale da un aggiornamento all'altro. Ora la velocita' si
# ricalcola al massimo ogni MIN_EMIT_INTERVAL secondi, e viene
# ammorbidita con una media mobile esponenziale (vedi _emit_progress)
# invece di essere ricalcolata da zero: il tempo rimanente scende in
# modo molto piu' graduale e credibile.
MIN_EMIT_INTERVAL = 0.2
RATE_SMOOTHING_ALPHA = 0.3


def _sample_hash(path: str, chunk_size: int = SAMPLE_CHUNK, n_samples: int = N_SAMPLES) -> str:
    """Hash VELOCE basato su blocchi distribuiti lungo il file (non
    letto per intero): usato come primo filtro, economico anche su
    migliaia di file grandi. Puo' dare falsi positivi molto rari (due
    file diversi con tutti i blocchi campionati uguali per puro caso),
    per questo il risultato va sempre confermato con _full_hash prima
    di considerarlo un duplicato vero."""
    h = hashlib.blake2b(digest_size=16)
    try:
        size = Path(path).stat().st_size
        with open(path, "rb") as f:
            if size <= chunk_size * n_samples:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    h.update(chunk)
            else:
                for i in range(n_samples):
                    offset = int(size * i / n_samples)
                    f.seek(offset)
                    h.update(f.read(chunk_size))
                f.seek(max(0, size - chunk_size))
                h.update(f.read(chunk_size))
    except OSError:
        return ""
    return h.hexdigest()


def _full_hash(path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
    """Hash dell'INTERO file, nessun rischio di falso positivo. Usato
    solo per CONFERMARE i pochi candidati che hanno gia' lo stesso
    _sample_hash (e quindi anche la stessa dimensione): sono quasi
    sempre un pugno di file, quindi leggerli per intero costa poco,
    anche se singolarmente sono grandi.
    BUG RISOLTO: prima l'unico hash usato leggeva solo il primo e
    l'ultimo blocco da 1 MB del file. Due file diversi ma della stessa
    dimensione, con contenuto centrale diverso (es. due CV con la
    stessa dimensione ma una foto diversa nel mezzo), potevano avere
    lo stesso hash ed essere segnalati come duplicati per errore."""
    h = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _image_phash(path: str) -> str | None:
    if not _HAS_IMAGEHASH:
        return None
    try:
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def format_eta(seconds: float | None) -> str:
    """Formatta una stima del tempo rimanente in una stringa breve, es.
    '~45 s rimanenti' o '~3 min rimanenti'. Ritorna stringa vuota se
    la stima non e' ancora disponibile (troppo presto per calcolarla)."""
    if seconds is None or seconds < 0:
        return ""
    if seconds < 1:
        return "quasi finito"
    if seconds < 60:
        return f"~{int(seconds)} s rimanenti"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"~{minutes} min {secs:02d} s rimanenti"
    hours = minutes // 60
    minutes = minutes % 60
    return f"~{hours} h {minutes:02d} min rimanenti"


class DuplicateGroup:
    """Un gruppo di file candidati duplicati tra loro."""

    def __init__(self, items: list[FileItem]):
        self.items = items

    def __len__(self) -> int:
        return len(self.items)


class DuplicateFinder(QThread):
    """Calcola i gruppi di duplicati a partire da una lista di FileItem."""

    # (fatti, totale, nome del file appena processato, stima tempo
    # rimanente gia' formattata) — il nome serve anche come diagnostica:
    # se lo scan si blocca, l'ultimo nome mostrato nella barra di stato
    # e' quello del file su cui si e' impuntato.
    progress = Signal(int, int, str, str)
    finished_scan = Signal(list)         # list[DuplicateGroup]

    def __init__(self, items: list[FileItem], parent=None):
        super().__init__(parent)
        self.items = items
        self._abort = False
        self._start_time = 0.0
        self._last_emit_time = 0.0
        self._last_emit_done = 0
        self._smoothed_rate: float | None = None
        self._last_eta_text = ""

    def abort(self) -> None:
        self._abort = True

    def _emit_progress(self, done: int, total: int, name: str) -> None:
        """Emette il segnale di progresso. Il NOME del file viene
        sempre aggiornato subito (utile per capire su cosa si e'
        fermato lo scan se sembra bloccato), ma la velocita'/ETA
        vengono ricalcolate al massimo ogni MIN_EMIT_INTERVAL secondi
        (vedi il commento sopra la costante) per evitare che il tempo
        rimanente "corra" in modo innaturale."""
        now = time.monotonic()
        elapsed_since_last = now - self._last_emit_time
        if elapsed_since_last >= MIN_EMIT_INTERVAL or done >= total:
            done_since_last = done - self._last_emit_done
            if elapsed_since_last > 0 and done_since_last > 0:
                instant_rate = done_since_last / elapsed_since_last
                if self._smoothed_rate is None:
                    self._smoothed_rate = instant_rate
                else:
                    self._smoothed_rate = (
                        RATE_SMOOTHING_ALPHA * instant_rate
                        + (1 - RATE_SMOOTHING_ALPHA) * self._smoothed_rate
                    )
            if self._smoothed_rate:
                remaining = max(0.0, (total - done) / self._smoothed_rate)
                self._last_eta_text = format_eta(remaining)
            self._last_emit_time = now
            self._last_emit_done = done
        self.progress.emit(done, total, name, self._last_eta_text)

    def run(self) -> None:
        self._start_time = time.monotonic()
        self._last_emit_time = self._start_time

        # Fase 1: raggruppa per dimensione esatta
        by_size: dict[int, list[FileItem]] = defaultdict(list)
        for it in self.items:
            by_size[it.size].append(it)

        candidates = [g for g in by_size.values() if len(g) > 1]
        total = sum(len(g) for g in candidates)
        done = 0
        groups: list[DuplicateGroup] = []

        for group in candidates:
            if self._abort:
                break

            # Fase 2: hash veloce campionato (o perceptual hash per le foto)
            by_key: dict[str, list[FileItem]] = defaultdict(list)
            is_phash: dict[str, bool] = {}
            for it in group:
                if self._abort:
                    break
                self._emit_progress(done, total, it.name)
                if it.category == FileCategory.IMAGE:
                    phash = _image_phash(it.path)
                    if phash is not None:
                        key = f"phash:{phash}"
                        is_phash[key] = True
                    else:
                        key = f"sample:{_sample_hash(it.path)}"
                        is_phash[key] = False
                else:
                    key = f"sample:{_sample_hash(it.path)}"
                    is_phash[key] = False
                it.file_hash = key
                by_key[key].append(it)
                done += 1
                self._emit_progress(done, total, it.name)

            for key, same in by_key.items():
                if len(same) <= 1:
                    continue
                if is_phash.get(key):
                    # corrispondenza percettiva tra foto (es. stessa
                    # foto ricompressa/ridimensionata): e' voluta cosi',
                    # nessuna verifica byte-a-byte aggiuntiva
                    groups.append(DuplicateGroup(same))
                else:
                    # Fase 3: CONFERMA con hash completo, solo su questi
                    # pochi candidati (stessa dimensione + stesso hash
                    # campionato) — qui si azzera il rischio di falsi
                    # duplicati, leggendo per intero solo un pugno di file.
                    # BUG RISOLTO ("resta sempre bloccato a un file dalla
                    # fine"): questa fase non emetteva MAI un aggiornamento
                    # di progresso, quindi se gli ultimi candidati
                    # richiedevano una conferma lunga (file grossi da
                    # leggere per intero), la barra di stato sembrava
                    # bloccata anche se stava ancora lavorando. Ora emette
                    # un aggiornamento (a percentuale invariata, ma con
                    # nome del file e "verifica in corso") anche qui.
                    by_full: dict[str, list[FileItem]] = defaultdict(list)
                    for it in same:
                        if self._abort:
                            break
                        self._emit_progress(done, total, f"verifica finale: {it.name}")
                        by_full[_full_hash(it.path)].append(it)
                    for confirmed in by_full.values():
                        if len(confirmed) > 1:
                            groups.append(DuplicateGroup(confirmed))

        self.finished_scan.emit(groups)
