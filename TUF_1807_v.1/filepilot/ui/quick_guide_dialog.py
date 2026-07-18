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
from filepilot.i18n import tr

def _guide_html() -> str:
    return f"""
<div style="color:#ddd; font-size:13px; line-height:145%;">

<p style="color:{TUF_ORANGE}; font-size:20px; font-weight:700; margin-bottom:2px;">
{tr("guide.welcome_title")}</p>
<p style="color:#999; font-size:12px; margin-top:0px;">
{tr("guide.welcome_subtitle")}</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">{tr("guide.what_is_title")}</p>
<p>{tr("guide.what_is_body")}</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">{tr("guide.how_start_title")}</p>
<p>
{tr("guide.how_start_body")}
</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">{tr("guide.duplicates_title")}</p>
<p>{tr("guide.duplicates_body")}</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">{tr("guide.voice_title")}</p>
<p>{tr("guide.voice_body")}</p>

<p style="color:{TUF_ORANGE}; font-size:14px; font-weight:700;">{tr("guide.more_title")}</p>
<p>{tr("guide.more_body")}</p>

<p style="color:#888; font-size:11px; margin-top:14px;">
{tr("guide.footer_note")}</p>

</div>
"""


class QuickGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("guide.window_title"))
        self.setWindowIcon(app_icon())
        self.setMinimumSize(520, 600)

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QLabel(_guide_html())
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
        self.terms_checkbox = QCheckBox(tr("guide.terms_checkbox"))
        self.terms_checkbox.setStyleSheet("color: #ddd; font-size: 11.5px;")
        self.terms_checkbox.stateChanged.connect(self._on_terms_toggled)
        terms_row.addWidget(self.terms_checkbox, stretch=1)

        read_terms_btn = QPushButton(tr("guide.read_terms_btn"))
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
        self.ok_btn = QPushButton(tr("guide.ok_btn"))
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
                self, tr("guide.terms_missing_title"),
                tr("guide.terms_missing_body"),
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

    # BUG RISOLTO ("l'utente puo' chiudere la finestra con la X o Esc
    # senza aver spuntato i Termini, e la guida non si ripropone piu'"):
    # il pulsante "Ho capito, inizia" restava disabilitato finche' i
    # Termini non venivano accettati, ma QDialog chiude comunque la
    # finestra su reject() (X della finestra, Esc, Alt+F4), che non
    # passa da _on_accept(). main_window.py segnava pero' "guide_seen"
    # a True subito dopo l'exec(), a prescindere dall'esito: risultato,
    # l'accettazione era bypassabile e non veniva piu' richiesta.
    # Ora chiudere la finestra senza aver accettato i Termini viene
    # semplicemente ignorato (il dialogo resta aperto): l'unico modo
    # di procedere e' spuntare la casella e premere "Ho capito, inizia".
    def closeEvent(self, event) -> None:
        if not self.terms_checkbox.isChecked():
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        # Esc chiama reject() di default: stesso blocco di closeEvent,
        # cosi' anche il tasto Esc non permette di bypassare i Termini.
        if not self.terms_checkbox.isChecked():
            return
        super().reject()
