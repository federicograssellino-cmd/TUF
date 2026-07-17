"""
ui/delete_progress_overlay.py
Overlay mostrato AL CENTRO, sopra tutta la finestra, mentre i file
duplicati vengono spostati nel cestino interno in background (vedi
core/delete_worker.py). Mostra una barra di progresso con la
percentuale, il nome del file appena spostato e il totale in GB gia'
cancellati sul totale da cancellare — richiesto perche' prima
"Cancella tutte le copie" non dava nessun feedback durante lo
spostamento vero e proprio dei file, che con tante copie di grandi
dimensioni puo' richiedere qualche secondo.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel, QProgressBar


class DeleteProgressOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 165);")
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setFixedWidth(420)
        card.setStyleSheet(
            "QFrame { background-color: #262626; border-radius: 12px;"
            " border: 2px solid #c0392b; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(10)

        icon = QLabel("🗑️")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 34px; border: none;")
        card_layout.addWidget(icon)

        self.title_label = QLabel("Eliminazione duplicati in corso...")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #fff; font-size: 14px; font-weight: 600; border: none;")
        card_layout.addWidget(self.title_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        self.bar.setStyleSheet(
            "QProgressBar { background-color: #1a1a1a; border-radius: 6px; color: #fff;"
            " text-align: center; min-height: 20px; border: none; }"
            "QProgressBar::chunk { background-color: #c0392b; border-radius: 6px; }"
        )
        card_layout.addWidget(self.bar)

        self.name_label = QLabel("")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("color: #ccc; font-size: 11px; border: none;")
        card_layout.addWidget(self.name_label)

        self.size_label = QLabel("")
        self.size_label.setAlignment(Qt.AlignCenter)
        self.size_label.setStyleSheet("color: #999; font-size: 11px; border: none;")
        card_layout.addWidget(self.size_label)

        outer.addWidget(card)
        self.hide()

    def show_for(self, total: int) -> None:
        self.bar.setValue(0)
        self.title_label.setText(f"Eliminazione di {total} file in corso...")
        self.name_label.setText("")
        self.size_label.setText("0.00 GB cancellati")
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def update_progress(self, done: int, total: int, name: str, gb_done: float, gb_total: float) -> None:
        pct = int(done * 100 / total) if total else 100
        self.bar.setValue(pct)
        self.name_label.setText(f"{done}/{total} — {name}")
        self.size_label.setText(f"{gb_done:.2f} GB cancellati su {gb_total:.2f} GB")

    def hide_overlay(self) -> None:
        self.hide()

    def sync_geometry(self) -> None:
        """Da richiamare quando la finestra principale cambia
        dimensione, per tenere l'overlay sempre a schermo intero."""
        if self.isVisible() and self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
