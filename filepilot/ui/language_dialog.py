"""
ui/language_dialog.py
RICHIESTA: "il primo run deve essere in inglese e devi poter scegliere
la lingua da subito" — questo dialogo compare PRIMA di tutto il resto
del primo avvio (prima della guida rapida/Termini, prima del tour: vedi
main_window.py, flag di config "language_chosen"), scritto in inglese
di default (vedi filepilot/i18n.py, DEFAULT_LANGUAGE = "en"), cosi' chi
apre TUF per la prima volta puo' scegliere subito tra le lingue
disponibili senza dover prima leggere niente in italiano.

Una volta scelta, la lingua si applica immediatamente al resto del
flusso di primo avvio (guida rapida, Termini, tour) — vedi
main_window._show_first_run_guide(). Richiamabile anche in seguito da
Impostazioni per cambiare lingua in qualsiasi momento.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup, QRadioButton,
)

from filepilot.ui.branding import app_icon, enable_dark_titlebar, TUF_ORANGE
from filepilot.i18n import tr, SUPPORTED_LANGUAGES, LANGUAGE_NAMES, get_language


class LanguageDialog(QDialog):
    """Selettore lingua. is_first_run=True toglie il pulsante di
    chiusura nativo (X) — al primissimo avvio la scelta e' un passo
    obbligato del flusso, non opzionale come quando si riapre da
    Impostazioni."""

    def __init__(self, parent=None, is_first_run: bool = False):
        super().__init__(parent)
        self._is_first_run = is_first_run
        self.selected_language = get_language()

        self.setWindowTitle(tr("lang_dialog.window_title"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(360)
        if is_first_run:
            self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(4)

        title = QLabel(tr("lang_dialog.title"))
        title.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel(tr("lang_dialog.subtitle"))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #999; font-size: 11.5px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        self._group = QButtonGroup(self)
        for lang in SUPPORTED_LANGUAGES:
            radio = QRadioButton(LANGUAGE_NAMES[lang])
            radio.setStyleSheet(
                "QRadioButton { color: #eee; font-size: 13px; padding: 6px 2px; }"
            )
            radio.setChecked(lang == self.selected_language)
            radio.toggled.connect(lambda checked, l=lang: checked and self._on_selected(l))
            self._group.addButton(radio)
            layout.addWidget(radio)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.continue_btn = QPushButton(tr("lang_dialog.continue_btn"))
        self.continue_btn.setStyleSheet(
            f"QPushButton {{ background-color: {TUF_ORANGE}; color: #1a1a1a; border: none;"
            " border-radius: 5px; padding: 8px 22px; font-weight: 700; }"
            "QPushButton:hover { background-color: #ff8a3d; }"
        )
        self.continue_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.continue_btn)
        layout.addSpacing(14)
        layout.addLayout(btn_row)

        enable_dark_titlebar(self)

    def _on_selected(self, lang: str) -> None:
        self.selected_language = lang

    def closeEvent(self, event) -> None:
        # Al primissimo avvio la scelta lingua e' obbligata quanto i
        # Termini nella guida rapida che segue (vedi quick_guide_dialog
        # .py): niente X per bypassarla. Nei richiami successivi da
        # Impostazioni, invece, si puo' chiudere senza cambiare nulla.
        if self._is_first_run:
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self._is_first_run:
            return
        super().reject()
