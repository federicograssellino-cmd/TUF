"""
ui/onboarding_tour.py
Tour interattivo "a riflettore": al primo avvio (dopo la guida testuale
con i Termini e Condizioni, vedi quick_guide_dialog.py), questo overlay
evidenzia UNO ALLA VOLTA i pulsanti/pannelli VERI della finestra
principale (non finti screenshot), con una nuvoletta che spiega a cosa
serve quello specifico controllo e un pulsante "Avanti" per passare al
successivo. Si puo' sempre saltare con "Salta tour" o con Esc.

RICHIESTA: "non si può creare una guida interattiva al primo avvio?" ->
"sarebbe figo!" — a differenza della guida testuale gia' esistente
(solo da leggere), qui l'utente vede DAVVERO dove sono i comandi mentre
gliene viene spiegato lo scopo, uno alla volta.

Anche richiamabile in qualsiasi momento da Impostazioni > Info
("Tour interattivo"), esattamente come la guida rapida testuale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, QRect, QPoint, QEvent, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QRegion
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from filepilot.ui.branding import TUF_ORANGE
from filepilot.i18n import tr

# Spazio (px) lasciato intorno al widget evidenziato prima di
# disegnare il "buco" nell'overlay scuro, cosi' il riflettore non
# aderisce esattamente al bordo del widget (sembrerebbe tagliato).
SPOTLIGHT_PADDING = 8
CALLOUT_MARGIN = 14
CALLOUT_WIDTH = 300


@dataclass
class TourStep:
    """Un passo del tour. get_target viene richiamato al momento di
    mostrare il passo (non prima), cosi' punta sempre al widget VERO
    e alla sua posizione ATTUALE sullo schermo, anche se la finestra
    e' stata ridimensionata o il layout e' cambiato nel frattempo."""
    get_target: Callable[[], QWidget | None]
    title: str
    text: str


class OnboardingTour(QWidget):
    """Overlay a schermo intero (sopra il centralWidget della finestra
    principale) che mostra un riflettore + nuvoletta esplicativa su un
    widget reale per volta. Blocca l'interazione con il resto della UI
    finche' il tour e' aperto, cosi' non si rischia di spostare/
    eliminare per sbaglio un file durante la spiegazione."""

    finished = Signal()

    def __init__(self, steps: list[TourStep], parent: QWidget):
        super().__init__(parent)
        self._steps = steps
        self._index = -1
        self._target_rect = QRect()

        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        # --------------------------------------------------- nuvoletta
        self.callout = QFrame(self)
        self.callout.setFixedWidth(CALLOUT_WIDTH)
        self.callout.setStyleSheet(
            "QFrame { background-color: #262626; border-radius: 10px;"
            f" border: 2px solid {TUF_ORANGE}; }}"
        )
        c_layout = QVBoxLayout(self.callout)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(6)

        self.step_label = QLabel("")
        self.step_label.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 10px; font-weight: 700; border: none;")
        c_layout.addWidget(self.step_label)

        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #fff; font-size: 14px; font-weight: 700; border: none;")
        c_layout.addWidget(self.title_label)

        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("color: #ccc; font-size: 12px; border: none;")
        c_layout.addWidget(self.text_label)

        btn_row = QHBoxLayout()
        self.skip_btn = QPushButton(tr("tour.skip_btn"))
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #999; border: none;"
            " padding: 6px 8px; font-size: 11px; }"
            "QPushButton:hover { color: #ddd; }"
        )
        self.skip_btn.clicked.connect(self.skip)
        btn_row.addWidget(self.skip_btn)
        btn_row.addStretch(1)

        self.next_btn = QPushButton(tr("tour.next_btn"))
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet(
            f"QPushButton {{ background-color: {TUF_ORANGE}; color: #1a1a1a; border: none;"
            " border-radius: 5px; padding: 7px 18px; font-weight: 700; font-size: 12px; }"
            "QPushButton:hover { background-color: #ff8a3d; }"
        )
        self.next_btn.clicked.connect(self.next_step)
        btn_row.addWidget(self.next_btn)
        c_layout.addLayout(btn_row)

        self.callout.hide()

        parent.installEventFilter(self)

    # ------------------------------------------------------- controllo
    def start(self) -> None:
        if not self._steps:
            self._end()
            return
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._index = -1
        self.next_step()

    def skip(self) -> None:
        self._end()

    def next_step(self) -> None:
        self._index += 1
        if self._index >= len(self._steps):
            self._end()
            return

        step = self._steps[self._index]
        target = step.get_target()
        if target is None or not target.isVisible():
            # il widget non c'e'/non e' visibile in questo momento
            # (es. una scheda non ancora costruita): salta al passo dopo
            # invece di mostrare un riflettore vuoto
            self.next_step()
            return

        self.setGeometry(self.parentWidget().rect())
        self._target_rect = self._widget_rect_in_overlay(target)

        is_last = self._index == len(self._steps) - 1
        self.step_label.setText(tr("tour.step_label", current=self._index + 1, total=len(self._steps)))
        self.title_label.setText(step.title)
        self.text_label.setText(step.text)
        self.next_btn.setText(tr("tour.finish_btn") if is_last else tr("tour.next_btn"))

        self._position_callout()
        self.callout.show()
        self.callout.raise_()
        self.update()

    def _end(self) -> None:
        self.callout.hide()
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # -------------------------------------------------------- geometria
    def _widget_rect_in_overlay(self, widget: QWidget) -> QRect:
        """Converte la posizione/dimensione del widget target in
        coordinate di QUESTO overlay, passando per le coordinate
        globali dello schermo: funziona sempre, indipendentemente da
        quanti livelli di layout separino il widget dall'overlay."""
        top_left_global = widget.mapToGlobal(QPoint(0, 0))
        top_left_local = self.mapFromGlobal(top_left_global)
        return QRect(top_left_local, widget.size())

    def _position_callout(self) -> None:
        target = self._target_rect
        overlay_rect = self.rect()
        callout_h = self.callout.sizeHint().height()
        callout_w = CALLOUT_WIDTH

        space_below = overlay_rect.bottom() - target.bottom()
        space_above = target.top() - overlay_rect.top()

        if space_below >= callout_h + CALLOUT_MARGIN:
            y = target.bottom() + CALLOUT_MARGIN
        elif space_above >= callout_h + CALLOUT_MARGIN:
            y = target.top() - CALLOUT_MARGIN - callout_h
        else:
            # ne' sopra ne' sotto c'e' abbastanza spazio (widget molto
            # alto, es. il pannello cartelle): centra verticalmente
            y = max(CALLOUT_MARGIN, (overlay_rect.height() - callout_h) // 2)

        # allineamento orizzontale: centrato sul target, ma sempre
        # dentro i bordi dell'overlay
        x = target.center().x() - callout_w // 2
        x = max(CALLOUT_MARGIN, min(x, overlay_rect.width() - callout_w - CALLOUT_MARGIN))
        y = max(CALLOUT_MARGIN, min(y, overlay_rect.height() - callout_h - CALLOUT_MARGIN))

        self.callout.setGeometry(x, y, callout_w, callout_h)

    # ------------------------------------------------------------ eventi
    def eventFilter(self, obj, event) -> bool:
        if obj is self.parentWidget() and event.type() == QEvent.Resize:
            self.setGeometry(self.parentWidget().rect())
            if self._index >= 0:
                self._position_callout()
                self.update()
        return False

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.skip()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.next_step()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        hole = self._target_rect.adjusted(
            -SPOTLIGHT_PADDING, -SPOTLIGHT_PADDING, SPOTLIGHT_PADDING, SPOTLIGHT_PADDING
        )

        full_region = QRegion(self.rect())
        hole_region = QRegion(hole, QRegion.Rectangle)
        painter.setClipRegion(full_region.subtracted(hole_region))
        painter.fillRect(self.rect(), QColor(0, 0, 0, 175))
        painter.setClipping(False)

        if not hole.isEmpty():
            pen = QPen(QColor(TUF_ORANGE))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(hole, 10, 10)
