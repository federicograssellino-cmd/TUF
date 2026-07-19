"""
ui/duplicate_review_dialog.py
Pannello per revisionare TUTTI i gruppi di duplicati insieme.

NON e' piu' una finestra separata (QDialog): e' un QWidget che prende
il POSTO dell'anteprima foto/video nella finestra principale mentre e'
attivo (vedi ui/main_window.py, dove viene inserito in uno
QStackedWidget insieme a PreviewWidget), cosi' tutto resta nello
stesso riquadro invece di aprire una finestra sopra. Quando si conferma
o si annulla (anche con la "X" in alto a destra), il pannello emette
un segnale (confirmed/cancelled) e la finestra principale torna a
mostrare l'anteprima normale.

Ogni gruppo di file "uguali" (stessa dimensione e stesso contenuto,
individuati da core/duplicates.py) e' mostrato su UNA SOLA RIGA: una
scheda per ciascun file con anteprima, nome, dimensione, data di
creazione, data di ultima modifica e (per i video) la durata. In alto
a sinistra di ogni scheda c'e' un piccolo pulsante cartella per aprire
Esplora risorse direttamente su quel file.

Sotto ogni file una checkbox "Cancella" (non piu' "Tieni"): di default
la PRIMA copia di ogni gruppo resta deselezionata (non verra'
eliminata), tutte le copie successive (seconda, terza, ...) sono GIA'
selezionate per l'eliminazione, dato che nella grande maggioranza dei
casi e' proprio quello che si vuole. Restano comunque modificabili file
per file, anche sulla prima copia. A destra di ogni riquadro, centrati
in verticale, ci sono due scorciatoie per l'intero gruppo: "non
cancellare nessuno" e "cancella copie (tieni solo la prima)".

In alto: un controllo per ordinare i gruppi (di default Dimensione
Decrescente, cosi' si revisionano prima i duplicati che liberano piu'
spazio) e uno zoom +/- per vedere le miniature piu' grandi o piu'
piccole. Se ALMENO un gruppo ha 2 o piu' copie (quindi sempre, dato che
un gruppo di duplicati ha per definizione almeno 2 file), compare
anche una barra "per posizione": un pulsante per colonna (2, 3, 4...)
che alterna, con un'unica icona (gomma se cliccandolo elimini quella
posizione su tutti i gruppi, spunta se la tieni — un po' come il
pulsante del microfono), invece delle vecchie coppie di pulsanti
testuali "Cancella/Non cancellare colonna N". La colonna 2 e' inclusa
(BUG RISOLTO: prima si partiva dalla colonna 3, assumendo bastasse la
scorciatoia per-gruppo "Cancella copie" a destra di ogni riquadro — ma
quella agisce solo su UN gruppo alla volta, non su tutti insieme).

Le MINIATURE vengono decodificate in un thread separato (vedi
_ThumbBatchWorker piu' sotto), non piu' in modo sincrono sul thread
dell'interfaccia: con lotti fino a 100 file, decodificarle tutte
subito poteva bloccare l'interfaccia per parecchi secondi, ed era
particolarmente evidente cambiando l'ordinamento (che riparte sempre
da miniature non ancora in cache). Ora ogni scheda mostra subito un
segnaposto e la miniatura vera compare non appena pronta, senza mai
bloccare nulla.

LAYOUT (v0.20): niente piu' margini di default attorno al pannello
(che lo facevano sembrare "rimpicciolito e spostato" rispetto
all'anteprima normale quando si passava dall'uno all'altro): ora usa
zero margini, esattamente come PreviewWidget, cosi' lo spazio
disponibile e' identico in entrambi i casi. Il testo lungo di
spiegazione e' diventato un'icona "ℹ" con tooltip (prima occupava due
righe fisse), e "Cancella tutte le copie" e' stato spostato sulla
STESSA riga di "Annulla"/"Elimina i selezionati" (prima era su una
riga a parte sopra): insieme liberano spazio verticale per la lista.

LIMITE NOTO (voluto, vedi anche _load_more piu' sotto): i gruppi
vengono mostrati a lotti di BATCH_SIZE alla volta. Passando al lotto
successivo, quello precedente non resta piu' a schermo in questo
pannello (per non accumulare centinaia di miniature in memoria). Le
scelte gia' fatte sui gruppi del lotto precedente restano comunque
valide (sono salvate in _keep_state, non nei widget a schermo) e
verranno applicate quando si conferma l'eliminazione, ma per
RIVEDERLI di nuovo a schermo serve chiudere questo pannello e far
ripartire il controllo duplicati da capo (si riscansiona la cartella).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QSize, QThread, Signal, QRect, QPoint
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QScrollArea, QFrame, QComboBox, QSlider, QGraphicsOpacityEffect, QLayout,
)

from filepilot.core.duplicates import DuplicateGroup
from filepilot.models import FileCategory, FileItem
from filepilot.ui.preview_widget import decode_thumb_and_duration

# Le miniature vengono DECODIFICATE (e messe in cache) a questa
# risoluzione, piu' alta della dimensione minima di visualizzazione:
# cosi' lo zoom puo' anche ingrandirle un po' senza sgranare troppo,
# senza dover ridecodificare il file da disco ogni volta che cambia lo
# zoom (che sarebbe lento). Lo zoom scala solo a video la pixmap gia'
# in cache.
DECODE_THUMB_SIZE = QSize(240, 240)
ZOOM_MIN = 70
ZOOM_MAX = 240
ZOOM_DEFAULT = 130
ZOOM_STEP = 20

# Quanti gruppi vengono costruiti/mostrati alla volta. Costruire TUTTI
# i gruppi in un colpo solo (anteprime comprese) poteva essere molto
# pesante con librerie grandi (centinaia di gruppi = centinaia di
# miniature da decodificare tutte insieme all'apertura). Ora si parte
# con un primo lotto, e se ne caricano altri a richiesta (vedi
# _load_more).
BATCH_SIZE = 100

# Criteri di ordinamento disponibili nella tendina "Ordina per". Ogni
# gruppo di duplicati condivide sempre la stessa dimensione (e' cosi'
# che vengono individuati), quindi per dimensione basta il primo file;
# per nome e date si usa il valore piu' "piccolo" del gruppo (il file
# piu' vecchio / il nome che viene prima in ordine alfabetico), cosi'
# l'ordinamento resta stabile anche se il gruppo ha piu' di due file.
SORT_FIELDS = {
    "Nome": lambda g: min(Path(it.path).name.lower() for it in g.items),
    "Dimensione": lambda g: g.items[0].size,
    "Data di creazione": lambda g: min(it.ctime for it in g.items),
    "Data ultima modifica": lambda g: min(it.mtime for it in g.items),
}


def _format_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _format_date(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(round(seconds))
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def reveal_in_explorer(path: str) -> None:
    """Apre Esplora risorse con il file gia' selezionato/evidenziato
    (non solo la cartella che lo contiene). Su Windows usa il comando
    nativo 'explorer /select,'; se non e' disponibile (o su un altro
    sistema operativo) ripiega sull'apertura semplice della cartella
    che lo contiene.

    BUG RISOLTO (SEGNALATO: "mi apre solo la cartella... mi deve
    arrivare direttamente al file"): qui /select e il percorso
    venivano passati come UN SOLO argomento concatenato
    (f"/select,{path}") — su Windows Esplora risorse a volte non
    riconosce questa forma (specialmente con percorsi che contengono
    spazi) e ripiega silenziosamente sulla sola apertura della
    cartella, senza selezionare nulla. La stessa identica funzione in
    main_window.py (_open_source_in_explorer) passa invece "/select,"
    e il percorso come DUE argomenti separati nella lista di
    subprocess.Popen, forma gia' verificata funzionante — questa
    funzione ora usa lo stesso identico schema, per coerenza."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(Path(path))])
            return
    except OSError:
        pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))


