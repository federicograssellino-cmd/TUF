"""
ui/folder_panel.py
Pannello destro: solo cartelle di destinazione. Riempie prima la
colonna 1 dall'alto verso il basso; solo quando lo spazio visibile
finisce passa alla colonna 2. Quando anche la colonna 2 riempie lo
spazio visibile, compare la barra di scorrimento verticale.

Due modalita':
- normale: un clic su una riga sposta li' il file corrente; un clic
  sul nome apre la cartella in Esplora risorse. Due colonne se serve.
- modifica (tasto matita): il numero diventa un campo di testo
  modificabile da tastiera (niente frecce). Le cartelle si dispongono
  in una sola colonna e si possono trascinare per riordinarle: le
  altre scorrono in alto/basso con un'animazione per fare spazio,
  come in una lista riordinabile normale (non e' il drag "nativo" di
  Qt, che non permetterebbe di animare le righe vicine). Si puo' anche
  trascinare una cartella da Esplora risorse di Windows per
  aggiungerla come destinazione, in qualsiasi momento.

STILE (v0.19): le righe sono ora vere "schede" — angoli arrotondati
piu' morbidi, senza bordo colorato tutto intorno (che le faceva
sembrare "scatolette"): il colore che distingue ogni cartella resta
solo su una sottile barra di accento a sinistra e sul colore del
numero stesso, per un effetto piu' pulito e meno "pieno" (senza
riquadri/anelli che spezzano visivamente la riga).
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import (
    Qt, Signal, QUrl, QRect, QPropertyAnimation, QEasingCurve, QTimer,
)
from PySide6.QtGui import QDesktopServices, QFontMetrics, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFrame, QHBoxLayout, QSlider, QSizePolicy, QApplication,
)

from filepilot.config import FolderTarget

# Palette di colori distinti per le righe, ciclica. Toni scuri e
# desaturati per restare leggibili con testo chiaro sopra.
ROW_COLORS = [
    "#3a2d4d",  # viola
    "#2d4a4d",  # petrolio
    "#4d3a2d",  # marrone
    "#2d4d38",  # verde scuro
    "#4d2d3a",  # bordeaux
    "#2d3a4d",  # blu
    "#4d4a2d",  # ocra
    "#3d2d4d",  # prugna
]

# Versione piu' chiara/satura di ogni colore, usata SOLO come accento
# (barra a sinistra, colore del numero): i toni sopra sono
# pensati per uno sfondo pieno, qui invece serve un colore che risalti
# un po' di piu' su un piccolo dettaglio.
ROW_ACCENTS = [
    "#8a6fc9",  # viola
    "#5fb8bd",  # petrolio
    "#c9905f",  # marrone
    "#5fbd82",  # verde
    "#c96f8a",  # bordeaux
    "#6f8ac9",  # blu
    "#c9b85f",  # ocra
    "#a06fc9",  # prugna
]

DEFAULT_SIZE_LEVEL = 4  # ~35% della scala 1-10, dimensione di default delle cartelle

# sfondo unico per tutte le righe: continuo, nessun blocco colorato "a
# colonne". Il colore della cartella si vede solo sull'accento a
# sinistra e sul colore del numero (vedi _apply_background)
ROW_BACKGROUND = "#262626"
ROW_BACKGROUND_HOVER = "#2c2c2c"
ROW_RADIUS = 12


def count_files_in(path: str) -> int:
    try:
        with os.scandir(path) as it:
            return sum(1 for entry in it if entry.is_file())
    except OSError:
        return 0


COUNT_HIDE_THRESHOLD = 68  # oltre questa altezza riga, il conteggio file si nasconde per far spazio al nome


def _sizes_for(row_height: int) -> dict:
    """Calcola le dimensioni proporzionate di tutti gli elementi della
    riga a partire dall'altezza scelta, cosi' testo/icona/badge
    crescono e si rimpiccioliscono insieme. Il tetto massimo dei font
    (46px) e' scelto per coincidere con l'altezza massima raggiungibile
    dallo slider, cosi' non c'e' mai una zona in cui la riga continua
    a crescere ma il testo resta fermo (e sembra "vuota")."""
    return {
        "row_height": row_height,
        "badge_w": min(100, max(28, int(row_height * 0.55))),
        "badge_font": min(46, max(11, int(row_height * 0.36))),
        "icon_font": min(50, max(13, int(row_height * 0.42))),
        "name_font": min(46, max(12, int(row_height * 0.36))),
        "count_font": min(16, max(9, int(row_height * 0.20))),
        "close_size": min(34, max(18, int(row_height * 0.34))),
        "show_count": row_height <= COUNT_HIDE_THRESHOLD,
    }


class FolderRow(QFrame):
    """Una singola cartella, colorata. In modalita' normale e'
    cliccabile per spostarci il file corrente; in modalita' modifica
    il numero e' un campo di testo e la riga si puo' trascinare
    (trascinamento "fatto in casa", non QDrag, per poter animare le
    righe vicine mentre si sposta)."""

    clicked = Signal(str)              # path della cartella (modalita' normale)
    number_changed = Signal(str, int)  # path, nuovo numero (digitato)
    remove_requested = Signal(str)     # path
    drag_moved = Signal(object)        # se stessa, mentre viene trascinata
    drag_finished = Signal(object)     # se stessa, al rilascio

    DRAG_THRESHOLD = 6

    def __init__(self, target: FolderTarget, row_height: int, color: str,
                 edit_mode: bool, parent=None, accent: str | None = None):
        super().__init__(parent)
        self.target = target
        self._color = color
        self._accent = accent or color
        self._highlighted = False
        self._edit_mode = edit_mode
        self._press_pos = None
        self._is_dragging = False

        # la riga non deve determinare la sua larghezza dal contenuto
        # (altrimenti con testo grande trabocca fuori dal pannello):
        # la larghezza la decide sempre la colonna/il pannello
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 8, 2)
        # RICHIESTA ("tra numero, nome cartella e numero file ci sono
        # come delle bande verticali brutte"): lo spazio uniforme di
        # 10px tra OGNI elemento (numero, icona, nome, conteggio, x)
        # faceva sembrare la riga divisa in tanti segmenti separati
        # invece di un'unica riga coerente — specialmente tra icona e
        # nome, che concettualmente sono la STESSA cosa ("cartella
        # prova1") ma avevano lo stesso distacco visivo di elementi
        # scollegati tra loro (es. numero e icona). Ridotto lo spazio
        # generale e, soprattutto, icona+nome ora vivono in un loro
        # sotto-layout con una spaziatura molto piu' stretta (vedi
        # icon_name_row piu' sotto), cosi' si leggono come un blocco
        # unico invece che come due caselle separate da una banda.
        layout.setSpacing(6)

        # barra di accento colorata sul bordo sinistro: al posto di un
        # bordo colorato tutto intorno (che dava l'effetto "scatoletta"),
        # ora il colore della cartella si vede solo qui e sul colore
        # del testo del numero
        self.accent_bar = QFrame()
        self.accent_bar.setFixedWidth(5)
        layout.addWidget(self.accent_bar)

        self.number_badge: QLabel | None = None
        self.number_edit: QLineEdit | None = None

        if edit_mode:
            self.setCursor(Qt.OpenHandCursor)
            self.number_edit = QLineEdit(f"{target.number:02d}")
            self.number_edit.setValidator(QIntValidator(1, 999, self))
            self.number_edit.setAlignment(Qt.AlignCenter)
            self.number_edit.editingFinished.connect(self._commit_number_field)
            layout.addWidget(self.number_edit)
        else:
            self.setCursor(Qt.PointingHandCursor)
            self.number_badge = QLabel(f"{target.number:02d}")
            self.number_badge.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.number_badge)

        # RICHIESTA: "creiamo un tasto, che faccia capire subito, sulla
        # barra di ogni cartella per buttare dentro il file, mettilo
        # subito dopo il numero" — cliccare OVUNQUE sulla riga sposta
        # gia' il file corrente qui (vedi mousePressEvent), ma non era
        # abbastanza evidente/scoperto. Bottone dedicato, freccia verso
        # il basso, colorato con l'accento della cartella, subito dopo
        # il numero: stessa identica azione del clic sulla riga (emette
        # 'clicked'), ma visivamente inequivocabile ("butta qui").
        # Solo in modalita' normale: in modifica quello spazio serve al
        # trascinamento per riordinare.
        self.move_here_btn: QPushButton | None = None
        if not edit_mode:
            self.move_here_btn = QPushButton("⬇")
            self.move_here_btn.setToolTip("Sposta qui il file corrente")
            self.move_here_btn.setCursor(Qt.PointingHandCursor)
            self.move_here_btn.clicked.connect(lambda: self.clicked.emit(self.target.path))
            layout.addWidget(self.move_here_btn)

        # Icona cartella e nome INSIEME in un sotto-layout con
        # spaziatura stretta: concettualmente sono un'unica cosa
        # ("cartella prova1"), quindi si leggono come un blocco solo
        # invece che come due caselle separate (vedi commento sopra).
        icon_name_row = QHBoxLayout()
        icon_name_row.setSpacing(4)

        self.icon_label = QLabel("📁")
        icon_name_row.addWidget(self.icon_label)

        self.label = QLabel(target.name)
        self.label.setStyleSheet("color: #fff; font-weight: 600;")
        self.label.setToolTip(f"{target.name}\nClic: apri in Esplora risorse")
        self.label.setCursor(Qt.PointingHandCursor)
        self._full_name = target.name
        self.label.mousePressEvent = self._on_name_clicked
        icon_name_row.addWidget(self.label, stretch=1)

        layout.addLayout(icon_name_row, stretch=1)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #ddd;")
        self.count_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.count_label)

        self.close_btn = QPushButton("✕")
        self.close_btn.clicked.connect(lambda: self.remove_requested.emit(self.target.path))
        layout.addWidget(self.close_btn)

        self.apply_style(row_height)
        self._apply_background(color)
        self.refresh_count()

    # --------------------------------------------------------- stile
    def _apply_background(self, color: str) -> None:
        # scheda con angoli arrotondati morbidi, SENZA bordo colorato
        # tutto intorno: il colore che distingue le cartelle resta solo
        # sulla barra di accento a sinistra e sul colore del numero.
        # Gli stati speciali (evidenziata / trascinabile / in
        # trascinamento) restano segnalati con un bordo, cosi' sono
        # comunque ben distinguibili.
        border = "1px solid transparent"
        if self._highlighted:
            border = "2px solid #ffd23f"
        if self._edit_mode:
            border = "2px dashed #666"  # tratteggio = "trascinabile"
        if self._is_dragging:
            border = "2px solid #6fd3ff"

        self.setStyleSheet(
            f"FolderRow {{ background-color: {ROW_BACKGROUND}; border-radius: {ROW_RADIUS}px; border: {border}; }}"
            f"FolderRow:hover {{ background-color: {ROW_BACKGROUND_HOVER}; border: {border}; }}"
        )
        self.accent_bar.setStyleSheet(
            f"background-color: {self._accent};"
            f"border-top-left-radius: {ROW_RADIUS}px; border-bottom-left-radius: {ROW_RADIUS}px;"
        )
        self.close_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; background: transparent; font-weight: bold; border-radius: 12px; }"
            "QPushButton:hover { color: #fff; background-color: #c0392b; }"
        )
        if self.move_here_btn is not None:
            font_size = getattr(self, "_move_btn_font_size", 14)
            self.move_here_btn.setStyleSheet(
                f"QPushButton {{ color: #fff; border: 1px solid transparent; background-color: {self._accent};"
                f" font-weight: bold; border-radius: 6px; font-size: {font_size}px; }}"
                f"QPushButton:hover {{ border: 1px solid #fff; }}"
            )

    def set_highlighted(self, highlighted: bool) -> None:
        self._highlighted = highlighted
        self._apply_background(self._color)

    def refresh_count(self) -> None:
        n = count_files_in(self.target.path)
        self.count_label.setText(f"{n}\nfile")

    def apply_style(self, row_height: int) -> None:
        s = _sizes_for(row_height)
        self.setFixedHeight(s["row_height"])
        if self.number_badge is not None:
            # Solo testo colorato, senza alcun riquadro/anello/pillola
            # attorno: quelli davano l'effetto "barra verticale" tra il
            # numero e il resto della riga (i bordi dritti ai lati di
            # una forma piu' alta che larga), che doveva sparire del
            # tutto. Il numero resta comunque ben distinguibile perche'
            # e' in grassetto e colorato con l'accento della cartella.
            self.number_badge.setFixedSize(s["badge_w"], min(s["badge_w"], s["row_height"] - 8))
            self.number_badge.setStyleSheet(
                f"background: transparent; border: none;"
                f"color: {self._accent}; font-weight: bold; font-size: {min(s['badge_font'], int((s['row_height'] - 8) * 0.55))}px;"
            )
        if self.number_edit is not None:
            self.number_edit.setFixedWidth(s["badge_w"])
            self.number_edit.setStyleSheet(
                f"background-color: rgba(0,0,0,140); border-radius: 4px;"
                f"color: #fff; font-weight: bold; font-size: {min(s['badge_font'], 28)}px;"
                f"border: 1px solid #888; padding: 2px;"
            )
        if self.move_here_btn is not None:
            btn_size = min(s["close_size"] + 4, max(20, s["row_height"] - 10))
            self.move_here_btn.setFixedSize(btn_size, btn_size)
            # il font-size va nello stesso stylesheet di _apply_background
            # (che lo sovrascriverebbe altrimenti): qui salviamo solo la
            # misura, cosi' _apply_background la trova gia' pronta sia
            # che venga chiamata prima (__init__) sia mai piu' (resize
            # dello slider dimensione, che richiama solo apply_style).
            self._move_btn_font_size = max(12, int(btn_size * 0.55))
            self._apply_background(self._color)
        self.icon_label.setStyleSheet(f"font-size: {s['icon_font']}px;")
        self.label.setStyleSheet(f"color: #fff; font-weight: 600; font-size: {s['name_font']}px;")
        self.count_label.setStyleSheet(f"color: #ddd; font-size: {s['count_font']}px;")
        self.count_label.setVisible(s["show_count"])
        self.close_btn.setFixedSize(s["close_size"], s["close_size"])
        self._elide_name()

    def _elide_name(self) -> None:
        """Accorcia il nome con i puntini se non entra nella riga,
        cosi' il testo non trabocca mai fuori dal riquadro."""
        fm = QFontMetrics(self.label.font())
        available = max(self.label.width(), 10)
        elided = fm.elidedText(self._full_name, Qt.ElideRight, available)
        self.label.setText(elided)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide_name()

    # ----------------------------------------------------- interazioni
    def _commit_number_field(self) -> None:
        text = self.number_edit.text().strip()
        try:
            value = int(text)
        except ValueError:
            return
        self.number_changed.emit(self.target.path, value)

    def _on_name_clicked(self, event) -> None:
        if self._edit_mode:
            # in modifica il nome non apre la cartella: cosi' si puo'
            # iniziare a trascinare la riga anche partendo dal nome
            event.ignore()
            return
        if event.button() == Qt.LeftButton:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.target.path))
            event.accept()

    def mousePressEvent(self, event) -> None:
        if self._edit_mode:
            if event.button() == Qt.LeftButton and not self.number_edit.underMouse() \
                    and not self.close_btn.underMouse():
                self._press_pos = event.position().toPoint()
            super().mousePressEvent(event)
            return

        if event.button() == Qt.LeftButton and not self.number_badge.underMouse():
            self.clicked.emit(self.target.path)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._edit_mode and self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            if not self._is_dragging:
                moved = (event.position().toPoint() - self._press_pos).manhattanLength()
                if moved < self.DRAG_THRESHOLD:
                    return
                self._is_dragging = True
                self._apply_background(self._color)
                self.raise_()
            # nuova posizione Y, nel sistema di coordinate del genitore (grid_host)
            new_top_left = self.mapToParent(event.position().toPoint() - self._press_pos)
            self.move(self.x(), new_top_left.y())
            self.drag_moved.emit(self)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._edit_mode and self._is_dragging:
            self._is_dragging = False
            self._press_pos = None
            self._apply_background(self._color)
            self.drag_finished.emit(self)
            return
        self._press_pos = None
        super().mouseReleaseEvent(event)

