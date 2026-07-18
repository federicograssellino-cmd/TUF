"""
ui/bottom_bar.py
Barra comandi in basso: Apri cartella, Indietro, Avanti, Elimina, Undo,
Comando vocale (con onda audio in background), Impostazioni. Il
contatore file e' mostrato invece nel riquadro dell'anteprima (in
basso a destra).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSizePolicy, QProgressBar,
)

from filepilot.ui.mic_button import MicButton
from filepilot.ui.branding import TUF_ORANGE


class BottomBar(QWidget):
    open_folder_clicked = Signal()
    back_clicked = Signal()
    next_clicked = Signal()
    delete_clicked = Signal()
    undo_clicked = Signal()
    voice_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # RICHIESTA: "crea una barra di loading fin quando i comandi
        # non sono tutti fluidi, cosi' l'utente ha idea di quando
        # poter iniziare a lavorare senza problemi" — striscia sottile
        # sempre presente IN CIMA a questa barra (l'altezza fissa di
        # BottomBar cresce di 4px UNA VOLTA SOLA per farle spazio, e
        # non cambia mai piu': mostrarla/nasconderla sposta solo 4px
        # di spazio DENTRO un contenitore gia' a altezza fissa, quindi
        # non puo' MAI causare il tipo di ridimensionamento involontario
        # della finestra gia' risolto altrove in questa stessa barra
        # (vedi status_label piu' sotto) — qui il rischio semplicemente
        # non esiste, la larghezza non e' mai in gioco.
        self.setFixedHeight(50)
        self.setStyleSheet("background-color: #202020; border-top: 1px solid #333;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #202020; border: none; }"
            f"QProgressBar::chunk {{ background-color: {TUF_ORANGE}; }}"
        )
        self.progress_bar.hide()
        outer.addWidget(self.progress_bar)

        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        outer.addWidget(row, stretch=1)

        self._status_full_text = ""

        BTN_HEIGHT = 36

        self.btn_open = QPushButton("📁 Apri cartella")
        self.btn_back = QPushButton("◀ Indietro")
        self.btn_next = QPushButton("Avanti ▶")
        self.btn_delete = QPushButton("🗑 Elimina (0)")
        self.btn_undo = QPushButton("↺ Undo")
        # RICHIESTA: il pulsante "Impostazioni" che stava qui (tra
        # Comando vocale e Undo) e' stato spostato nel pannello
        # cartelle, vicino a modifica/cestino (vedi folder_panel.py,
        # settings_btn) — qui era scollegato dagli altri controlli
        # legati alle cartelle di destinazione.

        for b in (self.btn_open, self.btn_back, self.btn_next,
                  self.btn_delete, self.btn_undo):
            b.setFixedHeight(BTN_HEIGHT)
            b.setStyleSheet(
                "QPushButton { color: #ddd; background-color: #333; border: none;"
                " padding: 6px 12px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #444; }"
                "QPushButton:disabled { color: #666; }"
            )
            layout.addWidget(b)

        self.mic_button = MicButton()
        self.mic_button.setFixedWidth(210)
        self.mic_button.setFixedHeight(BTN_HEIGHT)
        self.mic_button.clicked.connect(self.voice_clicked.emit)
        layout.addWidget(self.mic_button)

        layout.addStretch(1)

        # Il testo di stato ha un punto FISSO a destra e si allunga
        # verso sinistra quando serve piu' spazio, invece di partire da
        # sinistra e crescere verso destra: stretch=1 gli fa occupare
        # tutto lo spazio libero fra i pulsanti e source_label, e
        # AlignRight tiene il testo incollato al bordo destro di quello
        # spazio (quindi appena prima di source_label) qualunque sia la
        # sua lunghezza.
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #ccc; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # BUG RISOLTO ("appena parte il conteggio duplicati la finestra
        # si allarga verso destra e il pannello cartelle sparisce",
        # segnalato con timing preciso): questa label mostra il nome
        # del file in corso durante la scansione (set_status, sotto),
        # che puo' essere lungo. Senza vincoli, la SUA richiesta di
        # spazio (basata sul testo intero) si sommava al calcolo della
        # dimensione minima di tutta la finestra — ogni volta che
        # arrivava un nome file piu' lungo del precedente, la finestra
        # doveva allargarsi per "farcelo stare", schiacciando il resto.
        # QSizePolicy.Ignored dice al layout di NON considerare la
        # larghezza del testo come un vincolo: la label puo' essere
        # compressa quanto serve, il testo troppo lungo viene troncato
        # con "..." (vedi _update_status_display) invece di spingere
        # fuori tutto il resto.
        self.status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.status_label, stretch=1)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.source_label)

        self.btn_open.clicked.connect(self.open_folder_clicked.emit)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        self.btn_next.clicked.connect(self.next_clicked.emit)
        self.btn_delete.clicked.connect(self.delete_clicked.emit)
        self.btn_undo.clicked.connect(self.undo_clicked.emit)

    def set_undo_enabled(self, enabled: bool) -> None:
        self.btn_undo.setEnabled(enabled)

    def set_status(self, text: str) -> None:
        self._status_full_text = text
        self._update_status_display()

    def _update_status_display(self) -> None:
        fm = self.status_label.fontMetrics()
        available = max(self.status_label.width(), 50)
        elided = fm.elidedText(self._status_full_text, Qt.ElideMiddle, available)
        self.status_label.setText(elided)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_status_display()

    def set_listening(self, listening: bool) -> None:
        self.mic_button.set_active(listening)

    def push_mic_level(self, level: float) -> None:
        self.mic_button.push_level(level)

    def reset_mic_levels(self) -> None:
        self.mic_button.reset()

    # ------------------------------------------------- barra di carico
    def show_progress_indeterminate(self) -> None:
        """Per operazioni di cui non si conosce il totale in anticipo
        (es. scansione di una cartella: si scoprono i file mano a
        mano). Mostra una barra 'a onda' che va avanti e indietro,
        senza percentuale — comunica comunque chiaramente 'e' in
        corso qualcosa, aspetta'."""
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()

    def set_progress(self, done: int, total: int) -> None:
        """Per operazioni con un totale noto (es. controllo duplicati:
        si sa gia' quanti file vanno controllati)."""
        if total <= 0:
            self.show_progress_indeterminate()
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_bar.show()

    def hide_progress(self) -> None:
        self.progress_bar.hide()