class _ThumbBatchWorker(QThread):
    """Decodifica le miniature di un lotto di file in un thread
    separato, UNA alla volta, emettendo un segnale ogni volta che una
    e' pronta (invece di aspettare tutto il lotto): cosi' le miniature
    compaiono progressivamente senza mai bloccare l'interfaccia, anche
    per lotti da 100 file. decode_thumb_and_duration ritorna un
    QImage (non una QPixmap, che non e' sicura da creare fuori dal
    thread dell'interfaccia): la conversione a QPixmap avviene nel
    thread principale quando arriva il segnale (vedi _on_thumb_ready)."""

    item_ready = Signal(str, object, object)  # path, QImage|None, durata|None

    def __init__(self, items: list[FileItem], size: QSize, parent=None):
        super().__init__(parent)
        self._items = items
        self._size = size
        self._abort = False

    def stop(self) -> None:
        self._abort = True

    def run(self) -> None:
        for item in self._items:
            if self._abort:
                return
            img, duration = decode_thumb_and_duration(item, self._size)
            if self._abort:
                return
            self.item_ready.emit(item.path, img, duration)


class _FlowLayout(QLayout):
    """Layout che dispone i widget in riga e va a capo da solo quando
    non c'e' piu' spazio orizzontale, invece di far scorrere una
    striscia in orizzontale — RICHIESTA: "seleziona/deseleziona rimane
    al primo rigo invece colonna1,2,3 va a capo". Usato per la riga dei
    pulsanti 'per posizione' (Colonna N), che con etichette di testo
    complete (es. 'DESELEZIONA COLONNA 4' invece della vecchia icona)
    non ci stanno tutti su una riga sola quando ci sono molte copie
    per gruppo. Ricetta standard di Qt (Flow Layout Example),
    riadattata qui in forma compatta."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list = []

    def __del__(self):
        # Pulizia esplicita degli item (non dei widget, che restano di
        # proprieta' del genitore) alla distruzione del layout — stessa
        # accortezza della ricetta ufficiale Qt "Flow Layout Example"
        # (li' fatta nel distruttore C++). Difesa in piu' contro
        # eventuali riferimenti C++ non ripuliti correttamente da soli.
        try:
            while self._items:
                self._items.pop()
        except Exception:
            pass

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + m.bottom()


class DuplicateReviewPanel(QWidget):
    """Mostra tutti i gruppi di duplicati insieme, con checkbox
    "Cancella" per scegliere cosa eliminare. Emette confirmed(list di
    path) se si conferma, cancelled() se si annulla — non e' piu' un
    QDialog, vedi il commento in testa al file sul perche'."""

    confirmed = Signal(list)
    cancelled = Signal()

    def __init__(self, groups: list[DuplicateGroup], parent=None):
        super().__init__(parent)
        self._groups = groups
        self._all_items: list[FileItem] = [it for g in groups for it in g.items]
        self._item_by_path: dict[str, FileItem] = {it.path: it for it in self._all_items}

        # Stato di default: prima copia di ogni gruppo tenuta, tutte
        # le copie successive gia' selezionate per l'eliminazione.
        self._keep_state: dict[str, bool] = {}
        for group in groups:
            for i, item in enumerate(group.items):
                self._keep_state[item.path] = (i == 0)

        # NO LOG: queste due cache vivono SOLO qui, in memoria di
        # processo (normali dizionari Python) — non vengono MAI scritte
        # su disco, in nessuna cache/database. Spariscono da sole
        # quando questo pannello si chiude (garbage collection), non
        # sopravvivono al riavvio del programma. Vedi anche il
        # commento in cima a config.py sull'unico elenco di cose che
        # TUF salva davvero.
        self._duration_cache: dict[str, float | None] = {}
        self._thumb_cache: dict[str, QPixmap | None] = {}
        self._sorted_cache: list[DuplicateGroup] = []  # ordine corrente, ricalcolato ad ogni _rebuild
        self._visible_count = 0  # quanti gruppi (in _sorted_cache) sono gia' costruiti a schermo
        self._zoom_size = ZOOM_DEFAULT
        self._column_buttons: dict[int, QPushButton] = {}

        # Caricamento asincrono delle miniature: _thumb_gen e' un
        # contatore che cambia ad ogni ricostruzione del lotto visibile
        # (rebuild/load_more/zoom); i risultati di un worker "vecchio"
        # (di un lotto ormai sostituito) vengono scartati confrontando
        # la generazione con cui sono partiti, cosi' non si rischia di
        # aggiornare un QLabel che nel frattempo e' stato distrutto.
        self._thumb_gen = 0
        self._thumb_worker: _ThumbBatchWorker | None = None
        self._thumb_labels: dict[str, QLabel] = {}
        self._info_labels: dict[str, QLabel] = {}
        self._row_scrolls: list[QScrollArea] = []
        # SEGNALATO: "se schiaccio cancella copie selezionate mi
        # rimangono li', e non e' chiaro se sono cancellati o meno" —
        # i pulsanti per riga/colonna e le checkbox segnano SOLO le
        # copie per l'eliminazione (l'eliminazione vera avviene solo
        # dopo aver premuto "Elimina i selezionati" in fondo, con
        # conferma — e' voluto, cosi' resta sempre possibile
        # ripensarci prima di cancellare per davvero). Il problema era
        # che la scheda non mostrava NESSUN segno visivo di essere
        # stata marcata, quindi sembrava che il click non avesse fatto
        # niente. self._card_widgets tiene la scheda intera per path,
        # cosi' _apply_card_marked_style puo' cambiarne aspetto
        # (etichetta rossa "Sara' eliminato" + bordo + opacita'
        # ridotta) ogni volta che il suo stato cambia, da qualunque
        # pulsante/checkbox arrivi il cambiamento.
        self._card_widgets: dict[str, QWidget] = {}
        self._mark_labels: dict[str, QLabel] = {}

        # zero margini: come PreviewWidget, cosi' passando da
        # anteprima a revisione duplicati (e viceversa) lo spazio
        # disponibile non cambia. BUG RISOLTO ("la pagina si riduce e
        # si sposta a destra aprendo i duplicati"): prima questo
        # layout usava i margini di default di Qt (circa 9-11px per
        # lato) mentre PreviewWidget usa zero, quindi passando da uno
        # all'altro il contenuto si "restringeva" visibilmente.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # --- intestazione, con la "X" per chiudere in alto a destra ---
        header_row = QHBoxLayout()
        total_files = len(self._all_items)
        header = QLabel(f"Trovati {len(groups)} gruppi di duplicati ({total_files} file coinvolti)")
        header.setStyleSheet("font-size: 15px; font-weight: bold;")
        header_row.addWidget(header)

        # "ℹ" con tooltip al posto del paragrafo di spiegazione fisso
        # (che occupava un paio di righe): stesso contenuto, ma solo a
        # richiesta, per lasciare piu' spazio verticale alla lista.
        info_btn = QPushButton("ℹ")
        info_btn.setFixedSize(22, 22)
        info_btn.setToolTip(
            "Ogni riga e' un gruppo di file uguali tra loro. Di default la prima copia resta, le altre sono "
            "gia' selezionate per l'eliminazione: deseleziona 'Cancella' su quelle che vuoi tenere invece.\n"
            "Clic su miniatura o nome per aprire il file, sulla cartella in alto a sinistra per trovarlo in "
            "Esplora risorse."
        )
        info_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; border: none; border-radius: 11px; font-weight: bold; }"
            "QPushButton:hover { background-color: #444; color: #fff; }"
        )
        header_row.addWidget(info_btn)
        header_row.addStretch(1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("Chiudi (come Annulla)")
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: #3a3a3a; color: #ddd; border: none;"
            " border-radius: 13px; font-weight: 600; }"
            "QPushButton:hover { background-color: #c0392b; color: #fff; }"
        )
        self.close_btn.clicked.connect(self.cancelled.emit)
        header_row.addWidget(self.close_btn)
        layout.addLayout(header_row)

        # --- barra di ordinamento + zoom ---
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Ordina per:"))
        self.sort_field_combo = QComboBox()
        self.sort_field_combo.addItems(list(SORT_FIELDS.keys()))
        self.sort_field_combo.setCurrentText("Dimensione")
        sort_row.addWidget(self.sort_field_combo)

        self.sort_dir_combo = QComboBox()
        self.sort_dir_combo.addItems(["Crescente", "Decrescente"])
        self.sort_dir_combo.setCurrentText("Decrescente")  # i piu' grandi (piu' spazio da liberare) per primi
        sort_row.addWidget(self.sort_dir_combo)
        sort_row.addStretch(1)

        # RICHIESTA ("metti una barra con cursore invece di +/-"): gli
        # step fissi con +/- richiedevano piu' clic per arrivare alla
        # dimensione voluta; uno slider permette di trascinare
        # direttamente alla dimensione desiderata, con lo stesso
        # aggiornamento "in place" (niente ricostruzione, vedi
        # _apply_zoom_size) ad ogni movimento.
        sort_row.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(ZOOM_MIN)
        self.zoom_slider.setMaximum(ZOOM_MAX)
        self.zoom_slider.setValue(ZOOM_DEFAULT)
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.setToolTip("Dimensione miniature")
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        sort_row.addWidget(self.zoom_slider)

        layout.addLayout(sort_row)

        # --- azioni per "colonna" (posizione del file dentro al gruppo):
        # utile per agire su TUTTI i gruppi insieme (es. "tieni sempre
        # la prima copia ovunque", "cancella sempre la seconda
        # ovunque"), a differenza delle scorciatoie a destra di ogni
        # riquadro gruppo (che agiscono solo su QUEL gruppo). Ogni
        # pulsante e' un unico toggle che alterna testo/azione ad ogni
        # clic, invece delle vecchie coppie "Cancella colonna N" / "Non
        # cancellare colonna N".
        # BUG RISOLTO ("manca l'opzione per deselezionare tutta la
        # colonna 2"): la colonna 2 non aveva un pulsante globale,
        # perche' si presumeva bastasse la scorciatoia per-gruppo
        # "Cancella copie" a destra di ogni riquadro. Ma quella agisce
        # SOLO sul gruppo su cui si clicca, non su tutti i gruppi
        # insieme: con molti gruppi (es. tutti con 2 sole copie), non
        # c'era comunque un modo per, ad esempio, "tieni la seconda
        # copia dappertutto" in un solo clic. RICHIESTA successiva:
        # "inserisci anche la possibilità di selezionare o deselezionare
        # tutta la prima colonna" — ora la barra "per posizione" parte
        # dalla colonna 1 (copriva solo dalla 2 in poi) e compare ogni
        # volta che c'e' almeno un gruppo con 2 o piu' copie, cioe'
        # sempre (i gruppi di duplicati hanno per definizione almeno 2
        # file).
        max_columns = max((len(g.items) for g in groups), default=0)
        if max_columns >= 2:
            # RICHIESTA: "seleziona/deseleziona rimane al primo rigo
            # invece colonna1,2,3 va a capo" — l'etichetta resta da
            # sola sulla sua riga (non piu' incollata al primo
            # pulsante), e i pulsanti "per posizione" vanno a capo da
            # soli quando non c'entrano piu' in orizzontale (vedi
            # _FlowLayout), invece di dover scorrere lateralmente in
            # una striscia stretta e fissa come prima — utile ora che
            # le etichette sono testo esteso (es. "DESELEZIONA
            # COLONNA 4") invece di una singola icona.
            columns_label = QLabel("Per posizione (in tutti i gruppi insieme):")
            columns_label.setStyleSheet("color: #ccc; font-size: 11px;")
            layout.addWidget(columns_label)

            columns_container = QWidget()
            columns_flow = _FlowLayout(columns_container, margin=0, spacing=6)
            # RICHIESTA: "inserisci anche la possibilità di selezionare
            # o deselezionare tutta la prima colonna" — prima si
            # partiva dalla colonna 2 (si presumeva bastassero le
            # scorciatoie per-gruppo "Non cancellare nessuno"/"Cancella
            # copie" per la prima copia). Ma quelle agiscono solo sul
            # singolo gruppo, non su TUTTI insieme come questi pulsanti
            # "per posizione": senza un pulsante globale per la colonna
            # 1, non c'era modo di dire in un colpo solo "tieni/segna
            # sempre la prima copia di ogni gruppo".
            for col in range(1, max_columns + 1):
                columns_flow.addWidget(self._make_column_toggle_btn(col))
            layout.addWidget(columns_container)

        self.sort_field_combo.currentIndexChanged.connect(self._rebuild)
        self.sort_dir_combo.currentIndexChanged.connect(self._rebuild)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, stretch=1)

        load_more_row = QHBoxLayout()
        self.remaining_label = QLabel("")
        self.remaining_label.setStyleSheet("color: #aaa; font-size: 11px;")
        load_more_row.addWidget(self.remaining_label, stretch=1)
        self.load_more_btn = QPushButton()
        self.load_more_btn.clicked.connect(self._load_more)
        load_more_row.addWidget(self.load_more_btn)
        layout.addLayout(load_more_row)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #ccc; padding: 4px 0; font-weight: 600;")
        layout.addWidget(self.summary_label)

        # Annulla / Cancella tutte le copie / Elimina i selezionati: ora
        # tutti sulla STESSA riga (prima "Cancella tutte le copie" era
        # su una riga a parte sopra questa), per liberare una riga
        # intera di spazio verticale per la lista sopra.
        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("Annulla")
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)

        self.delete_all_copies_btn = QPushButton("Cancella tutte le copie (tieni solo la prima di ogni gruppo)")
        self.delete_all_copies_btn.setStyleSheet(
            "QPushButton { background-color: #6d3d3d; color: #fff; border-radius: 4px; padding: 8px 14px; }"
            "QPushButton:hover { background-color: #7d4d4d; }"
        )
        self.delete_all_copies_btn.clicked.connect(self._keep_only_first_all_groups)
        btn_row.addWidget(self.delete_all_copies_btn)

        self.confirm_btn = QPushButton("Elimina i selezionati")
        self.confirm_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: #fff; padding: 8px 16px;"
            " border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #d9483a; }"
        )
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

        self.confirm_btn.clicked.connect(lambda: self.confirmed.emit(self.paths_to_delete()))
        self.cancel_btn.clicked.connect(self.cancelled.emit)

        self._rebuild()

    # --------------------------------------------------------- build
    def _sorted_groups(self) -> list[DuplicateGroup]:
        field = self.sort_field_combo.currentText()
        key_fn = SORT_FIELDS.get(field, SORT_FIELDS["Nome"])
        reverse = self.sort_dir_combo.currentText() == "Decrescente"
        return sorted(self._groups, key=key_fn, reverse=reverse)

    def _on_zoom_slider_changed(self, value: int) -> None:
        self._zoom_size = value
        self._apply_zoom_size()

    def _apply_zoom_size(self) -> None:
        # BUG RISOLTO ("lo zoom si blocca e poi va a scatti"): la vecchia
        # versione, ad OGNI clic su +/-, buttava via e ricostruiva da zero
        # l'intero albero di widget delle schede visibili (_rebuild_visible_only:
        # nuovi QFrame/QScrollArea/QLabel per ogni file di ogni gruppo mostrato),
        # tutto sul thread dell'interfaccia. Con diversi gruppi/copie a schermo
        # questo poteva richiedere piu' di un secondo, dando l'impressione che
        # il programma si blocchi e poi "recuperi a scatti" i clic accumulati
        # nel frattempo (o, con lo slider, i tanti valueChanged emessi
        # trascinando). Le miniature pero' sono GIA' tutte decodificate e in
        # cache (vedi _thumb_cache/_on_thumb_ready): zoomare non ha davvero
        # bisogno di ricreare nulla, basta ridimensionare le label gia'
        # esistenti e riscalare la pixmap gia' pronta. Niente piu' perdita
        # della posizione di scroll neanche da salvare/ripristinare, dato che
        # il widget dentro la QScrollArea non viene mai sostituito.
        size = self._zoom_size
        for path, label in list(self._thumb_labels.items()):
            try:
                label.setFixedSize(size, size)
                pix = self._thumb_cache.get(path)
                if pix is not None:
                    label.setPixmap(pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except RuntimeError:
                pass  # widget gia' distrutto (lotto cambiato nel frattempo)
        for path, info in list(self._info_labels.items()):
            try:
                info.setFixedWidth(max(size + 50, 140))
            except RuntimeError:
                pass
        for scroll in list(self._row_scrolls):
            try:
                content = scroll.widget()
                if content is not None:
                    content.adjustSize()
                    scroll.setFixedHeight(content.sizeHint().height() + 4)
            except RuntimeError:
                pass  # widget gia' distrutto (lotto cambiato nel frattempo)

    # ----------------------------------------------- miniature async
    def _start_thumb_loading(self, groups: list[DuplicateGroup]) -> None:
        """Avvia (o riavvia) il caricamento asincrono delle miniature
        per i gruppi appena costruiti a schermo. Ferma subito il
        worker precedente (se ce n'era uno ancora in corso per un
        lotto ormai sostituito) e ne parte uno nuovo solo per i file
        non ancora in cache."""
        self._thumb_gen += 1
        my_gen = self._thumb_gen
        if self._thumb_worker is not None:
            self._thumb_worker.stop()
            try:
                self._thumb_worker.item_ready.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._thumb_worker = None

        to_decode = [
            it for g in groups for it in g.items
            if it.path not in self._thumb_cache
        ]
        if not to_decode:
            return

        worker = _ThumbBatchWorker(to_decode, DECODE_THUMB_SIZE, self)
        worker.item_ready.connect(
            lambda p, img, d, gen=my_gen: self._on_thumb_ready(p, img, d, gen)
        )
        worker.finished.connect(worker.deleteLater)
        self._thumb_worker = worker
        worker.start()

    def _on_thumb_ready(self, path: str, qimage, duration, gen: int) -> None:
        if gen != self._thumb_gen:
            return  # lotto ormai sostituito, risultato scartato
        pix = QPixmap.fromImage(qimage) if qimage is not None else None
        self._thumb_cache[path] = pix
        if duration is not None:
            self._duration_cache[path] = duration
        label = self._thumb_labels.get(path)
        if label is None:
            return
        try:
            if pix is not None:
                size = self._zoom_size
                label.setPixmap(pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                label.setText("📄")
        except RuntimeError:
            pass  # il widget e' gia' stato distrutto (lotto cambiato nel frattempo)

    def _rebuild(self) -> None:
        # BUG RISOLTO: cambiare l'ordinamento (es. da Crescente a
        # Decrescente) mandava in crash la finestra. Causa: ogni volta
        # si creava un widget "content" nuovo con dentro tutte le righe
        # e lo si passava a scroll.setWidget(...), ma quello VECCHIO
        # non veniva mai eliminato esplicitamente (QScrollArea non lo
        # distrugge da solo): restava un widget "orfano" ancora vivo, e
        # prima o poi Qt andava in crash. Ora il widget precedente viene
        # tolto ed eliminato esplicitamente PRIMA di costruire quello
        # nuovo.
        #
        # Cambiare l'ordinamento riparte sempre dal primo lotto (i primi
        # BATCH_SIZE gruppi nel nuovo ordine), non da dove si era
        # arrivati nell'ordine precedente: non avrebbe senso mischiarli.
        old_content = self.scroll.takeWidget()
        if old_content is not None:
            old_content.setParent(None)
            old_content.deleteLater()

        self._sorted_cache = self._sorted_groups()
        self._visible_count = min(BATCH_SIZE, len(self._sorted_cache))

        self._thumb_labels = {}
        self._info_labels = {}
        self._row_scrolls = []
        self._card_widgets = {}
        self._mark_labels = {}
        visible_groups = self._sorted_cache[: self._visible_count]
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        for group in visible_groups:
            content_layout.addWidget(self._build_group_row(group))
        content_layout.addStretch(1)
        self.scroll.setWidget(content)
        self._update_load_more()
        self._update_summary()
        self._start_thumb_loading(visible_groups)

    def _rebuild_visible_only(self) -> None:
        """Come _rebuild, ma senza toccare l'ordinamento ne' il lotto
        corrente: usato dallo zoom, che deve solo ridisegnare le stesse
        righe gia' visibili a una dimensione diversa. Le miniature gia'
        in cache si vedono subito (viene solo riscalata la pixmap gia'
        decodificata); solo quelle non ancora arrivate vengono
        rimesse in coda per la decodifica."""
        old_content = self.scroll.takeWidget()
        if old_content is not None:
            old_content.setParent(None)
            old_content.deleteLater()

        self._thumb_labels = {}
        self._info_labels = {}
        self._row_scrolls = []
        self._card_widgets = {}
        self._mark_labels = {}
        visible_groups = self._sorted_cache[: self._visible_count]
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        for group in visible_groups:
            content_layout.addWidget(self._build_group_row(group))
        content_layout.addStretch(1)
        self.scroll.setWidget(content)
        self._start_thumb_loading(visible_groups)

    def _load_more(self) -> None:
        """Passa al lotto successivo di BATCH_SIZE gruppi, SOSTITUENDO
        quello attuale (non lo aggiunge in coda): vedi il commento in
        testa al file (LIMITE NOTO) sul perche' e sulle conseguenze.
        Le scelte gia' fatte sui gruppi del lotto che sparisce restano
        comunque salvate in _keep_state e verranno applicate
        all'eliminazione finale."""
        old_content = self.scroll.takeWidget()
        if old_content is not None:
            old_content.setParent(None)
            old_content.deleteLater()

        start = self._visible_count
        end = min(start + BATCH_SIZE, len(self._sorted_cache))

        self._thumb_labels = {}
        self._info_labels = {}
        self._row_scrolls = []
        self._card_widgets = {}
        self._mark_labels = {}
        visible_groups = self._sorted_cache[start:end]
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        for group in visible_groups:
            content_layout.addWidget(self._build_group_row(group))
        content_layout.addStretch(1)
        self.scroll.setWidget(content)

        self._visible_count = end
        self._update_load_more()
        self._start_thumb_loading(visible_groups)

    def _update_load_more(self) -> None:
        total = len(self._sorted_cache)
        shown = self._visible_count
        remaining_groups = total - shown
        if remaining_groups > 0:
            remaining_files = sum(len(g.items) for g in self._sorted_cache[shown:])
            self.remaining_label.setText(
                f"Mostrati {shown} di {total} gruppi — "
                f"{remaining_groups} gruppi ({remaining_files} copie) ancora da revisionare"
            )
            self.load_more_btn.setText(f"Carica prossimi {min(BATCH_SIZE, remaining_groups)}")
            self.load_more_btn.show()
        else:
            self.remaining_label.setText(f"Tutti i {total} gruppi sono stati mostrati")
            self.load_more_btn.hide()

    def _build_group_row(self, group: DuplicateGroup) -> QFrame:
        """Un intero gruppo di file 'uguali' su una sola riga: una
        scheda per ciascun file con anteprima, nome, dimensione, data
        di creazione, data di ultima modifica, durata (video) e
        checkbox 'Cancella'. A destra, centrate in verticale, le due
        scorciatoie per l'intero gruppo."""
        card = QFrame()
        card.setStyleSheet("background-color: #232323; border-radius: 8px;")
        outer = QHBoxLayout(card)

        # BUG RISOLTO ("con lo zoom + i pulsanti a destra spariscono"):
        # la riga di schede file era dentro lo STESSO QHBoxLayout dei
        # pulsanti "Non cancellare"/"Cancella copie". Zoomando, le
        # miniature (e quindi ogni scheda) si allargano, e con
        # abbastanza copie la riga intera puo' diventare piu' larga
        # dello spazio visibile: il layout non va a capo, quindi
        # semplicemente spinge i pulsanti fuori dalla vista a destra
        # (serviva scorrere ORIZZONTALMENTE per ritrovarli, cosa non
        # ovvia). Ora la riga di schede vive nella sua PROPRIA area di
        # scorrimento orizzontale, separata dai pulsanti: questi ultimi
        # restano un elemento a parte, sempre visibile, qualunque sia
        # lo zoom o il numero di copie nel gruppo.
        files_scroll = QScrollArea()
        files_scroll.setWidgetResizable(True)
        files_scroll.setFrameShape(QFrame.NoFrame)
        files_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        files_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        files_scroll.setStyleSheet("background: transparent;")

        files_container = QWidget()
        files_container.setStyleSheet("background: transparent;")
        files_layout = QVBoxLayout(files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        group_checks: list[QCheckBox] = []
        for item in group.items:
            row.addWidget(self._build_item_card(item, group_checks))
        row.addStretch(1)
        files_layout.addLayout(row)
        files_scroll.setWidget(files_container)
        outer.addWidget(files_scroll, stretch=1)
        # BUG RISOLTO ("le righe tagliano l'anteprima, non si vede tutta
        # l'immagine"): files_scroll ha lo scroll verticale sempre
        # disattivato (serve solo per scorrere ORIZZONTALMENTE tra le
        # copie, vedi sopra), ma senza un'altezza esplicita la sua
        # altezza veniva decisa dal layout esterno com'era al PRIMO
        # disegno della riga (con lo zoom di default). Aumentando lo
        # zoom in seguito (specialmente ora che lo slider permette di
        # saltare subito a dimensioni molto piu' grandi, vedi
        # _apply_zoom_size) le miniature diventavano piu' alte della
        # riga, ma senza scroll verticale la parte in eccesso restava
        # semplicemente tagliata fuori invece di essere visibile. Ora
        # l'altezza della riga viene impostata esplicitamente in base al
        # contenuto reale, e riaggiornata ad ogni cambio di zoom (vedi
        # _apply_zoom_size), cosi' la riga cresce sempre a sufficienza
        # per mostrare la miniatura per intero.
        files_container.adjustSize()
        files_scroll.setFixedHeight(files_container.sizeHint().height() + 4)
        self._row_scrolls.append(files_scroll)

        # scorciatoie per l'intero gruppo, a destra e centrate in
        # verticale (prima erano sotto le miniature, a tutta larghezza)
        actions_col = QVBoxLayout()
        actions_col.addStretch(1)
        keep_all_btn = QPushButton(f"Non cancellare\nnessuno dei {len(group.items)}")
        # BUG RISOLTO ("fai diventare 'non cancellare nessuno' come il
        # tasto 'cancella copie'"): prima questo pulsante non aveva
        # nessuno stile (grigio di default di Qt), diverso da tutti gli
        # altri pulsanti del pannello. Ora ha lo stesso trattamento
        # grafico (bordi arrotondati, stesso padding/peso del testo) di
        # "Cancella copie", ma in verde invece che in rosso — lo stesso
        # schema colori gia' usato per "tieni" nei pulsanti "per
        # posizione" qui sotto, cosi' verde/rosso restano coerenti in
        # tutto il pannello per indicare "tieni"/"cancella".
        keep_all_btn.setStyleSheet(
            "QPushButton { background-color: #3d6d45; color: #fff; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: #4d7d55; }"
        )
        keep_all_btn.clicked.connect(lambda: self._check_all(group_checks))
        actions_col.addWidget(keep_all_btn)

        delete_copies_btn = QPushButton("Cancella copie\n(tieni solo la prima)")
        delete_copies_btn.setStyleSheet(
            "QPushButton { background-color: #6d3d3d; color: #fff; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: #7d4d4d; }"
        )
        delete_copies_btn.clicked.connect(lambda: self._keep_only_first(group_checks))
        actions_col.addWidget(delete_copies_btn)

        # RICHIESTA: "nelle righe dei duplicati mettiamo anche un
        # altro tasto: cancella tutto (quindi dovrà selezionare anche
        # quelli non selezionati)" — a differenza di "Cancella copie"
        # (tiene sempre la prima), questo marca DAVVERO tutte le copie
        # del gruppo, prima inclusa: utile quando non se ne vuole
        # tenere NESSUNA. Stile piu' scuro/deciso per non confonderlo
        # con "Cancella copie".
        delete_all_btn = QPushButton(f"Cancella tutto\n({len(group.items)} file)")
        delete_all_btn.setToolTip(
            "Marca TUTTE le copie di questo gruppo per l'eliminazione, "
            "compresa la prima (a differenza di \"Cancella copie\", che "
            "tiene sempre la prima)."
        )
        delete_all_btn.setStyleSheet(
            "QPushButton { background-color: #8a2f2f; color: #fff; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: #9a3f3f; }"
        )
        delete_all_btn.clicked.connect(lambda: self._delete_all(group_checks))
        actions_col.addWidget(delete_all_btn)

        actions_col.addStretch(1)
        outer.addLayout(actions_col)

        return card

    def _build_item_card(self, item: FileItem, group_checks: list[QCheckBox]) -> QWidget:
        item_widget = QWidget()
        item_widget.setAttribute(Qt.WA_StyledBackground, True)
        iv = QVBoxLayout(item_widget)

        # SEGNALATO: "se schiaccio cancella copie selezionate mi
        # rimangono li', non e' chiaro se sono cancellati o meno" —
        # etichetta ben visibile che appare SOLO quando questa copia e'
        # marcata per l'eliminazione (vedi _apply_card_marked_style),
        # cosi' un click su "Cancella copie"/colonna/checkbox si vede
        # SUBITO sulla scheda stessa, anche se il file vero e proprio
        # sparisce solo dopo "Elimina i selezionati" (con conferma).
        mark_label = QLabel("🗑 Sarà eliminato")
        mark_label.setAlignment(Qt.AlignCenter)
        mark_label.setStyleSheet(
            "background-color: #6d3d3d; color: #fff; font-weight: bold;"
            " font-size: 10px; border-radius: 3px; padding: 2px 4px;"
        )
        mark_label.setVisible(False)
        iv.addWidget(mark_label)
        self._mark_labels[item.path] = mark_label
        self._card_widgets[item.path] = item_widget

        # piccolo pulsante in alto a sinistra per trovare il file
        # direttamente in Esplora risorse, senza doverlo prima aprire
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        reveal_btn = QPushButton("📁")
        reveal_btn.setFixedSize(22, 22)
        reveal_btn.setToolTip("Apri in Esplora risorse")
        reveal_btn.setStyleSheet(
            "QPushButton { background-color: #333; border-radius: 4px; padding: 0px; }"
            "QPushButton:hover { background-color: #444; }"
        )
        reveal_btn.clicked.connect(lambda _, p=item.path: reveal_in_explorer(p))
        top_row.addWidget(reveal_btn)
        top_row.addStretch(1)
        iv.addLayout(top_row)

        size = self._zoom_size
        thumb = QLabel()
        thumb.setFixedSize(size, size)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background-color: #1a1a1a; border-radius: 4px; color: #666;")
        thumb.setCursor(Qt.PointingHandCursor)
        thumb.setToolTip("Clic per aprire il file")

        # le miniature sono in cache per path, decodificate una sola
        # volta a DECODE_THUMB_SIZE in un thread separato (vedi
        # _ThumbBatchWorker/_start_thumb_loading): lo zoom si limita a
        # scalare la pixmap gia' in cache, senza mai ridecodificare da
        # disco. Se non e' ancora in cache si mostra un segnaposto e la
        # si aggiorna quando il worker in background la produce.
        self._thumb_labels[item.path] = thumb
        if item.path in self._thumb_cache:
            base_pix = self._thumb_cache[item.path]
            if base_pix is not None:
                thumb.setPixmap(base_pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("📄")
        else:
            thumb.setText("...")

        path_for_click = item.path
        open_fn = lambda ev, p=path_for_click: QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        thumb.mousePressEvent = open_fn

        lines = [
            f"<b>{Path(item.path).name}</b>",
            f"Dimensione: {_format_size(item.size)}",
            f"Creato: {_format_date(item.ctime)}",
            f"Modificato: {_format_date(item.mtime)}",
        ]
        if item.category == FileCategory.VIDEO:
            lines.append(f"Durata: {_format_duration(self._duration_cache.get(item.path))}")

        info = QLabel("<br>".join(lines))
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 10px;")
        info.setFixedWidth(max(size + 50, 140))
        info.setCursor(Qt.PointingHandCursor)
        info.mousePressEvent = open_fn
        self._info_labels[item.path] = info

        # checkbox "Cancella" (non piu' "Tieni"): checked = questo file
        # verra' eliminato. Di default checked per tutte le copie tranne
        # la prima (vedi _keep_state in __init__).
        cb = QCheckBox("Cancella")
        cb.setChecked(not self._keep_state.get(item.path, True))
        cb.toggled.connect(lambda checked, p=item.path: self._on_toggle(p, not checked))

        iv.addWidget(thumb, alignment=Qt.AlignCenter)
        iv.addWidget(info)
        iv.addWidget(cb, alignment=Qt.AlignCenter)

        group_checks.append(cb)
        # stato iniziale della scheda coerente con la checkbox appena
        # creata (importante per _rebuild(), che ricrea tutte le
        # schede da zero leggendo _keep_state: senza questo, una
        # scheda ricostruita dopo un "Colonna N" o "tieni solo la
        # prima" tornerebbe visivamente "pulita" anche se in realta'
        # e' ancora marcata per l'eliminazione).
        self._apply_card_marked_style(item.path, marked=not self._keep_state.get(item.path, True))
        return item_widget

    def _apply_card_marked_style(self, path: str, marked: bool) -> None:
        """Aggiorna l'aspetto della scheda di 'path' in base a se e'
        marcata per l'eliminazione o no: etichetta rossa visibile,
        bordo rosso e opacita' ridotta quando marcata; aspetto normale
        altrimenti. Chiamato sia alla creazione della scheda sia ad
        ogni cambio di stato (checkbox singola, pulsanti per riga/
        colonna, 'tieni solo la prima' su tutti i gruppi)."""
        card = self._card_widgets.get(path)
        label = self._mark_labels.get(path)
        if label is not None:
            label.setVisible(marked)
        if card is not None:
            card.setStyleSheet(
                "background-color: #3d2323; border: 1px solid #8a4a4a; border-radius: 6px;"
                if marked else
                "background-color: transparent; border: 1px solid transparent; border-radius: 6px;"
            )
            effect = card.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(card)
                card.setGraphicsEffect(effect)
            effect.setOpacity(0.55 if marked else 1.0)

    def _on_toggle(self, path: str, keep: bool) -> None:
        self._keep_state[path] = keep
        self._apply_card_marked_style(path, marked=not keep)
        self._update_summary()
        self._refresh_all_column_btns()

    def _check_all(self, checks: list[QCheckBox]) -> None:
        """'Non cancellare nessuno': scheck (Cancella=no) tutte le
        checkbox del gruppo."""
        for cb in checks:
            cb.setChecked(False)

    def _keep_only_first(self, checks: list[QCheckBox]) -> None:
        """'Cancella copie': seleziona Cancella per tutte tranne la
        prima (indice 0)."""
        for i, cb in enumerate(checks):
            cb.setChecked(i != 0)

    def _delete_all(self, checks: list[QCheckBox]) -> None:
        """'Cancella tutto': RICHIESTA esplicita — marca TUTTE le copie
        del gruppo per l'eliminazione, PRIMA COMPRESA (a differenza di
        _keep_only_first, che la tiene sempre). Utile quando non se ne
        vuole tenere nessuna."""
        for cb in checks:
            cb.setChecked(True)

    def _keep_only_first_all_groups(self) -> None:
        """Come _keep_only_first, ma per tutti i gruppi insieme: tiene
        solo il primo file di ogni gruppo e marca il resto per
        l'eliminazione. Lavora direttamente su _keep_state (la fonte di
        verita') e poi ricostruisce la lista per aggiornare le checkbox
        a schermo."""
        for group in self._groups:
            for i, item in enumerate(group.items):
                self._keep_state[item.path] = (i == 0)
        self._rebuild()
        self._refresh_all_column_btns()

    def _make_column_toggle_btn(self, col: int) -> QPushButton:
        """Un unico pulsante per la 'colonna' N (l'N-esimo file di ogni
        gruppo, 1-based). BUG RISOLTO ("clicco Colonna 3 e non succede
        niente, clicco di nuovo e mi deseleziona tutto" — segnalato con
        la sequenza esatta): il pulsante aveva una sua 'memoria'
        separata (delete_mode) che partiva sempre da 'prossimo clic =
        segna per l'eliminazione', SCOLLEGATA dallo stato vero delle
        checkbox. Ma le copie (tranne la prima di ogni gruppo) sono
        gia' selezionate per l'eliminazione di default: il primo clic
        quindi non cambiava nulla (chiedeva di fare qualcosa gia'
        fatto), il secondo si' — sembrava che il pulsante 'saltasse un
        colpo'. La stessa cosa succedeva anche cambiando le checkbox a
        mano o con altre scorciatoie: il pulsante restava scollegato da
        quello che si vedeva davvero. Ora il pulsante non ha piu' una
        sua memoria: colore/testo/azione si ricalcolano SEMPRE dallo
        stato reale delle checkbox per quella colonna (vedi
        _column_state), quindi sono sempre coerenti con cio' che si
        vede, indipendentemente da come sono state cambiate."""
        btn = QPushButton()
        btn.setProperty("col", col)
        self._column_buttons[col] = btn
        self._refresh_column_btn_style(col)
        btn.clicked.connect(lambda: self._on_column_toggle_clicked(col))
        return btn

    def _column_state(self, col: int) -> str:
        """'all_delete' se la colonna e' interamente selezionata per
        l'eliminazione, 'all_keep' se interamente tenuta, 'mixed' se e'
        un misto (puo' capitare se alcuni gruppi hanno meno copie di
        altri, o dopo modifiche manuali alle singole checkbox)."""
        idx = col - 1
        states = [
            not self._keep_state.get(group.items[idx].path, False)  # True = segnato per l'eliminazione
            for group in self._groups if idx < len(group.items)
        ]
        if not states:
            return "all_keep"
        if all(states):
            return "all_delete"
        if not any(states):
            return "all_keep"
        return "mixed"

    def _refresh_column_btn_style(self, col: int) -> None:
        """SEGNALATO: "le voci colonna 2 colonna 3 colonna 4 sono
        ancora non chiare" — al posto delle vecchie icone (🗑️/✅/◐) +
        "Colonna N" (che non diceva COSA sarebbe successo cliccando),
        il testo del pulsante ora e' l'AZIONE stessa che il clic
        eseguira', in maiuscolo per essere ben visibile:
        "SELEZIONA COLONNA N" se cliccando le marchi per l'eliminazione,
        "DESELEZIONA COLONNA N" se cliccando le togli dall'eliminazione
        (le tieni). Dato che le copie sono gia' selezionate per
        l'eliminazione di default (vedi _keep_state in __init__), la
        colonna 2 in poi mostra "DESELEZIONA" fin da subito, non
        "SELEZIONA" — coerente con lo stato vero, non con un'ipotetica
        azione di default sbagliata. Il colore (rosso/verde/giallo)
        resta com'era, per distinguere a colpo d'occhio anche lo stato
        "misto" (solo alcuni gruppi hanno una copia in quella
        posizione)."""
        btn = self._column_buttons.get(col)
        if btn is None:
            return
        # RICHIESTA: "riesci a mettere a capo la scritta colonna?" —
        # testo lungo ("SELEZIONA COLONNA 4") su una riga sola stava
        # stretto/tagliato sul pulsante. Va a capo tra l'azione e
        # "COLONNA N", stesso trattamento gia' usato per gli altri
        # pulsanti a due righe in questo pannello (es. "Cancella
        # copie\n(tieni solo la prima)").
        state = self._column_state(col)
        if state == "all_delete":
            # tutte gia' marcate per l'eliminazione: il clic le TIENE
            btn.setText(f"DESELEZIONA\nCOLONNA {col}")
            btn.setToolTip(
                f"Colonna {col}: tutte le copie in questa posizione sono "
                "gia' selezionate per l'eliminazione. Clic: tienile tutte."
            )
            btn.setStyleSheet(
                "QPushButton { background-color: #6d3d3d; color: #fff; border-radius: 4px;"
                " padding: 3px 10px; font-weight: 600; }"
                "QPushButton:hover { background-color: #7d4d4d; }"
            )
        elif state == "all_keep":
            # nessuna marcata: il clic le SELEZIONA per l'eliminazione
            btn.setText(f"SELEZIONA\nCOLONNA {col}")
            btn.setToolTip(
                f"Colonna {col}: tutte le copie in questa posizione sono "
                "tenute. Clic: selezionale tutte per l'eliminazione."
            )
            btn.setStyleSheet(
                "QPushButton { background-color: #3d6d45; color: #fff; border-radius: 4px;"
                " padding: 3px 10px; font-weight: 600; }"
                "QPushButton:hover { background-color: #4d7d55; }"
            )
        else:  # mixed
            btn.setText(f"SELEZIONA\nCOLONNA {col}")
            btn.setToolTip(
                f"Colonna {col}: solo ALCUNE copie in questa posizione sono "
                "selezionate per l'eliminazione. Clic: selezionale tutte."
            )
            btn.setStyleSheet(
                "QPushButton { background-color: #5a5530; color: #fff; border-radius: 4px;"
                " padding: 3px 10px; font-weight: 600; }"
                "QPushButton:hover { background-color: #6a6540; }"
            )

    def _refresh_all_column_btns(self) -> None:
        for col in self._column_buttons:
            self._refresh_column_btn_style(col)

    def _on_column_toggle_clicked(self, col: int) -> None:
        # SEGNALATO: "crash subito dopo aver aperto duplicati e
        # cliccato su seleziona colonna" — non ancora riprodotto in
        # test automatici (scansione reale, duplicati reali, click
        # sulle colonne: tutto verificato senza errori), ma per
        # sicurezza questo pulsante non deve MAI poter chiudere
        # l'intero programma: qualunque problema imprevisto qui viene
        # ora intercettato e mostrato nella barra di stato invece di
        # interrompere tutto, cosi' anche se il bug si ripresenta resta
        # utilizzabile e soprattutto il messaggio d'errore aiuta a
        # trovarlo per davvero.
        try:
            state = self._column_state(col)
            # se e' gia' tutta segnata per l'eliminazione, il clic la
            # tiene tutta; in ogni altro caso (tutta tenuta, o mista)
            # il clic la segna tutta per l'eliminazione — cosi' un solo
            # clic porta sempre a uno stato "pulito" (tutto o niente),
            # mai a uno stato intermedio che richiederebbe di indovinare
            # cosa succedera'
            keep = state == "all_delete"
            self._set_column_keep(col, keep=keep)
        except Exception as e:  # pragma: no cover - rete di sicurezza
            import traceback
            traceback.print_exc()
            if self.summary_label is not None:
                self.summary_label.setText(f"Errore su Colonna {col}: {e}")

    def _set_column_keep(self, column: int, keep: bool) -> None:
        """'Colonna N' = l'N-esimo file di ogni gruppo (1-based). Utile
        quando un gruppo ha piu' di 2 copie: permette di dire ad
        esempio "tieni sempre la terza copia" su tutti i gruppi in un
        colpo solo, invece di aprire ogni gruppo uno per uno. I gruppi
        che non arrivano a quella posizione vengono ignorati."""
        idx = column - 1
        for group in self._groups:
            if idx < len(group.items):
                self._keep_state[group.items[idx].path] = keep
        self._rebuild()
        self._refresh_all_column_btns()

    def _update_summary(self) -> None:
        to_delete = [self._item_by_path[p] for p, keep in self._keep_state.items() if not keep]
        size_mb = sum(item.size for item in to_delete) / (1024 * 1024)
        if to_delete:
            self.summary_label.setText(
                f"Verranno eliminati {len(to_delete)} file ({size_mb:.1f} MB liberati)"
            )
        else:
            self.summary_label.setText("Nessun file selezionato per l'eliminazione")

    def paths_to_delete(self) -> list[str]:
        return [p for p, keep in self._keep_state.items() if not keep]
