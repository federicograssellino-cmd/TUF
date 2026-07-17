"""
core/delete_worker.py
Sposta una lista di file nel cestino interno di TUF in un thread
SEPARATO, invece che in modo sincrono sul thread dell'interfaccia.

Prima "Elimina i selezionati"/"Cancella tutte le copie" nella finestra
duplicati spostava i file uno alla volta direttamente sul thread
principale (ui/main_window.py, _delete_duplicate_paths): con tante
copie di grandi dimensioni questo poteva richiedere tempo e bloccare
l'interfaccia nel frattempo, oltre a non dare nessun feedback visivo
di quanto mancasse. Ora il lavoro vero e proprio avviene qui, e il
segnale "progress" permette alla finestra principale di mostrare una
barra di caricamento con percentuale, nome del file corrente e GB
cancellati sul totale (vedi ui/delete_progress_overlay.py).
"""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal


@dataclass
class DeleteItem:
    path: str
    size: int


class DuplicateDeleteWorker(QThread):
    # done, totale, nome del file appena spostato, GB cancellati finora, GB totali da cancellare
    progress = Signal(int, int, str, float, float)
    # lista di (src, dest) spostati con successo, lista di path che hanno dato errore
    finished_delete = Signal(list, list)

    def __init__(self, items: list[DeleteItem], trash_dir_path: Path, parent=None):
        super().__init__(parent)
        self._items = items
        self._trash_dir = trash_dir_path

    def run(self) -> None:
        total = len(self._items)
        total_bytes = sum(it.size for it in self._items)
        moved: list[tuple[str, str]] = []
        failed: list[str] = []
        bytes_done = 0

        for done, it in enumerate(self._items, start=1):
            src = Path(it.path)
            dest = self._trash_dir / src.name
            if dest.exists():
                dest = dest.with_stem(dest.stem + "_" + str(int(time.time())))
            try:
                shutil.move(str(src), str(dest))
                moved.append((str(src), str(dest)))
                bytes_done += it.size
            except OSError:
                failed.append(it.path)

            self.progress.emit(
                done, total, src.name,
                bytes_done / (1024 ** 3), total_bytes / (1024 ** 3),
            )

        self.finished_delete.emit(moved, failed)
