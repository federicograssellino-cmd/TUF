"""
ui/dashboard.py
Dialogo mostrato subito dopo la scansione di una cartella: riepiloga
i conteggi per tipo, i duplicati stimati (per dimensione) e il peso
totale. L'utente sceglie l'ordinamento iniziale e se iniziare la
catalogazione o controllare subito i duplicati.
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QComboBox
)

from filepilot.models import FileItem, FileCategory, CATEGORY_LABELS
from filepilot.ui.branding import app_icon, enable_dark_titlebar


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


class DashboardDialog(QDialog):
    ACTION_CATALOG = 1
    ACTION_DUPLICATES = 2

    def __init__(self, items: list[FileItem], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Riepilogo cartella")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(380)
        self.chosen_action: int | None = None

        counts = Counter(it.category for it in items)
        total_size = sum(it.size for it in items)

        # stima rapida duplicati per dimensione (candidati, non confermati)
        sizes = Counter(it.size for it in items)
        dup_candidates = sum(c for c in sizes.values() if c > 1)

        # SEGNALATO ("il logo TUF si ripete due volte"): stesso motivo
        # di settings_dialog.py — la barra del titolo nativa mostra
        # gia' l'icona TUF accanto a "Riepilogo cartella", quindi il
        # BrandedHeader qui sotto (puramente decorativo, come in
        # Impostazioni) ripeteva la stessa cosa. Tolto.
        layout = QVBoxLayout(self)

        title = QLabel("Analisi completata")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding-bottom: 8px;")
        layout.addWidget(title)

        rows = [(CATEGORY_LABELS[cat], counts.get(cat, 0)) for cat in CATEGORY_LABELS]
        rows.append(("Candidati duplicati", dup_candidates))
        rows.append(("Peso totale", human_size(total_size)))

        for label, value in rows:
            row = QHBoxLayout()
            l = QLabel(label)
            l.setStyleSheet("color: #ccc;")
            v = QLabel(str(value))
            v.setStyleSheet("color: #fff; font-weight: bold;")
            row.addWidget(l)
            row.addStretch(1)
            row.addWidget(v)
            layout.addLayout(row)

        layout.addSpacing(8)
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Ordina per:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Nome", "Dimensione", "Data"])
        sort_row.addWidget(self.sort_combo, stretch=1)
        layout.addLayout(sort_row)

        btn_row = QHBoxLayout()
        self.btn_catalog = QPushButton("Inizia catalogazione")
        self.btn_dupes = QPushButton("Controlla duplicati")
        btn_row.addWidget(self.btn_catalog)
        btn_row.addWidget(self.btn_dupes)
        layout.addSpacing(12)
        layout.addLayout(btn_row)

        self.btn_catalog.clicked.connect(self._choose_catalog)
        self.btn_dupes.clicked.connect(self._choose_dupes)

        # BUG RISOLTO: vedi il commento in ui/main_window.py sullo
        # stesso argomento — va chiamata DOPO che il layout esiste,
        # non a inizio __init__.
        enable_dark_titlebar(self)

    def _choose_catalog(self) -> None:
        self.chosen_action = self.ACTION_CATALOG
        self.accept()

    def _choose_dupes(self) -> None:
        self.chosen_action = self.ACTION_DUPLICATES
        self.accept()

    def sort_mode(self) -> str:
        return self.sort_combo.currentText()
