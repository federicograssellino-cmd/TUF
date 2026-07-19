"""
ui/branding.py
Identita' visiva di TideUp File (TUF): icona dell'applicazione, una
intestazione "brandizzata" (logo + scritta) da mettere in cima ad ogni
finestra/dialogo, e una funzione per scurire la barra del titolo nativa
di Windows, cosi' che non ci si affidi piu' solo alla barra del titolo
di Windows (che di suo mostra un'icona generica e resta chiara/bianca)
per capire in che programma ci si trova. L'icona viene disegnata a
runtime con QPainter invece di essere un file immagine fisso: resta
nitida a qualunque dimensione/DPI e non serve spedire un asset binario
separato con l'app.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

TUF_ORANGE = "#F2711C"

_icon_cache: QIcon | None = None
_pixmap_cache: dict[int, QPixmap] = {}


def _render_icon_pixmap(size: int) -> QPixmap:
    if size in _pixmap_cache:
        return _pixmap_cache[size]
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#1f1f1f"))
    painter.setPen(Qt.NoPen)
    radius = size * 0.22
    painter.drawRoundedRect(0, 0, size, size, radius, radius)
    font = QFont("Arial", max(1, int(size * 0.38)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(TUF_ORANGE))
    painter.drawText(pix.rect(), Qt.AlignCenter, "TUF")
    painter.end()
    _pixmap_cache[size] = pix
    return pix


def app_icon() -> QIcon:
    """Icona dell'app: da usare con setWindowIcon() su OGNI finestra
    (principale e dialoghi), cosi' anche la barra del titolo/la
    taskbar di Windows mostrano il marchio TUF invece dell'icona
    generica di Python/Qt."""
    global _icon_cache
    if _icon_cache is not None:
        return _icon_cache
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_render_icon_pixmap(size))
    _icon_cache = icon
    return icon


def enable_dark_titlebar(widget: QWidget) -> None:
    """Su Windows 10/11 scurisce la barra del titolo NATIVA (dove
    stanno riduci/ingrandisci/chiudi), che di suo Windows disegna
    sempre chiara anche se il resto dell'app usa un tema scuro. Va
    chiamata DOPO che la finestra ha un handle nativo valido, quindi
    tipicamente a fine __init__ (dopo aver costruito il layout) o
    subito prima di show(): prima di allora winId() puo' non esistere
    ancora. Non fa nulla (silenziosamente) se non siamo su Windows o se
    l'API non e' disponibile, cosi' resta sicura da chiamare sempre,
    anche durante lo sviluppo/test su altri sistemi."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass  # meglio una barra del titolo chiara che un crash


class BrandedHeader(QWidget):
    """Intestazione con il logo di TUF: l'icona (che ha gia' la scritta
    "TUF" disegnata dentro) piu' un sottotitolo, con un filo arancione
    in basso. Va messa in cima al layout di ogni finestra/dialogo (vedi
    main_window.py, settings_dialog.py, import_dialog.py, dashboard.py)
    per dare a tutte le pagine un'intestazione coerente e "stilosa"
    invece che quella generica del sistema operativo.

    NOTA v0.20: prima c'era ANCHE una scritta "TUF" separata accanto
    all'icona, che essendo l'icona stessa gia' un quadratino con "TUF"
    disegnato dentro, risultava scritta due volte ("TUF TUF"). Ora
    resta solo l'icona (l'istanza a sinistra, come richiesto) con il
    sottotitolo sotto/accanto."""

    def __init__(self, subtitle: str = "Tide Up File", corner_widget: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("TufBrandedHeader")
        self.setStyleSheet(
            "#TufBrandedHeader { border-bottom: 2px solid " + TUF_ORANGE + "; }"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 8)
        row.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(_render_icon_pixmap(36))
        icon_label.setFixedSize(36, 36)
        row.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.addStretch(1)
        caption = QLabel(subtitle.upper())
        caption.setStyleSheet("color: #999; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        text_col.addWidget(caption)
        text_col.addStretch(1)
        row.addLayout(text_col)
        row.addStretch(1)

        # RICHIESTA: "le impostazioni mettile sulla stessa riga lato
        # destro del logo in alto a sinistra" — un chiamante (oggi solo
        # main_window.py) puo' passare un widget qui, che finisce nella
        # STESSA riga del logo, allineato al bordo destro. Nessun altro
        # utilizzo di BrandedHeader (Impostazioni, Riepilogo cartella,
        # ecc.) lo passa, quindi per loro il comportamento resta
        # identico a prima (solo logo + sottotitolo).
        if corner_widget is not None:
            row.addWidget(corner_widget)
