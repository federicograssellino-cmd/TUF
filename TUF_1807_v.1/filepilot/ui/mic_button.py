"""
ui/mic_button.py
Pulsante del comando vocale, disegnato a mano per poter mostrare:
- quando spento: icona microfono con una sbarra diagonale (muto)
- quando acceso: sfondo con un'onda audio animata che riflette il
  livello reale captato dal microfono, cosi' si vede a colpo d'occhio
  se sta ascoltando
"""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy

BAR_COUNT = 28


class MicButton(QWidget):
    """Pulsante microfono con onda audio in background quando attivo."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(32)
        self._active = False
        self._levels: deque[float] = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self._label = "Comando vocale (C)"

    def set_active(self, active: bool) -> None:
        self._active = active
        self._label = "Ascolto attivo (C per fermare)" if active else "Comando vocale (C)"
        if not active:
            self._levels = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self.update()

    def push_level(self, level: float) -> None:
        """Aggiunge un nuovo campione di livello audio (0.0-1.0) e
        ridisegna subito la barra, dando l'effetto di onda animata."""
        self._levels.append(max(0.0, min(1.0, level)))
        if self._active:
            self.update()

    def reset(self) -> None:
        self._levels = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        # sfondo arrotondato
        bg_color = QColor("#b33333") if self._active else QColor("#333333")
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 4, 4)

        # onda audio, solo quando attivo
        if self._active:
            painter.setBrush(QColor(255, 255, 255, 90))
            n = len(self._levels)
            if n > 0:
                bar_w = rect.width() / n
                mid_y = rect.height() / 2
                for i, level in enumerate(self._levels):
                    h = max(2.0, level * (rect.height() - 8))
                    x = i * bar_w
                    painter.drawRoundedRect(
                        QRectF(x + 1, mid_y - h / 2, max(1.0, bar_w - 2), h), 1, 1
                    )

        # icona microfono (con sbarra se spento)
        icon_rect = QRectF(10, rect.height() / 2 - 9, 18, 18)
        painter.setPen(QPen(QColor("#fff"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.setFont(QFont("Segoe UI Emoji", 12))
        painter.drawText(icon_rect.adjusted(-4, -4, 4, 4), Qt.AlignCenter, "🎤")
        if not self._active:
            pen = QPen(QColor("#ff5555"), 2.5)
            painter.setPen(pen)
            painter.drawLine(
                int(icon_rect.left()), int(icon_rect.top()),
                int(icon_rect.right()), int(icon_rect.bottom()),
            )

        # etichetta testuale
        painter.setPen(QColor("#fff") if self._active else QColor("#ddd"))
        painter.setFont(QFont("Segoe UI", 9))
        text_rect = QRectF(36, 0, rect.width() - 42, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._label)
