"""
ui/confirm_overlay.py
Finestra di conferma eliminazione mostrata AL CENTRO, sopra il
riquadro di anteprima, cosi' da essere immediatamente visibile sia
per chi conferma con mouse/tastiera sia per chi usa il comando
vocale ("sì"/"conferma" oppure "no"/"annulla").
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton


class DeleteConfirmOverlay(QWidget):
    """Overlay semi-trasparente con una scheda centrale di conferma.
    Resta nascosto finche' non viene chiamato show_for()."""

    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 165);")
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setFixedWidth(380)
        card.setStyleSheet(
            "QFrame { background-color: #262626; border-radius: 12px;"
            " border: 2px solid #cc4444; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(10)

        icon = QLabel("🗑️")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 38px; border: none;")
        card_layout.addWidget(icon)

        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("color: #fff; font-size: 15px; font-weight: 600; border: none;")
        card_layout.addWidget(self.text_label)

        hint = QLabel('Di\' "sì" / "conferma" oppure "no" / "annulla" — o clicca')
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; font-size: 11px; border: none;")
        card_layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self.yes_btn = QPushButton("✅ Sì, elimina")
        self.yes_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: #fff; border: none;"
            " padding: 10px; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #d9483a; }"
        )
        self.no_btn = QPushButton("❌ Annulla")
        self.no_btn.setStyleSheet(
            "QPushButton { background-color: #3a3a3a; color: #ddd; border: none;"
            " padding: 10px; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_row.addWidget(self.yes_btn)
        btn_row.addWidget(self.no_btn)
        card_layout.addLayout(btn_row)

        outer.addWidget(card)

        self.yes_btn.clicked.connect(self.confirmed.emit)
        self.no_btn.clicked.connect(self.cancelled.emit)

        self.hide()

    def show_for(self, filename: str) -> None:
        self.text_label.setText(f'Eliminare "{filename}"?')
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()

    def hide_overlay(self) -> None:
        self.hide()

    def sync_geometry(self) -> None:
        """Da richiamare quando la finestra principale cambia
        dimensione, per tenere l'overlay sempre a schermo intero."""
        if self.isVisible() and self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.confirmed.emit()
        elif event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)
