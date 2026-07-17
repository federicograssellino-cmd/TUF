"""
ui/quick_guide_dialog.py
RICHIESTA: "crea anche una guida veloce e pratica che si apre in una
finestra appena apri per la prima volta il programma" — un dialogo che
compare in automatico al PRIMO avvio (vedi main_window.py, flag di
config "guide_seen": una volta chiuso non si riapre da solo), e resta
comunque richiamabile a mano da Impostazioni > Info ("Guida rapida"),
per chi la chiude troppo in fretta o la vuole rileggere.

RICHIESTA successiva: "metti accetto termini e condizioni nel primo
riquadro all'apertura" — la stessa nota pratica scritta dentro
TERMINI_E_CONDIZIONI.pdf ("e' opportuno affiancare... una schermata di
accettazione espressa prima del primo uso") diceva esattamente questo:
ora il pulsante per chiudere la guida resta disabilitato finche' non
si spunta "Ho letto e accetto i Termini e Condizioni", con un link
diretto per aprirli e leggerli prima di accettare.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget,
    QPushButton, QFrame, QCheckBox, QMessageBox,
)

from filepilot.ui.branding import app_icon, enable_dark_titlebar, TUF_ORANGE

_GUIDE_HTML = f"""
<div style="color:#ddd; font-size:13px; line-height:145%;">

<p style="color:{TUF_ORANGE}; font-size:20px; font-weight:700; margin-bottom:2px;">
Benvenuto/a in TUF</p>
<p style="color:#999; font-size:12px; margin-top:0px;">
Come funziona, in due minuti.</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">Cos'è TUF</p>
<p>TUF ti aiuta a scorrere, catalogare e ripulire foto, video, documenti e molti
altri formati dentro una cartella, trovando anche i file duplicati.
Gira tutto sul tuo computer: non salva mai il contenuto dei file che apri e
non manda niente online (vedi "no log" nella scheda Info di Impostazioni).</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">Come iniziare</p>
<p>
1. Apri una cartella da esplorare (pulsante cartella in alto).<br>
2. Scegli i formati che ti interessano in <b>Impostazioni &gt; Formati</b>, oppure
al volo dalla tendina <b>Filtri</b> in basso a sinistra.<br>
3. Scorri i file con i tasti <b>avanti/indietro</b> (frecce, mouse o comando vocale).<br>
4. Se un file non ti serve, usa il tasto <b>cestino</b>: va nel Cestino interno di
TUF, recuperabile con <b>Annulla</b> finché non lo svuoti.
</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">Trovare i duplicati</p>
<p>Premi <b>Cerca duplicati</b>: TUF li raggruppa e te li mostra fianco a fianco.
Puoi tenerli tutti, cancellare le copie (tenendo la prima), cancellare
tutto un gruppo, oppure scegliere colonna per colonna con i pulsanti
"seleziona/deseleziona colonna". Niente sparisce senza che tu lo veda:
i file segnati per l'eliminazione restano visibili ma marcati, finché
non confermi.</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">Comando vocale (facoltativo)</p>
<p>Se lo attivi, puoi dire "avanti", "indietro", "cestino" o "annulla" per
navigare senza mouse. Usa il servizio gratuito di Google per capire cosa
dici (unica eccezione al funzionamento locale — vedi Termini e Condizioni
e Privacy, in Impostazioni &gt; Info, per i dettagli). È del tutto facoltativo: TUF funziona
identico anche solo con mouse e tastiera.</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">Dove trovare il resto</p>
<p>Il tasto <b>⚙ Impostazioni</b>, accanto al logo in alto, ha tutto il resto:
i formati riconosciuti, le informazioni sull'app (scheda Info, con anche
i Termini e Condizioni), e uno spazio per scriverci consigli o formati
mancanti.</p>

<p style="color:#888; font-size:11px; margin-top:14px;">
Questa guida si riapre in qualsiasi momento da Impostazioni &gt; Info.</p>

</div>
"""


class QuickGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guida rapida — TUF")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(520, 600)

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QLabel(_GUIDE_HTML)
        content.setWordWrap(True)
        content.setTextFormat(Qt.RichText)
        content.setAlignment(Qt.AlignTop)
        content.setContentsMargins(6, 6, 6, 6)
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        # --- riquadro accettazione Termini e Condizioni ---
        terms_box = QFrame()
        terms_box.setStyleSheet(
            "QFrame { background-color: #232323; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        terms_layout = QVBoxLayout(terms_box)

        terms_row = QHBoxLayout()
        self.terms_checkbox = QCheckBox("Ho letto e accetto i Termini e Condizioni")
        self.terms_checkbox.setStyleSheet("color: #ddd; font-size: 11.5px;")
        self.terms_checkbox.stateChanged.connect(self._on_terms_toggled)
        terms_row.addWidget(self.terms_checkbox, stretch=1)

        read_terms_btn = QPushButton("Leggi i Termini")
        read_terms_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #ddd; border: 1px solid #555;"
            " border-radius: 4px; padding: 4px 10px; font-size: 11px; }"
            "QPushButton:hover { background-color: #3d3d3d; }"
        )
        read_terms_btn.clicked.connect(self._open_terms)
        terms_row.addWidget(read_terms_btn)
        terms_layout.addLayout(terms_row)
        layout.addWidget(terms_box)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.ok_btn = QPushButton("Ho capito, inizia")
        self.ok_btn.setEnabled(False)
        self.ok_btn.setStyleSheet(
            f"QPushButton {{ background-color: {TUF_ORANGE}; color: #1a1a1a; border: none;"
            " border-radius: 5px; padding: 8px 20px; font-weight: 700; }"
            "QPushButton:hover { background-color: #ff8a3d; }"
            "QPushButton:disabled { background-color: #444; color: #888; }"
        )
        self.ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self.ok_btn)
        layout.addLayout(btn_row)

        enable_dark_titlebar(self)

    def _on_terms_toggled(self, _state) -> None:
        self.ok_btn.setEnabled(self.terms_checkbox.isChecked())

    def _open_terms(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent.parent
        pdf_path = base_dir / "TERMINI_E_CONDIZIONI.pdf"
        if pdf_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
        else:
            QMessageBox.warning(
                self, "Termini e Condizioni",
                "Non trovo il file TERMINI_E_CONDIZIONI.pdf nella cartella del programma."
            )

    def _on_accept(self) -> None:
        try:
            from filepilot.config import ConfigManager
            cfg = ConfigManager()
            cfg.set("terms_accepted_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
            cfg.save()
        except Exception:
            pass  # l'accettazione resta comunque valida per questa sessione anche se il salvataggio fallisce
        self.accept()
