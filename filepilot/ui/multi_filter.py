"""
ui/multi_filter.py
Filtro "tipo di file" a selezione multipla, organizzato a gruppi
espandibili (Multimedia, Documenti, Altro...) che contengono categorie
(Foto, Video, Audio...), a loro volta espandibili nei singoli FORMATI
(es. .mp3, .wav dentro Audio) — RICHIESTA: "nella tendina in basso a
sinistra pero' mi da solo la voce audio, non tutti i formati che ci
sono, mettili anche li' cosi' da essere piu' veloce nella scelta". Chi
vuole filtrare per intere categorie clicca solo le checkbox di primo/
secondo livello come prima; chi vuole essere piu' preciso (es. solo
.mp3, non tutto l'Audio) espande la categoria e sceglie i singoli
formati, senza dover aprire le Impostazioni per farlo. Il pulsante
apre un popup indipendente (NON un QMenu) dove ogni gruppo/categoria
ha un'intestazione con checkbox "seleziona tutto" e una freccia che
espande/comprime verso il basso il livello sottostante.

Nota tecnica: un QMenu con widget personalizzati incollati dentro
(QWidgetAction) puo' chiudersi in modo imprevedibile ai clic, perche'
QMenu fa una gestione speciale del mouse pensata per semplici voci di
menu, non per contenuti interattivi complessi. Un QWidget con flag
Qt.Popup si comporta invece come una finestra normale: i clic al suo
interno funzionano sempre in modo affidabile, e si chiude solo
cliccando fuori da essa.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import (
    QToolButton, QCheckBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame,
)

from filepilot.models import FileCategory, CATEGORY_LABELS, CATEGORY_GROUPS, CATEGORY_EXTENSIONS


class _GroupCheckBox(QCheckBox):
    """Checkbox tri-state ma solo per la VISUALIZZAZIONE (mostra lo
    stato 'parziale' quando alcuni dei suoi figli sono spuntati e
    altri no). Il click dell'utente alterna sempre e solo tra
    tutto/niente, ignorando lo stato parziale nel ciclo."""

    def nextCheckState(self) -> None:
        if self.checkState() == Qt.Checked:
            self.setCheckState(Qt.Unchecked)
        else:
            self.setCheckState(Qt.Checked)


class _GroupHeader(QWidget):
    """Intestazione riusabile per un livello espandibile: checkbox
    'seleziona tutto' + nome + freccia. Un clic sull'intestazione
    (fuori dalla checkbox) espande o comprime il contenuto sottostante.
    Usata sia per i GRUPPI (Multimedia, Documenti...) sia, un livello
    piu' sotto, per le singole CATEGORIE (Audio, Video...) quando
    mostrano i loro formati."""

    toggle_requested = Signal()

    def __init__(self, name: str, bold: bool = True, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.group_checkbox = _GroupCheckBox()
        self.group_checkbox.setTristate(True)
        layout.addWidget(self.group_checkbox)

        text = f"<b>{name}</b>" if bold else name
        self.name_label = QLabel(text)
        self.name_label.setStyleSheet("color: #eee;")
        layout.addWidget(self.name_label, stretch=1)

        self.arrow_label = QLabel("▸")
        self.arrow_label.setStyleSheet("color: #999;")
        layout.addWidget(self.arrow_label)

    def set_expanded(self, expanded: bool) -> None:
        self.arrow_label.setText("▾" if expanded else "▸")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.group_checkbox.underMouse():
            self.toggle_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _CategoryRow(QWidget):
    """Una categoria dentro un gruppo (es. 'Audio' dentro 'Multimedia'),
    con i suoi singoli formati elencati sotto, comprimibili — stesso
    meccanismo espandi/comprimi di _CategoryGroupWidget, un livello
    piu' in profondita' (categoria -> formati invece di gruppo ->
    categorie). Chi non espande vede/usa solo la checkbox della
    categoria come prima (comportamento identico a prima di questa
    modifica)."""

    changed = Signal()

    def __init__(self, label: str, category: FileCategory, extensions: list[str], parent=None):
        super().__init__(parent)
        self.category = category
        self.ext_checkboxes: dict[str, QCheckBox] = {}
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = _GroupHeader(label, bold=False)
        self.header.toggle_requested.connect(self._toggle_expanded)
        self.header.group_checkbox.stateChanged.connect(self._on_master_changed)
        outer.addWidget(self.header)

        self.children_container = QWidget()
        child_layout = QVBoxLayout(self.children_container)
        child_layout.setContentsMargins(24, 2, 4, 4)
        child_layout.setSpacing(2)
        for ext in extensions:
            cb = QCheckBox(ext)
            cb.setChecked(True)
            cb.setStyleSheet("color: #bbb; font-size: 11px;")
            cb.stateChanged.connect(self._on_ext_changed)
            child_layout.addWidget(cb)
            self.ext_checkboxes[ext] = cb
        # se una categoria non ha formati noti (non dovrebbe succedere,
        # ma per sicurezza), niente freccia/espansione: la checkbox
        # della categoria resta l'unico controllo, come prima.
        if not extensions:
            self.header.arrow_label.setVisible(False)
        self.children_container.setVisible(False)
        outer.addWidget(self.children_container)

        self._sync_master_checkbox()

    def _toggle_expanded(self) -> None:
        if not self.ext_checkboxes:
            return
        self._expanded = not self._expanded
        self.children_container.setVisible(self._expanded)
        self.header.set_expanded(self._expanded)

    def _on_master_changed(self, state: int) -> None:
        # BUG RISOLTO: vedi commento identico in
        # ui/settings_dialog.py._on_category_master_changed — 'state'
        # e' l'int grezzo del segnale stateChanged, va ricostruito
        # l'enum prima di confrontarlo con Qt.Checked, altrimenti
        # "riseleziona tutto il formato" non funziona mai.
        checked = Qt.CheckState(state) == Qt.Checked
        for cb in self.ext_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self.changed.emit()

    def _on_ext_changed(self) -> None:
        self._sync_master_checkbox()
        self.changed.emit()

    def _sync_master_checkbox(self) -> None:
        states = [cb.isChecked() for cb in self.ext_checkboxes.values()]
        self.header.group_checkbox.blockSignals(True)
        if not states or all(states):
            self.header.group_checkbox.setCheckState(Qt.Checked)
        elif not any(states):
            self.header.group_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.header.group_checkbox.setCheckState(Qt.PartiallyChecked)
        self.header.group_checkbox.blockSignals(False)

    def set_all(self, checked: bool) -> None:
        """Usato dal gruppo padre per un 'seleziona/deseleziona tutto'
        a cascata: spunta/toglie sia la checkbox della categoria sia
        tutte le sue estensioni, senza far scattare segnali intermedi
        (li emette una volta sola il chiamante)."""
        for cb in self.ext_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self.header.group_checkbox.blockSignals(True)
        self.header.group_checkbox.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.header.group_checkbox.blockSignals(False)


class _CategoryGroupWidget(QWidget):
    """Un gruppo completo: intestazione + elenco categorie che si
    apre verso il basso quando espanso."""

    changed = Signal()

    def __init__(self, group_name: str, options: list[tuple[str, FileCategory, list[str]]], parent=None):
        super().__init__(parent)
        self.category_rows: dict[FileCategory, _CategoryRow] = {}
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = _GroupHeader(group_name)
        self.header.toggle_requested.connect(self._toggle_expanded)
        self.header.group_checkbox.stateChanged.connect(self._on_group_checkbox_changed)
        outer.addWidget(self.header)

        self.children_container = QWidget()
        child_layout = QVBoxLayout(self.children_container)
        child_layout.setContentsMargins(28, 2, 8, 6)
        child_layout.setSpacing(3)
        # RICHIESTA: "la tendina è secondaria, si basa su quello che è
        # selezionato nelle impostazioni" — le estensioni da mostrare
        # per ogni categoria arrivano gia' FILTRATE dal chiamante
        # (MultiTypeFilter._rebuild_groups), non sono piu' calcolate
        # qui internamente da CATEGORY_EXTENSIONS al completo.
        for label, cat, extensions in options:
            row = _CategoryRow(label, cat, extensions)
            row.changed.connect(self._on_child_changed)
            child_layout.addWidget(row)
            self.category_rows[cat] = row
        self.children_container.setVisible(False)
        outer.addWidget(self.children_container)

        self._sync_group_checkbox()

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self.children_container.setVisible(self._expanded)
        self.header.set_expanded(self._expanded)

    def _on_group_checkbox_changed(self, state: int) -> None:
        # BUG RISOLTO: stesso problema di _on_master_changed qui sopra.
        checked = Qt.CheckState(state) == Qt.Checked
        for row in self.category_rows.values():
            row.set_all(checked)
        self.changed.emit()

    def _on_child_changed(self) -> None:
        self._sync_group_checkbox()
        self.changed.emit()

    def _sync_group_checkbox(self) -> None:
        states = [row.header.group_checkbox.checkState() for row in self.category_rows.values()]
        all_checked = all(s == Qt.Checked for s in states)
        none_checked = all(s == Qt.Unchecked for s in states)
        self.header.group_checkbox.blockSignals(True)
        if all_checked:
            self.header.group_checkbox.setCheckState(Qt.Checked)
        elif none_checked:
            self.header.group_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.header.group_checkbox.setCheckState(Qt.PartiallyChecked)
        self.header.group_checkbox.blockSignals(False)


class _FilterPopup(QWidget):
    """Popup indipendente (non un QMenu) che ospita i gruppi di
    checkbox, dentro un'area scorrevole a dimensione FISSA. Si chiude
    solo cliccando fuori da esso.

    BUG SEGNALATO ("uso tanto la tendina, apro/seleziono/deseleziono
    file... mi cambia dimensione"): prima il contenuto (i gruppi con
    le loro checkbox) viveva direttamente nel layout del popup, che
    essendo un widget top-level con un proprio layout si ridimensiona
    AUTOMATICAMENTE al contenuto per default in Qt — quindi ogni
    espandi/comprimi di un gruppo, o anche solo il ricalcolo dopo un
    clic su una checkbox, poteva far cambiare le dimensioni del
    popup mentre era aperto. Ora il contenuto vive dentro una
    QScrollArea a dimensione fissa (impostata una volta sola
    all'apertura): il popup stesso non cambia mai dimensione durante
    l'uso, qualunque gruppo/categoria si espanda o checkbox si spunti
    — se il contenuto espanso non ci sta tutto, scorre dentro invece
    di far crescere/spostare il popup."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setStyleSheet(
            "background-color: #262626; border: 1px solid #3a3a3a; border-radius: 6px;"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        outer.addWidget(self.scroll)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(inner)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(2)
        self.scroll.setWidget(inner)


class MultiTypeFilter(QToolButton):
    """Pulsante con popup a gruppi/categorie/formati espandibili, per
    selezionare piu' tipi di file insieme (es. Foto + Video, o tutto
    il gruppo Documenti) oppure singoli formati precisi (es. solo
    .mp3 dentro Audio)."""

    selection_changed = Signal()

    def __init__(self, enabled_extensions: set[str] | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QToolButton { background-color: #262626; border: 1px solid #3a3a3a;"
            " border-radius: 4px; padding: 4px 8px; color: #ddd; }"
            "QToolButton:hover { background-color: #2e2e2e; }"
        )
        self.clicked.connect(self._toggle_popup)

        self._popup = _FilterPopup(self)
        self._groups: list[_CategoryGroupWidget] = []
        self._rebuild_groups(enabled_extensions if enabled_extensions is not None else set(SUPPORTED_EXT))

    def set_enabled_extensions(self, enabled: set[str]) -> None:
        """RICHIESTA: "la scelta dei formati nelle impostazioni è la
        principale, quella della tendina è secondaria e si basa su
        quello che è selezionato nell'impostazioni... ho audio nel
        menu a tendina, vado in impostazioni, tolgo il flag a audio e
        mi sparisce anche dal menu a tendina". Chiamato da
        main_window.py ogni volta che le Impostazioni vengono salvate
        (e all'avvio, con le estensioni salvate in config): ricostruisce
        la tendina da zero mostrando SOLO le estensioni/categorie
        abilitate. Una categoria con zero estensioni abilitate sparisce
        del tutto (non solo le sue singole estensioni); un gruppo con
        tutte le categorie sparite sparisce a sua volta."""
        was_visible = self._popup.isVisible()
        if was_visible:
            self._popup.hide()
        self._rebuild_groups(enabled)
        self.selection_changed.emit()

    def _rebuild_groups(self, enabled_extensions: set[str]) -> None:
        # pulisce il popup esistente (se e' una ricostruzione, non la
        # prima costruzione)
        while self._popup.content_layout.count():
            item = self._popup.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        self._groups = []
        for group_name, categories in CATEGORY_GROUPS.items():
            options = []
            for cat in categories:
                cat_extensions = sorted(CATEGORY_EXTENSIONS.get(cat, set()) & enabled_extensions)
                if not cat_extensions:
                    continue  # categoria interamente disattivata in Impostazioni: non compare qui
                options.append((CATEGORY_LABELS[cat], cat, cat_extensions))
            if not options:
                continue  # gruppo interamente vuoto: non compare nemmeno il gruppo
            group_widget = _CategoryGroupWidget(group_name, options)
            group_widget.changed.connect(self._on_change)
            self._popup.content_layout.addWidget(group_widget)
            self._groups.append(group_widget)
        self._popup.content_layout.addStretch(1)

        self._update_label()

    def _toggle_popup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
            return

        popup_width = max(self.width(), 260)

        # Dimensione FISSA (vedi commento su _FilterPopup): calcolata
        # una volta sola all'apertura in base allo schermo disponibile,
        # non cambia piu' mentre il popup resta aperto — ne' aprendo/
        # chiudendo un gruppo o categoria, ne' spuntando/togliendo
        # checkbox.
        screen = self.screen()
        screen_rect = screen.availableGeometry() if screen is not None else None
        if screen_rect is not None:
            popup_height = max(280, min(420, int(screen_rect.height() * 0.6)))
        else:
            popup_height = 380

        self._popup.setFixedSize(popup_width, popup_height)

        button_top_left = self.mapToGlobal(QPoint(0, 0))
        button_bottom_left = self.mapToGlobal(QPoint(0, self.height()))

        # BUG SEGNALATO ("la tendina dei formati si apre verso il
        # basso e quindi scompare"): prima il popup veniva SEMPRE
        # posizionato con lo stesso offset fisso, senza guardare
        # quanto spazio ci fosse davvero sopra o sotto il pulsante su
        # quello specifico schermo/risoluzione — cosi' una parte del
        # popup poteva finire oltre il bordo visibile e diventare
        # irraggiungibile. Ora si sceglie la direzione (sopra o
        # sotto) in base allo spazio DISPONIBILE, e la posizione
        # finale viene comunque bloccata dentro i bordi dello schermo.
        if screen_rect is not None:
            # piccolo margine di sicurezza: oltre a essere piu' bello
            # esteticamente (mai attaccato al pixel esatto del bordo
            # schermo), assorbe anche piccoli scarti di 1-2px che
            # alcuni backend Qt introducono tra la posizione richiesta
            # con move() e quella poi effettivamente riportata.
            margin = 6
            space_below = screen_rect.bottom() - button_bottom_left.y()
            space_above = button_top_left.y() - screen_rect.top()
            if popup_height <= space_below or space_below >= space_above:
                pos_y = button_bottom_left.y()
            else:
                pos_y = button_top_left.y() - popup_height
            pos_y = max(screen_rect.top() + margin, min(pos_y, screen_rect.bottom() - popup_height - margin))
            pos_x = max(screen_rect.left() + margin, min(button_top_left.x(), screen_rect.right() - popup_width - margin))
        else:
            pos_y = button_bottom_left.y()
            pos_x = button_top_left.x()

        self._popup.move(pos_x, pos_y)
        self._popup.show()

    def _all_extension_checkboxes(self) -> dict[str, QCheckBox]:
        result: dict[str, QCheckBox] = {}
        for group in self._groups:
            for row in group.category_rows.values():
                result.update(row.ext_checkboxes)
        return result

    def _on_change(self) -> None:
        self._update_label()
        self.selection_changed.emit()

    def _update_label(self) -> None:
        checks = self._all_extension_checkboxes()
        total = len(checks)
        if total == 0:
            # nessun formato abilitato in Impostazioni > Formati
            self.setText("Nessun formato abilitato ▾")
            return
        selected = sum(1 for cb in checks.values() if cb.isChecked())
        if selected == total:
            self.setText("Tutti i tipi ▾")
        elif selected == 0:
            self.setText("Nessun tipo ▾")
        else:
            self.setText(f"{selected} formati selezionati ▾")

    def selected_extensions(self) -> set[str]:
        return {ext for ext, cb in self._all_extension_checkboxes().items() if cb.isChecked()}

    def is_all_selected(self) -> bool:
        checks = self._all_extension_checkboxes()
        return all(cb.isChecked() for cb in checks.values())