class FolderPanel(QWidget):
    """Contenitore scrollabile per tutte le FolderRow: riempie prima
    la colonna 1, poi la 2, poi scorre (modalita' normale). In
    modalita' modifica usa una sola colonna con riordino animato.
    Accetta anche cartelle trascinate da Esplora risorse di Windows
    per aggiungerle come destinazione."""

    folder_activated = Signal(str)      # path scelto (click o scorciatoia)
    folders_changed = Signal(list)      # list[FolderTarget] dopo riordino/rimozione/aggiunta
    delete_requested = Signal()         # cestino cliccato
    size_level_changed = Signal(int)    # livello slider 1-10

    ANIM_MS = 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row_height = 40
        self.row_spacing = 6
        self._targets: list[FolderTarget] = []
        self._rows: dict[str, FolderRow] = {}
        self._last_highlighted: str | None = None
        self._edit_mode = False
        self._drag_order: list[str] = []  # ordine dei path durante un trascinamento
        self._anims: list[QPropertyAnimation] = []
        self._last_rows_per_col: int | None = None  # per evitare rebuild inutili, vedi resizeEvent
        self.setAcceptDrops(True)  # per importare cartelle trascinate da Esplora risorse

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        # tutto su un'unica riga: dimensione, "SPOSTA IN:" al centro, modifica, cestino
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(1, 10)
        self.size_slider.setValue(DEFAULT_SIZE_LEVEL)
        self.size_slider.setToolTip("Dimensione cartelle")
        self.size_slider.setFixedWidth(70)
        self.size_slider.valueChanged.connect(self._on_slider_changed)
        top_row.addWidget(self.size_slider)

        top_row.addStretch(1)
        header = QLabel("SPOSTA IN:")
        header.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px;")
        top_row.addWidget(header)
        top_row.addStretch(1)

        self.edit_btn = QPushButton("✏")
        self.edit_btn.setToolTip("Modifica numerazione e ordine (trascina le righe per riordinare)")
        self.edit_btn.setFixedSize(28, 28)
        self.edit_btn.setCheckable(True)
        self.edit_btn.clicked.connect(self._toggle_edit_mode)
        top_row.addWidget(self.edit_btn)

        self.trash_btn = QPushButton("🗑")
        self.trash_btn.setToolTip("Elimina file corrente (tasto 0)")
        self.trash_btn.setFixedSize(28, 28)
        self._trash_highlighted = False
        top_row.addWidget(self.trash_btn)

        # RICHIESTA (v0.32): il pulsante Impostazioni si e' spostato di
        # nuovo, stavolta nella riga del logo in alto a sinistra ("le
        # impostazioni mettile sulla stessa riga lato destro del
        # logo") — vedi BrandedHeader/main_window.py. Prima stava qui,
        # vicino a modifica/cestino (v0.30).

        outer.addLayout(top_row)

        self._apply_edit_btn_style()
        self._apply_trash_style()
        self.trash_btn.clicked.connect(self.delete_requested.emit)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignTop)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(self.row_spacing)
        self.scroll.setWidget(self.grid_host)

        outer.addWidget(self.scroll, stretch=1)

    # ------------------------------------------------------- gestione
    def set_folders(self, targets: list[FolderTarget]) -> None:
        self._targets = sorted(targets, key=lambda t: t.number)
        self._rebuild()

    def add_folder(self, target: FolderTarget) -> None:
        self._targets.append(target)
        self._targets.sort(key=lambda t: t.number)
        self._rebuild()
        self.folders_changed.emit(self._targets)

    def get_folders(self) -> list[FolderTarget]:
        return list(self._targets)

    def folder_for_shortcut(self, key: str) -> FolderTarget | None:
        # il tasto rapido segue sempre il numero ATTUALE della cartella
        # (che puo' cambiare riordinando), non un valore fissato alla
        # creazione
        for t in self._targets:
            if str(t.number) == key:
                return t
        return None

    def get_row_widget(self, path: str) -> FolderRow | None:
        return self._rows.get(path)

    def set_style(self, text_size: int, row_height: int, row_spacing: int) -> None:
        # text_size mantenuto per compatibilita' con SettingsDialog,
        # ma la dimensione del testo e' ora derivata da row_height
        # per restare sempre proporzionata (vedi _sizes_for).
        self.row_height = row_height
        self.row_spacing = row_spacing
        self.grid.setVerticalSpacing(row_spacing)
        for row in self._rows.values():
            row.apply_style(row_height)
        self._rebuild()  # la capacita' della colonna 1 dipende dall'altezza riga

    def _on_slider_changed(self, level: int) -> None:
        # livello 1 (poche cartelle, enormi) -> 10 (molte cartelle, piccole).
        # Il massimo (128px) e' scelto vicino al punto in cui il font
        # raggiunge il proprio tetto (_sizes_for), cosi' non c'e' una
        # zona in cui la riga cresce ma il testo resta fermo.
        row_height = 28 + level * 10     # 38 .. 128
        row_spacing = 2 + level // 2     # 2 .. 7
        self.set_style(10 + level, row_height, row_spacing)
        self.size_level_changed.emit(level)

    def set_size_level(self, level: int) -> None:
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(level)
        self.size_slider.blockSignals(False)
        self._on_slider_changed(level)

    def get_size_level(self) -> int:
        return self.size_slider.value()

    def refresh_counts(self) -> None:
        """Da richiamare dopo ogni spostamento/eliminazione file per
        aggiornare il conteggio mostrato su ogni cartella."""
        for row in self._rows.values():
            row.refresh_count()

    def highlight_last_used(self, path: str | None) -> None:
        """Evidenzia la cartella verso cui e' stato spostato l'ultimo
        file (bordo giallo). Passa None per rimuovere ogni
        evidenziazione (es. dopo un undo). Evidenziare una cartella
        spegne l'evidenziazione del cestino, e viceversa."""
        self._last_highlighted = path
        for p, row in self._rows.items():
            row.set_highlighted(p == path)
        if path is not None and self._trash_highlighted:
            self._trash_highlighted = False
            self._apply_trash_style()

    def _apply_trash_style(self) -> None:
        if self._trash_highlighted:
            self.trash_btn.setStyleSheet(
                "QPushButton { background-color: #6d3d3d; border-radius: 14px; color: #fff;"
                " font-size: 14px; border: 2px solid #ffd23f; }"
                "QPushButton:hover { background-color: #7d4d4d; }"
            )
        else:
            self.trash_btn.setStyleSheet(
                "QPushButton { background-color: #4d2d2d; border-radius: 14px; color: #fff;"
                " font-size: 14px; border: 2px solid transparent; }"
                "QPushButton:hover { background-color: #6d3d3d; }"
            )

    def _apply_edit_btn_style(self) -> None:
        if self._edit_mode:
            self.edit_btn.setStyleSheet(
                "QPushButton { background-color: #2d6d4d; border-radius: 14px; color: #fff;"
                " font-size: 13px; border: 2px solid #ffd23f; }"
                "QPushButton:hover { background-color: #3d7d5d; }"
            )
        else:
            self.edit_btn.setStyleSheet(
                "QPushButton { background-color: #333; border-radius: 14px; color: #fff;"
                " font-size: 13px; border: 2px solid transparent; }"
                "QPushButton:hover { background-color: #444; }"
            )

    def _toggle_edit_mode(self) -> None:
        self._edit_mode = self.edit_btn.isChecked()
        self._apply_edit_btn_style()
        self._rebuild()

    def set_trash_highlighted(self, active: bool) -> None:
        """Evidenzia il cestino (bordo giallo) quando e' l'ultima
        azione compiuta, cosi' come per le cartelle. Attivarlo spegne
        l'evidenziazione delle cartelle."""
        self._trash_highlighted = active
        self._apply_trash_style()
        if active and self._last_highlighted is not None:
            self._last_highlighted = None
            for row in self._rows.values():
                row.set_highlighted(False)

    # --------------------------------------------------------- interni
    def _rows_per_column(self) -> int:
        """Quante righe stanno nell'altezza visibile prima di dover
        passare alla seconda colonna (solo modalita' normale)."""
        viewport_h = self.scroll.viewport().height()
        if viewport_h <= 0:
            viewport_h = self.height() or 500
        unit = self.row_height + self.row_spacing
        return max(1, viewport_h // max(unit, 1))

    def _clear_rows(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
        for row in list(self._rows.values()):
            if row.parent() is not None:
                row.hide()
                row.setParent(None)
            row.deleteLater()
        self._rows.clear()

    def _rebuild(self) -> None:
        # nasconde/schedula la cancellazione vera e propria dei widget
        # precedenti (non solo scollegarli): un widget scollegato ma
        # non distrutto puo' ridiventare visibile come finestra a se'
        # stante se qualcosa lo richiama in causa (es. un evento in coda)
        self._clear_rows()
        self._targets.sort(key=lambda t: t.number)

        if self._edit_mode:
            self._rebuild_edit_mode()
        else:
            self._rebuild_normal_mode()

    def _rebuild_normal_mode(self) -> None:
        rows_per_col = self._rows_per_column()
        self._last_rows_per_col = rows_per_col
        # la colonna 2 riceve spazio solo se effettivamente usata,
        # altrimenti con poche cartelle meta' pannello resterebbe
        # vuoto e il testo verrebbe compresso inutilmente
        col2_used = len(self._targets) > rows_per_col
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if col2_used else 0)

        for i, target in enumerate(self._targets):
            color = ROW_COLORS[i % len(ROW_COLORS)]
            accent = ROW_ACCENTS[i % len(ROW_ACCENTS)]
            row = FolderRow(target, self.row_height, color, False, accent=accent)
            row.clicked.connect(self.folder_activated.emit)
            row.number_changed.connect(self._on_number_changed)
            row.remove_requested.connect(self._on_remove)
            self._rows[target.path] = row
            if i < rows_per_col:
                col, r = 0, i
            else:
                col, r = 1, i - rows_per_col
            self.grid.addWidget(row, r, col)

        if self._last_highlighted:
            for p, row in self._rows.items():
                row.set_highlighted(p == self._last_highlighted)

    def _rebuild_edit_mode(self) -> None:
        # in modifica: una sola colonna, posizionamento manuale (non
        # dal QGridLayout) cosi' si possono animare le righe durante
        # il trascinamento
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 0)
        unit = self.row_height + self.row_spacing
        width = self.grid_host.width() or self.scroll.viewport().width() or 300

        self._drag_order = [t.path for t in self._targets]
        for i, target in enumerate(self._targets):
            color = ROW_COLORS[i % len(ROW_COLORS)]
            accent = ROW_ACCENTS[i % len(ROW_ACCENTS)]
            row = FolderRow(target, self.row_height, color, True, accent=accent)
            row.number_changed.connect(self._on_number_changed)
            row.remove_requested.connect(self._on_remove)
            row.drag_moved.connect(self._on_row_dragged)
            row.drag_finished.connect(self._on_row_drag_finished)
            row.setParent(self.grid_host)
            row.setGeometry(0, i * unit, width, self.row_height)
            row.show()
            self._rows[target.path] = row

        self.grid_host.setMinimumHeight(len(self._targets) * unit)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # BUG RISOLTO (log del terminale di un utente: raffica di
        # "QWindowsWindow::setGeometry: Unable to set geometry" con la
        # larghezza minima della finestra che cresceva ad ogni tentativo
        # — 1483, 1507, 1887, 1997, 2000, 2064... — mentre l'altezza
        # restava sempre la stessa, il che punta dritto qui): prima si
        # ricostruiva TUTTA la lista di cartelle (distruggendo e
        # ricreando ogni singola riga) ad OGNI ridimensionamento, anche
        # per un pixel, anche in larghezza (che pero' non cambia mai
        # quante righe stanno per colonna: quello dipende solo
        # dall'altezza, vedi _rows_per_column). Su un bug noto di
        # Qt/Windows col DPI, dove un singolo ridimensionamento puo'
        # gia' scatenare un breve andirivieni nella negoziazione della
        # geometria nativa, ricostruire tutti i widget del pannello ad
        # ogni tentativo di quell'andirivieni poteva far crescere un
        # po' la dimensione minima richiesta ad ogni giro (nuovi widget
        # measurati leggermente diversi dai precedenti), alimentando un
        # ciclo che si autoalimentava invece di stabilizzarsi subito.
        # Ora si ricostruisce solo se il numero di righe per colonna
        # e' DAVVERO cambiato (l'unica cosa che conta per il layout);
        # altrimenti e' il QGridLayout stesso a occuparsi di riadattare
        # le righe gia' esistenti, senza ricrearle.
        if not self._edit_mode:
            rows_per_col = self._rows_per_column()
            if rows_per_col != self._last_rows_per_col:
                self._rebuild()
        else:
            self._reposition_edit_rows(animate=False)

    def _reposition_edit_rows(self, animate: bool = True) -> None:
        unit = self.row_height + self.row_spacing
        width = self.grid_host.width() or self.scroll.viewport().width() or 300
        for i, path in enumerate(self._drag_order):
            row = self._rows.get(path)
            if row is None or row._is_dragging:
                continue
            target_rect = QRect(0, i * unit, width, self.row_height)
            if animate and row.geometry() != target_rect:
                self._animate_row(row, target_rect)
            else:
                row.setGeometry(target_rect)

    def _animate_row(self, row: FolderRow, target_rect: QRect) -> None:
        anim = QPropertyAnimation(row, b"geometry", self)
        anim.setDuration(self.ANIM_MS)
        anim.setStartValue(row.geometry())
        anim.setEndValue(target_rect)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anims.append(anim)
        anim.finished.connect(lambda a=anim: self._anims.remove(a) if a in self._anims else None)

    def _on_row_dragged(self, dragged_row: FolderRow) -> None:
        """Mentre una riga viene trascinata verticalmente, le altre
        scorrono in alto/basso (animate) per fare spazio, come in una
        lista riordinabile."""
        unit = self.row_height + self.row_spacing
        dragged_path = dragged_row.target.path
        old_index = self._drag_order.index(dragged_path)
        center_y = dragged_row.y() + dragged_row.height() / 2
        new_index = int(center_y // unit)
        new_index = max(0, min(new_index, len(self._drag_order) - 1))
        if new_index != old_index:
            self._drag_order.pop(old_index)
            self._drag_order.insert(new_index, dragged_path)
            self._reposition_edit_rows(animate=True)

    def _on_row_drag_finished(self, dragged_row: FolderRow) -> None:
        unit = self.row_height + self.row_spacing
        width = self.grid_host.width() or self.scroll.viewport().width() or 300
        final_index = self._drag_order.index(dragged_row.target.path)
        self._animate_row(dragged_row, QRect(0, final_index * unit, width, self.row_height))
        QTimer.singleShot(self.ANIM_MS + 20, lambda: self._commit_drag_order())

    def _commit_drag_order(self) -> None:
        by_path = {t.path: t for t in self._targets}
        ordered = [by_path[p] for p in self._drag_order if p in by_path]
        for i, t in enumerate(ordered, start=1):
            t.number = i
        self._targets = ordered
        self._rebuild()
        self.folders_changed.emit(self._targets)

    def _on_number_changed(self, path: str, requested_number: int) -> None:
        """La cartella modificata (digitando il numero) va alla
        posizione richiesta e tutte le altre scalano di conseguenza
        (inserimento, non sovrascrittura): es. la cartella 10 messa a
        1 diventa la prima, la vecchia 1 diventa 2, ..., la vecchia 9
        diventa 10."""
        ordered = sorted(self._targets, key=lambda t: t.number)
        moving = next((t for t in ordered if t.path == path), None)
        if moving is None:
            return
        ordered.remove(moving)
        insert_at = max(0, min(requested_number - 1, len(ordered)))
        ordered.insert(insert_at, moving)
        for i, t in enumerate(ordered, start=1):
            t.number = i
        self._targets = ordered
        self._rebuild()
        self.folders_changed.emit(self._targets)

    def _on_remove(self, path: str) -> None:
        self._targets = [t for t in self._targets if t.path != path]
        self._rebuild()
        self.folders_changed.emit(self._targets)

    # ------------------------------------------- import da Esplora risorse
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).is_dir():
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event) -> None:
        added = False
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if not local_path or not Path(local_path).is_dir():
                continue
            if any(t.path == local_path for t in self._targets):
                continue  # gia' presente
            next_number = max([t.number for t in self._targets], default=0) + 1
            self._targets.append(FolderTarget(
                number=next_number, name=Path(local_path).name, path=local_path, shortcut="",
            ))
            added = True
        if added:
            self._targets.sort(key=lambda t: t.number)
            self._rebuild()
            self.folders_changed.emit(self._targets)
