"""
core/scanner.py
Scansione ricorsiva di una cartella per costruire la lista di FileItem
supportati. Gira in un QThread dedicato per mantenere la UI reattiva
anche con decine di migliaia di file. Puo' essere limitata a un
sottoinsieme di estensioni (import selettivo scelto dall'utente).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from filepilot.models import FileItem, SUPPORTED_EXT


class FileScanner(QThread):
    """Scansiona ricorsivamente `root` ed emette i FileItem trovati."""

    progress = Signal(int)          # numero di file scansionati finora
    item_found = Signal(object)     # FileItem
    finished_scan = Signal(list)    # list[FileItem] completa

    def __init__(self, root: str, allowed_ext: set[str] | None = None, parent=None):
        super().__init__(parent)
        self.root = root
        self.allowed_ext = allowed_ext or SUPPORTED_EXT
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        results: list[FileItem] = []
        count = 0
        root_path = Path(self.root)
        if not root_path.exists():
            self.finished_scan.emit(results)
            return

        for p in root_path.rglob("*"):
            if self._abort:
                break
            if not p.is_file():
                continue
            if p.suffix.lower() not in self.allowed_ext:
                continue
            try:
                item = FileItem.from_path(p)
            except OSError:
                continue
            results.append(item)
            count += 1
            self.item_found.emit(item)
            if count % 25 == 0:
                self.progress.emit(count)

        self.progress.emit(count)
        self.finished_scan.emit(results)
