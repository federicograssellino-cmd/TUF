"""
ui/main_window.py
Finestra principale di TideUp File (TUF). Assembla:
- sinistra (75%): anteprima grande + filtri/ricerca in basso
- destra (25%): solo cartelle, due colonne
- basso: barra comandi
Gestisce scorciatoie da tastiera (1..9 = sposta file, 0 = elimina),
undo, dashboard iniziale, flusso duplicati e salvataggio/ripristino
configurazione.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QByteArray, QUrl, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QLineEdit, QComboBox, QFileDialog, QMessageBox, QPushButton, QStackedWidget,
)

from filepilot.config import ConfigManager, FolderTarget, trash_dir
from filepilot.core.scanner import FileScanner
from filepilot.core.duplicates import DuplicateFinder, DuplicateGroup
from filepilot.models import FileItem, FileCategory, SUPPORTED_EXT
from filepilot.ui.preview_widget import PreviewWidget
from filepilot.ui.folder_panel import FolderPanel, DEFAULT_SIZE_LEVEL
from filepilot.ui.bottom_bar import BottomBar
from filepilot.ui.dashboard import DashboardDialog
from filepilot.ui.duplicate_review_dialog import DuplicateReviewPanel
from filepilot.ui.branding import app_icon, BrandedHeader, enable_dark_titlebar
from filepilot.ui.delete_progress_overlay import DeleteProgressOverlay
from filepilot.core.delete_worker import DuplicateDeleteWorker, DeleteItem
from filepilot.ui.settings_dialog import SettingsDialog
from filepilot.ui.quick_guide_dialog import QuickGuideDialog
from filepilot.ui.onboarding_tour import OnboardingTour, TourStep
from filepilot.ui.multi_filter import MultiTypeFilter
from filepilot.core.voice_control import VoiceWorker, parse_voice_command, parse_yes_no
from filepilot.ui.fly_animation import animate_file_to_folder
from filepilot.ui.confirm_overlay import DeleteConfirmOverlay
from filepilot.core.update_check import UpdateCheckWorker
from filepilot import __version__

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


class MoveAction:
    """Rappresenta uno spostamento file, per undo. Tiene anche il
    FileItem originale cosi' l'undo puo' farlo ricomparire subito
    nel visualizzatore invece di andare perso."""

    def __init__(self, src: str, dst: str, item: FileItem):
        self.src = src
        self.dst = dst
        self.item = item


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TideUp File (TUF)")
        self.setWindowIcon(app_icon())
        self.resize(1400, 900)
        self.setStyleSheet("background-color: #181818;")

        self.config = ConfigManager()

        self.all_items: list[FileItem] = []
        self.filtered_items: list[FileItem] = []
        self.current_index: int = -1
        self.undo_stack: list[MoveAction] = []
        self._clamping_geometry = False  # guardia anti-ricorsione per _clamp_geometry_to_screen
        self.current_source_folder: str = ""

        self.scanner: FileScanner | None = None
        self.dup_finder: DuplicateFinder | None = None
        self.dup_groups: list[DuplicateGroup] = []
        self.voice_worker: VoiceWorker | None = None
        self.pending_delete_item: FileItem | None = None  # in attesa di conferma (overlay o voce)
        self._pending_single_delete_item: FileItem | None = None  # in eliminazione (thread separato)
        self._single_delete_worker: DuplicateDeleteWorker | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_release_url: str = ""
        self._onboarding_tour: OnboardingTour | None = None

        # RICHIESTA: "e se usassi questo tasto \ per scrivere la doppia
        # cifra? ovviamente prima di scrivere i numeri" — stato per la
        # scorciatoia a due cifre (premere '\', poi due tasti numero),
        # per raggiungere cartelle numerate 10 in su senza mouse. Vedi
        # _on_digit_key più sotto.
        self._double_digit_pending = False
        self._double_digit_first: int | None = None
        self._double_digit_timer = QTimer(self)
        self._double_digit_timer.setSingleShot(True)
        self._double_digit_timer.timeout.connect(self._on_double_digit_timeout)

        self._build_ui()
        self._restore_config()
        self._install_shortcuts()

        # BUG RISOLTO (possibile causa di "la finestra si sposta/si
        # rompe" su Windows, specialmente aprendo dialoghi come il
        # Riepilogo cartella): enable_dark_titlebar() chiama winId(),
        # che forza Qt a creare SUBITO l'handle nativo della finestra
        # (DWM/Windows). La funzione stessa documenta di andare
        # chiamata DOPO che il layout esiste gia', ma prima veniva
        # chiamata a inizio __init__, ancora PRIMA di _build_ui():
        # forzare la creazione dell'handle nativo prima che la finestra
        # abbia contenuto/dimensioni definitive puo' causare, su
        # Windows, ricalcoli di geometria imprevisti quando poi la
        # finestra viene popolata e ridimensionata (ancora piu'
        # probabile se nel frattempo si apre anche un dialogo figlio,
        # che a sua volta forzava lo stesso problema — vedi
        # ui/dashboard.py, ui/settings_dialog.py, ui/import_dialog.py).
        # Ora viene chiamata qui, a fine __init__, quando splitter e
        # tutti i pannelli sono gia' completamente costruiti.
        enable_dark_titlebar(self)

        if send2trash is None:
            self.bottom_bar.set_status(
                "⚠ Modulo Cestino (Send2Trash) non installato: i file eliminati "
                "NON andranno nel Cestino di Windows. Esegui: pip install -r requirements.txt"
            )

        # RICHIESTA: "crea anche una guida veloce e pratica che si
        # apre in una finestra appena apri per la prima volta il
        # programma" — controlliamo un flag persistito in config.json
        # (vedi config.py: e' solo un booleano, non c'entra nulla con
        # la politica no-log). QTimer.singleShot(0, ...) fa comparire
        # il dialogo SUBITO DOPO che la finestra principale e' gia'
        # visibile (show() viene chiamato da main.py dopo il
        # costruttore), invece che durante __init__ quando la finestra
        # non ha ancora una geometria definitiva sullo schermo.
        if not self.config.get("guide_seen", False):
            QTimer.singleShot(200, self._show_first_run_guide)

        # RICHIESTA: "vorrei rilasciare gli aggiornamenti su software
        # installati su altri pc" — controllo in background, poco dopo
        # l'avvio, se su GitHub esiste una versione piu' recente (vedi
        # core/update_check.py). SOLO avviso + link, mai download/
        # installazione automatica: se c'e' una versione nuova compare
        # un pulsante cliccabile nell'intestazione, altrimenti non
        # cambia nulla e non compare nessun popup.
        QTimer.singleShot(1500, self._start_update_check)

    def _start_update_check(self) -> None:
        self._update_check_worker = UpdateCheckWorker(__version__, self)
        self._update_check_worker.update_available.connect(self._on_update_available)
        self._update_check_worker.start()

    def _on_update_available(self, new_version: str, release_url: str) -> None:
        self._update_release_url = release_url
        self.update_btn.setText(f"⬆ Nuova versione disponibile ({new_version})")
        self.update_btn.setVisible(True)

    def _open_update_page(self) -> None:
        if self._update_release_url:
            QDesktopServices.openUrl(QUrl(self._update_release_url))

    def _show_first_run_guide(self) -> None:
        QuickGuideDialog(self).exec()
        self.config.set("guide_seen", True)
        self.config.save()
        # RICHIESTA: "non si può creare una guida interattiva al primo
        # avvio?" -> "sarebbe figo!" — subito dopo la guida testuale
        # (che resta, serve anche per l'accettazione dei Termini e
        # Condizioni), parte anche un tour "a riflettore" che mostra
        # DAL VIVO i controlli veri della finestra, uno alla volta.
        QTimer.singleShot(300, self._start_onboarding_tour)

    def _start_onboarding_tour(self) -> None:
        """Costruisce ed avvia il tour interattivo sui controlli veri
        della finestra principale. get_target e' una funzione (non il
        widget direttamente) cosi' la posizione viene letta SUL
        MOMENTO in cui ogni passo viene mostrato, sempre aggiornata
        anche se nel frattempo la finestra e' stata ridimensionata.
        Richiamabile anche a mano da Impostazioni > Info ("Tour
        interattivo"), non solo al primissimo avvio."""
        steps = [
            TourStep(
                lambda: self.bottom_bar.btn_open,
                "Apri una cartella",
                "Si parte da qui: apri la cartella con le tue foto, "
                "video, documenti (o quasi qualunque altro formato).",
            ),
            TourStep(
                lambda: self.preview_stack,
                "Anteprima",
                "I file compaiono qui uno alla volta. Scorri con le "
                "frecce ◀ ▶ della barra in basso (o con la tastiera).",
            ),
            TourStep(
                lambda: self.folder_panel,
                "Cartelle di destinazione",
                "Clicca una cartella (o premi il suo numero sulla "
                "tastiera) per spostarci subito il file che stai "
                "guardando. Il tasto ✏ permette di riordinarle o "
                "rinumerarle trascinandole.",
            ),
            TourStep(
                lambda: self.add_folder_btn,
                "Aggiungi cartelle",
                "Da qui aggiungi nuove cartelle di destinazione. Puoi "
                "anche trascinarne una direttamente da Esplora risorse.",
            ),
            TourStep(
                lambda: self.bottom_bar.btn_delete,
                "Elimina",
                "Sposta il file corrente nel Cestino interno di TUF: "
                "resta recuperabile con Undo finché non chiudi il "
                "programma.",
            ),
            TourStep(
                lambda: self.bottom_bar.btn_undo,
                "Annulla (Undo)",
                "Se sposti o elimini per sbaglio, questo tasto annulla "
                "l'ultima azione.",
            ),
            TourStep(
                lambda: self.bottom_bar.mic_button,
                "Comando vocale (facoltativo)",
                "Puoi anche dire \"avanti\", \"indietro\", \"cestino\" o "
                "il nome di una cartella per navigare senza mouse. Del "
                "tutto facoltativo: funziona identico anche senza.",
            ),
            TourStep(
                lambda: self.settings_btn,
                "Impostazioni",
                "Qui trovi i formati riconosciuti, le scorciatoie "
                "personalizzabili, questa guida e il tour, e uno spazio "
                "per lasciare consigli o segnalare formati mancanti.",
            ),
        ]
        self._onboarding_tour = OnboardingTour(steps, self.centralWidget())
        self._onboarding_tour.finished.connect(self._on_onboarding_tour_finished)
        self._onboarding_tour.start()

    def _on_onboarding_tour_finished(self) -> None:
        self._onboarding_tour = None

    # ------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 0)
        root.setSpacing(0)

        # RICHIESTA (v0.32): "le impostazioni mettile sulla stessa riga
        # lato destro del logo in alto a sinistra" — prima stava nel
        # pannello cartelle vicino a modifica/cestino (v0.30). Il
        # pulsante viene creato qui e passato a BrandedHeader come
        # corner_widget, cosi' finisce nella stessa riga del logo,
        # allineato al bordo destro.
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setToolTip("Impostazioni")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; border: none;"
            " border-radius: 14px; font-size: 14px; }"
            "QPushButton:hover { background-color: #444; color: #fff; }"
        )
        self.settings_btn.clicked.connect(self._open_settings)

        # RICHIESTA: avviso aggiornamento disponibile — pulsante
        # nascosto di default (vedi _on_update_available), compare
        # solo se core/update_check.py trova una versione piu' recente
        # su GitHub. Nella stessa riga del logo e delle impostazioni,
        # cosi' resta visibile ma non invadente.
        self.update_btn = QPushButton("⬆ Aggiornamento disponibile")
        self.update_btn.setVisible(False)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: #fff; border: none;"
            " border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.update_btn.clicked.connect(self._open_update_page)

        header_corner = QWidget()
        header_corner_layout = QHBoxLayout(header_corner)
        header_corner_layout.setContentsMargins(0, 0, 0, 0)
        header_corner_layout.setSpacing(8)
        header_corner_layout.addWidget(self.update_btn)
        header_corner_layout.addWidget(self.settings_btn)
        root.addWidget(BrandedHeader(corner_widget=header_corner))

        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter, stretch=1)

        # ---------------- sinistra: preview + filtri/ricerca ----------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)

        self.preview = PreviewWidget()

        # Lo stack permette di mostrare, nello STESSO riquadro, o
        # l'anteprima foto/video normale (indice 0) o il pannello di
        # revisione duplicati (indice 1, creato al volo quando serve,
        # vedi _on_duplicates_found) senza aprire una finestra separata.
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.preview)
        self.duplicate_panel: DuplicateReviewPanel | None = None
        left_layout.addWidget(self.preview_stack, stretch=1)

        # percorso sorgente + pulsante "apri in esplora risorse"
        source_row = QHBoxLayout()
        self.source_path_label = QLabel("Nessuna cartella aperta")
        self.source_path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.open_explorer_btn = QPushButton("📂 Apri in Esplora risorse")
        self.open_explorer_btn.setEnabled(False)
        self.open_explorer_btn.clicked.connect(self._open_source_in_explorer)
        source_row.addWidget(self.source_path_label, stretch=1)
        source_row.addWidget(self.open_explorer_btn)
        left_layout.addLayout(source_row)

        bottom_left = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Cerca per nome file...")
        self.search_box.textChanged.connect(self._apply_filter)

        # RICHIESTA: "la tendina è secondaria e si basa su quello che
        # è selezionato nelle impostazioni" — costruita subito con le
        # estensioni gia' abilitate in config (quelle scelte in
        # Impostazioni > Formati nella sessione precedente), non con
        # TUTTE le estensioni esistenti come prima.
        self.type_filter = MultiTypeFilter(set(self.config.get("enabled_extensions", list(SUPPORTED_EXT))))
        self.type_filter.selection_changed.connect(self._apply_filter)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Nome", "Dimensione", "Data"])
        self.sort_combo.currentIndexChanged.connect(self._apply_sort)

        bottom_left.addWidget(QLabel("Filtri:"))
        bottom_left.addWidget(self.type_filter)
        bottom_left.addWidget(self.sort_combo)
        bottom_left.addWidget(self.search_box, stretch=1)
        left_layout.addLayout(bottom_left)

        self.file_info_label = QLabel("")
        self.file_info_label.setStyleSheet("color: #bbb; font-size: 12px; padding: 2px 0;")
        # BUG RISOLTO ("non posso copiare il nome del file"): di default
        # un QLabel non permette la selezione del testo col mouse. Cosi'
        # si puo' selezionare (anche solo il nome) e copiare con
        # Ctrl+C o dal menu del tasto destro, come un campo di testo.
        self.file_info_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.file_info_label.setCursor(Qt.IBeamCursor)
        left_layout.addWidget(self.file_info_label)

        # ---------------- destra: solo cartelle ----------------
        self.folder_panel = FolderPanel()
        self.folder_panel.folder_activated.connect(self._on_folder_activated)
        self.folder_panel.folders_changed.connect(self._on_folders_changed)
        self.folder_panel.delete_requested.connect(self._delete_current)
        self.folder_panel.size_level_changed.connect(
            lambda level: self.config.set("folder_size_level", level)
        )

        self.add_folder_btn = QPushButton("+ Aggiungi cartella di destinazione")
        self.add_folder_btn.clicked.connect(self._add_destination_folder)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.addWidget(self.folder_panel, stretch=1)
        right_layout.addWidget(self.add_folder_btn)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        # BUG RISOLTO ("la finestra si sposta/si rompe" aprendo i
        # duplicati o comunque dopo un dialogo modale sopra la finestra
        # principale): setStretchFactor da solo NON imposta le
        # dimensioni iniziali del divisore (influenza solo come si
        # ridistribuisce lo spazio EXTRA quando la finestra viene
        # ridimensionata), quindi senza uno stato salvato il divisore
        # poteva assegnare al pannello destro (cartelle) una larghezza
        # arbitraria o perfino zero, che restava "collassato" — a
        # quel punto sembrava che tutta la finestra si fosse spostata,
        # perche' il riquadro sinistro si allargava a coprire tutto.
        # Impostare esplicitamente le dimensioni iniziali e vietare il
        # collasso a zero su entrambi i lati risolve il problema alla
        # radice, indipendentemente da cosa lo scateni.
        self.splitter.setSizes([1050, 350])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        right.setMinimumWidth(220)

        # ---------------- basso: barra comandi ----------------
        self.bottom_bar = BottomBar()
        self.bottom_bar.open_folder_clicked.connect(self._open_source_folder)
        self.bottom_bar.back_clicked.connect(self._go_back)
        self.bottom_bar.next_clicked.connect(self._go_next)
        self.bottom_bar.delete_clicked.connect(self._delete_current)
        self.bottom_bar.undo_clicked.connect(self._undo)
        self.bottom_bar.voice_clicked.connect(self._start_voice_command)
        root.addWidget(self.bottom_bar)


        # ---------------- overlay conferma eliminazione (al centro, sopra tutto) ----------------
        self.delete_overlay = DeleteConfirmOverlay(central)
        self.delete_overlay.confirmed.connect(self._on_delete_confirmed)
        self.delete_overlay.cancelled.connect(self._on_delete_cancelled)

        # overlay con barra di progresso mostrato mentre i duplicati
        # selezionati vengono spostati nel cestino interno in background
        self.delete_progress_overlay = DeleteProgressOverlay(central)

    def _install_shortcuts(self) -> None:
        # I tasti numero 1-9 (cartelle) e lo 0 restano SEMPRE fissi:
        # sono legati al numero stesso di ogni cartella (digitare "3"
        # sposta sempre nella cartella numero 3), quindi non avrebbe
        # senso renderli rimappabili singolarmente da Impostazioni
        # (vedi anche il commento su DEFAULT_SHORTCUTS in config.py).
        # '0' da solo elimina; '\' (rimappabile, vedi sotto) arma la
        # modalita' "doppia cifra" per raggiungere cartelle 10 in su:
        # i DUE tasti numero successivi vengono allora combinati in un
        # solo numero invece di spostare/eliminare subito (vedi
        # _on_digit_key).
        for n in range(0, 10):
            sc = QShortcut(QKeySequence(str(n)), self)
            sc.activated.connect(lambda num=n: self._on_digit_key(num))

        # RICHIESTA: "sarebbe carico che il cestino, il comando doppio
        # numero e tutte le shortcut create possano essere
        # personalizzabili in impostazioni" — tutto il resto (tasto
        # Canc, prefisso doppia cifra, undo, comando vocale, zoom,
        # avanti/indietro, play/pausa) e' costruito da config invece
        # che con QKeySequence fisse, cosi' Impostazioni > Scorciatoie
        # puo' cambiarlo (vedi _install_custom_shortcuts, richiamato di
        # nuovo da _open_settings dopo un salvataggio).
        self._custom_shortcuts: dict[str, QShortcut] = {}
        self._install_custom_shortcuts()

    def _shortcut_handlers(self) -> dict:
        return {
            "delete": self._delete_current,
            "double_digit_prefix": self._start_double_digit_shortcut,
            "undo": self._undo,
            "voice_command": self._start_voice_command,
            "reset_zoom": self.preview.reset_zoom,
            "next": self._go_next,
            "back": self._go_back,
            "play_pause": self._on_space_pressed,
        }

    def _install_custom_shortcuts(self) -> None:
        """Costruisce (o ricostruisce, dopo un salvataggio in
        Impostazioni > Scorciatoie) tutte le scorciatoie rimappabili a
        partire da quanto salvato in config, cosi' una modifica si
        applica subito, senza dover riavviare TUF."""
        for sc in self._custom_shortcuts.values():
            sc.setEnabled(False)
            sc.deleteLater()
        self._custom_shortcuts = {}

        handlers = self._shortcut_handlers()
        for action_id, key_str in self.config.get_shortcuts().items():
            handler = handlers.get(action_id)
            if not key_str or handler is None:
                continue
            sc = QShortcut(QKeySequence(key_str), self)
            sc.activated.connect(handler)
            self._custom_shortcuts[action_id] = sc

    def _on_space_pressed(self) -> None:
        """La barra spaziatrice mette in play/pausa il video quando ne
        e' aperto uno, altrimenti non fa nulla (il comando vocale ora
        si attiva con la lettera C)."""
        if self.preview.is_showing_video():
            self.preview.toggle_play_pause()

    def _start_double_digit_shortcut(self) -> None:
        self._double_digit_pending = True
        self._double_digit_first = None
        self.bottom_bar.set_status(
            "Scorciatoia a due cifre: digita il numero della cartella "
            "(es. 1 poi 0 per la cartella 10)..."
        )
        self._double_digit_timer.start(2500)

    def _on_double_digit_timeout(self) -> None:
        if self._double_digit_pending:
            self._double_digit_pending = False
            self._double_digit_first = None
            self.bottom_bar.set_status("Scorciatoia a due cifre annullata (tempo scaduto).")

    def _on_digit_key(self, digit: int) -> None:
        """Punto unico da cui passano TUTTI i tasti numero (0-9),
        sia in modalita' normale (0 = elimina, 1-9 = sposta nella
        cartella con quel numero) sia durante una scorciatoia a due
        cifre armata con '\' (vedi _start_double_digit_shortcut)."""
        if self._double_digit_pending:
            self._double_digit_timer.stop()
            if self._double_digit_first is None:
                self._double_digit_first = digit
                self.bottom_bar.set_status(
                    f"Scorciatoia a due cifre: {digit}… digita la seconda cifra"
                )
                self._double_digit_timer.start(2500)
            else:
                number = self._double_digit_first * 10 + digit
                self._double_digit_pending = False
                self._double_digit_first = None
                self._move_current_to_number(number)
            return

        if digit == 0:
            self._delete_current()
        else:
            self._move_current_to_number(digit)

    # ------------------------------------------------------ apertura
    def _open_source_folder(self) -> None:
        # RICHIESTA (menu Impostazioni > Formati, v0.30): prima qui si
        # apriva un dialogo "Cosa vuoi importare?" ad ogni cartella,
        # con scelta solo per CATEGORIA (Foto/Video/PDF/...). Ora la
        # scelta e' per singola ESTENSIONE, fatta una volta sola in
        # Impostazioni, e i formati flaggati li' sono quelli usati
        # direttamente aprendo una cartella — niente piu' dialogo in
        # mezzo ad ogni apertura.
        start_dir = self.config.get("last_source_folder", "") or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Seleziona cartella", start_dir)
        if not folder:
            return
        self.config.set("last_source_folder", folder)

        allowed_ext = set(self.config.get("enabled_extensions", list(SUPPORTED_EXT)))
        if not allowed_ext:
            QMessageBox.information(
                self, "Nessun formato selezionato",
                "Nessun formato di file e' abilitato. Vai in Impostazioni → "
                "Formati e seleziona almeno un tipo di file da riconoscere."
            )
            return

        self.current_source_folder = folder
        self.source_path_label.setText(folder)
        self.open_explorer_btn.setEnabled(True)
        self._start_scan(folder, allowed_ext)

    def _open_source_in_explorer(self) -> None:
        """BUG RISOLTO ("non riesco a risalire ai file anche se schiaccio
        apri in Esplora risorse"): la scansione e' ricorsiva (vedi
        scanner.py, rglob), quindi il file mostrato in anteprima puo'
        stare diversi livelli di sottocartelle sotto la cartella
        sorgente scelta all'inizio. Aprire sempre e solo quella radice
        non aiuta a trovare il file vero. Ora, se c'e' un file
        attualmente in anteprima, apriamo Esplora risorse GIA'
        posizionato in quella sottocartella con il file selezionato
        (comando nativo Windows "explorer /select,"); solo se non c'e'
        nessun file mostrato si ricade sull'apertura della sola
        cartella radice."""
        item = None
        if 0 <= self.current_index < len(self.filtered_items):
            item = self.filtered_items[self.current_index]

        if item is not None and sys.platform == "win32":
            try:
                subprocess.Popen(["explorer", "/select,", str(Path(item.path))])
                return
            except OSError:
                pass  # ricade sull'apertura della cartella sorgente qui sotto

        if item is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(item.path).parent)))
        elif self.current_source_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_source_folder))

    def _start_scan(self, folder: str, allowed_ext: set[str]) -> None:
        self.bottom_bar.set_status(f"Scansione di {folder} in corso...")
        # RICHIESTA: "crea una barra di loading finche' i comandi non
        # sono tutti fluidi... cosi' l'utente ha idea di quando poter
        # iniziare a lavorare senza problemi" — non si conosce il
        # totale dei file in anticipo (si scoprono mano a mano durante
        # la scansione), quindi barra indeterminata ("a onda").
        self.bottom_bar.show_progress_indeterminate()
        self._set_list_controls_enabled(False)
        self.scanner = FileScanner(folder, allowed_ext=allowed_ext)
        self.scanner.progress.connect(self._on_scan_progress)
        self.scanner.finished_scan.connect(self._on_scan_finished)
        self.scanner.start()

    def _on_scan_progress(self, count: int) -> None:
        self.bottom_bar.set_status(f"File trovati finora: {count}")

    def _on_scan_finished(self, items: list[FileItem]) -> None:
        self.bottom_bar.hide_progress()
        self._set_list_controls_enabled(True)
        self.all_items = items
        self.bottom_bar.set_status(f"Scansione completata: {len(items)} file supportati.")
        if not items:
            QMessageBox.information(self, "Nessun file",
                                     "Nessun file supportato trovato in questa cartella.")
            return
        dlg = DashboardDialog(items, self)
        dlg.exec()
        idx_map = {"Nome": 0, "Dimensione": 1, "Data": 2}
        self.sort_combo.setCurrentIndex(idx_map.get(dlg.sort_mode(), 0))
        if dlg.chosen_action == DashboardDialog.ACTION_DUPLICATES:
            self._start_duplicate_scan()
        else:
            self._apply_filter()

    # ---------------------------------------------------- filtro/sort
    def _apply_filter(self) -> None:
        text = self.search_box.text().strip().lower()
        # RICHIESTA: "nella tendina in basso a sinistra mi da solo la
        # voce audio, non tutti i formati, mettili anche li'" — il
        # filtro ora lavora per singola ESTENSIONE (es. .mp3), non piu'
        # solo per categoria intera, cosi' si puo' scegliere anche
        # solo alcuni formati dentro una categoria (vedi
        # multi_filter.py). Spuntare l'intera categoria equivale a
        # prima (tutte le sue estensioni spuntate insieme).
        selected_extensions = self.type_filter.selected_extensions()

        result = self.all_items
        if not self.type_filter.is_all_selected():
            result = [it for it in result if it.extension in selected_extensions]
        if text:
            result = [it for it in result if text in Path(it.path).name.lower()]

        self.filtered_items = result
        self._apply_sort(keep_index=False)

    def _apply_sort(self, *_, keep_index: bool = True) -> None:
        mode = self.sort_combo.currentText()
        if mode == "Dimensione":
            self.filtered_items.sort(key=lambda it: it.size, reverse=True)
        elif mode == "Data":
            self.filtered_items.sort(key=lambda it: it.mtime, reverse=True)
        else:
            self.filtered_items.sort(key=lambda it: Path(it.path).name.lower())

        if not keep_index or self.current_index < 0:
            self.current_index = 0 if self.filtered_items else -1
        self._show_current()

    def _select_item_by_path(self, path: str) -> None:
        """Porta il visualizzatore sull'elemento con questo path, se
        presente nella lista filtrata corrente (usato dopo un undo)."""
        for i, it in enumerate(self.filtered_items):
            if it.path == path:
                self.current_index = i
                break
        self._show_current()

    # ----------------------------------------------------- navigazione
    def _show_current(self) -> None:
        if 0 <= self.current_index < len(self.filtered_items):
            item = self.filtered_items[self.current_index]
            self.preview.show_item(item)
            self.file_info_label.setText(PreviewWidget.format_file_info(item))
            if self.current_index + 1 < len(self.filtered_items):
                self.preview.preload(self.filtered_items[self.current_index + 1])
        else:
            self.preview.show_item(None)
            self.file_info_label.setText("")
        self.preview.set_counter(
            self.current_index + 1 if self.current_index >= 0 else 0,
            len(self.filtered_items),
        )

    def _go_next(self) -> None:
        if self.pending_delete_item is not None:
            self._on_delete_cancelled()
            return
        if self.current_index + 1 < len(self.filtered_items):
            self.current_index += 1
            self._show_current()

    def _go_back(self) -> None:
        if self.pending_delete_item is not None:
            self._on_delete_cancelled()
            return
        if self.current_index > 0:
            self.current_index -= 1
            self._show_current()

    # -------------------------------------------------- spostamento file
    def _on_folder_activated(self, path: str) -> None:
        self._move_current_to_path(path)

    def _move_current_to_number(self, number: int) -> None:
        target = self.folder_panel.folder_for_shortcut(str(number))
        if target:
            self._move_current_to_path(target.path)
        else:
            self.bottom_bar.set_status(f"Nessuna cartella con numero {number}.")

    def _play_move_animation(self, item: FileItem, dest_dir: str) -> None:
        """Fa 'volare' una miniatura del file verso la riga della
        cartella di destinazione, per un feedback visivo immediato."""
        row = self.folder_panel.get_row_widget(dest_dir)
        if row is None:
            return
        pix = None
        if item.category == FileCategory.IMAGE:
            pix = self.preview._cache.get(item.path) or self.preview._base_pixmap
        start_global = self.preview.mapToGlobal(self.preview.rect().center())
        end_global = row.mapToGlobal(row.rect().center())
        animate_file_to_folder(self.centralWidget(), pix, start_global, end_global)

    def _move_current_to_path(self, dest_dir: str) -> None:
        if not (0 <= self.current_index < len(self.filtered_items)):
            return
        item = self.filtered_items[self.current_index]
        src = Path(item.path)
        dest = Path(dest_dir) / src.name

        self.preview.stop_video()  # rilascia il file se e' un video in riproduzione
        self._play_move_animation(item, dest_dir)

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = dest.with_stem(dest.stem + "_dup")
            shutil.move(str(src), str(dest))
        except OSError as e:
            QMessageBox.warning(self, "Errore spostamento", f"Impossibile spostare il file:\n{e}")
            return

        self.undo_stack.append(MoveAction(str(src), str(dest), item))
        self.bottom_bar.set_undo_enabled(True)
        self.folder_panel.refresh_counts()
        self.folder_panel.highlight_last_used(dest_dir)

        # rimuovi dalla lista e mostra il prossimo, senza tempi morti
        del self.filtered_items[self.current_index]
        if self.current_index >= len(self.filtered_items):
            self.current_index = len(self.filtered_items) - 1
        self.all_items = [it for it in self.all_items if it.path != item.path]
        self._show_current()

    def _undo(self) -> None:
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        try:
            Path(action.dst).rename(action.src)
        except OSError as e:
            QMessageBox.warning(self, "Errore undo", f"Impossibile annullare:\n{e}")
            return
        self.bottom_bar.set_undo_enabled(bool(self.undo_stack))
        self.folder_panel.refresh_counts()
        self.folder_panel.highlight_last_used(None)

        # rimette il file nella lista e ci torna sopra, cosi' ricompare
        # subito nel visualizzatore invece di andare perso
        self.all_items.append(action.item)
        self._apply_filter()
        self._select_item_by_path(action.item.path)

    # ----------------------------------------------------- comando vocale
    def _start_voice_command(self) -> None:
        # se e' gia' attivo, questo stesso tasto lo disattiva del tutto
        if self.voice_worker is not None and self.voice_worker.isRunning():
            self.bottom_bar.set_status("Ascolto vocale disattivato.")
            self.voice_worker.stop()
            return

        self.bottom_bar.set_listening(True)
        self.bottom_bar.set_status(
            "🎤 Ascolto attivo: di' un numero o il nome di una cartella "
            "(premi di nuovo C per disattivare)"
        )
        self.voice_worker = VoiceWorker()
        self.voice_worker.recognized.connect(self._on_voice_recognized)
        self.voice_worker.error.connect(self._on_voice_error)
        self.voice_worker.phrase_started.connect(self._on_voice_phrase_started)
        self.voice_worker.audio_level.connect(self.bottom_bar.push_mic_level)
        self.voice_worker.finished.connect(lambda: self.bottom_bar.set_listening(False))
        self.voice_worker.finished.connect(self.bottom_bar.reset_mic_levels)
        self.voice_worker.start()

    def _on_voice_recognized(self, text: str) -> None:
        # se e' in sospeso una richiesta di conferma eliminazione,
        # questa frase viene interpretata come si'/no, non come comando
        if self.pending_delete_item is not None:
            answer = parse_yes_no(text)
            if answer is True:
                self._on_delete_confirmed()
            elif answer is False:
                self._on_delete_cancelled()
            else:
                self.bottom_bar.set_status(
                    f'Non ho capito. Eliminare "{self.pending_delete_item.name}"? '
                    'Di\' "sì"/"conferma" o "no"/"annulla"'
                )
            return

        if not (0 <= self.current_index < len(self.filtered_items)):
            self.bottom_bar.set_status(f'Comando vocale: "{text}" → nessun file da spostare al momento')
            return

        folder_names = {t.name.lower(): t.number for t in self.folder_panel.get_folders()}
        action, number = parse_voice_command(text, folder_names)

        if action == "delete":
            # RICHIESTA: "quando c'è il riconoscimento vocale se
            # elimino un file non deve chiedere conferma" — a
            # differenza di tastiera/mouse/cestino (che mostrano
            # sempre la finestra di conferma), il comando vocale
            # elimina SUBITO, senza fermarsi ad aspettare un secondo
            # "sì" pronunciato. Resta comunque recuperabile con Ctrl+Z/
            # comando vocale "annulla" esattamente come ogni altra
            # eliminazione (vedi _delete_item, che sposta nel cestino
            # interno di TUF, mai una cancellazione definitiva sul
            # colpo). Corregge anche il caso segnalato "lo 0 ovvero
            # cestino non lo fa più": prima il comando vocale faceva
            # comparire una richiesta di conferma che si aspettava un
            # SECONDO comando vocale ("sì"/"conferma") per completarsi
            # — se non arrivava (o non veniva capito), sembrava che
            # "elimina"/"cestino"/"0" non facesse piu' nulla.
            item = self.filtered_items[self.current_index]
            self.bottom_bar.set_status(f'Comando vocale: "{text}" → elimino "{item.name}"')
            self._delete_item(item)
        elif action == "undo":
            # RICHIESTA: comando vocale per annullare l'ultima azione,
            # come Ctrl+Z. Riusa la stessa _undo() del tasto e della
            # scorciatoia da tastiera, cosi' il comportamento (incluso
            # il far ricomparire il file nel visualizzatore) resta
            # identico in tutti e tre i modi di attivarlo.
            if self.undo_stack:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → annullo l\'ultima azione')
                self._undo()
            else:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → niente da annullare')
        elif action == "next":
            # RICHIESTA: "avanti"/"indietro" a voce, come le frecce
            # della tastiera. Riusa _go_next/_go_back, quindi si
            # comporta esattamente come premere la freccia (compreso
            # l'annullare una richiesta di eliminazione in sospeso).
            if self.current_index + 1 < len(self.filtered_items):
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → file successivo')
                self._go_next()
            else:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → sei gia\' all\'ultimo file')
        elif action == "prev":
            if self.current_index > 0:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → file precedente')
                self._go_back()
            else:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → sei gia\' al primo file')
        elif action == "move" and number is not None:
            target = self.folder_panel.folder_for_shortcut(str(number))
            if target:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → sposto in "{target.name}"')
                self._move_current_to_path(target.path)
            else:
                self.bottom_bar.set_status(f'Comando vocale: "{text}" → nessuna cartella con numero {number}')
        else:
            self.bottom_bar.set_status(f'Comando vocale non riconosciuto: "{text}" — resto in ascolto')

    def _on_voice_phrase_started(self) -> None:
        self.bottom_bar.set_status("🎙️ Ti sento, parla pure...")

    def _on_voice_error(self, message: str) -> None:
        self.bottom_bar.set_status(message)

    def _delete_current(self) -> None:
        """Eliminazione richiesta da tastiera/mouse/cestino: mostra la
        finestra di conferma centrale (funziona anche a voce). Se la
        finestra e' gia' aperta, premere di nuovo Canc/Elimina la
        annulla invece di riproporla."""
        if self.pending_delete_item is not None:
            self._on_delete_cancelled()
            return
        if not (0 <= self.current_index < len(self.filtered_items)):
            return
        item = self.filtered_items[self.current_index]
        self._request_delete_confirmation(item)

    def _request_delete_confirmation(self, item: FileItem) -> None:
        """Mostra subito, al centro, la richiesta di conferma per
        eliminare `item`. Funziona sia con mouse/tastiera (pulsanti
        nell'overlay) sia a voce ("sì"/"conferma" o "no"/"annulla")."""
        self.preview.pause_for_dialog()  # altrimenti un video in riproduzione resta sopra l'overlay
        self.pending_delete_item = item
        self.delete_overlay.show_for(item.name)
        self.bottom_bar.set_status(
            f'Eliminare "{item.name}"? Di\' "sì"/"conferma" o "no"/"annulla", oppure usa i pulsanti'
        )

    def _on_delete_confirmed(self) -> None:
        item = self.pending_delete_item
        if item is None:
            return
        self.pending_delete_item = None
        self.delete_overlay.hide_overlay()
        self.bottom_bar.set_status(f'Elimino "{item.name}"...')
        self._delete_item(item)

    def _on_delete_cancelled(self) -> None:
        item = self.pending_delete_item
        self.pending_delete_item = None
        self.delete_overlay.hide_overlay()
        if item is not None:
            self.bottom_bar.set_status(f'Eliminazione di "{item.name}" annullata.')

    def _delete_item(self, item: FileItem) -> None:
        """Elimina il file spostandolo nel cestino interno di TUF
        (recuperabile con Ctrl+Z, esattamente come uno spostamento in
        cartella). Nessuna ulteriore conferma qui: va chiamato solo
        dopo che la conferma, vocale o dall'overlay, e' gia' stata
        ottenuta.

        BUG RISOLTO ("il programma si blocca" eliminando un file dalla
        vista classica): lo spostamento (shutil.move) avveniva qui in
        modo SINCRONO sul thread dell'interfaccia. Con un file grande
        (es. un video) o su un disco lento/esterno/di rete, o con un
        antivirus che scansiona il file mentre viene spostato, questo
        poteva richiedere diversi secondi durante i quali l'intera
        finestra restava "non risponde" — esattamente lo stesso
        problema gia' risolto per "Elimina i selezionati" nella
        finestra duplicati (vedi _delete_duplicate_paths piu' sotto).
        Ora anche qui lo spostamento avviene in un thread separato
        (riusando DuplicateDeleteWorker, gia' pensato per una lista di
        file: una lista di un solo elemento funziona allo stesso modo),
        con la stessa barra di progresso."""
        self.preview.stop_video()  # rilascia il file se e' un video in riproduzione
        self._pending_single_delete_item = item
        self.bottom_bar.set_status(f'Elimino "{item.name}"...')

        delete_items = [DeleteItem(item.path, item.size)]
        self.delete_progress_overlay.show_for(len(delete_items))
        self._single_delete_worker = DuplicateDeleteWorker(delete_items, trash_dir())
        self._single_delete_worker.progress.connect(self._on_delete_progress)
        self._single_delete_worker.finished_delete.connect(self._on_single_delete_finished)
        self._single_delete_worker.start()

    def _on_single_delete_finished(self, moved: list[tuple[str, str]], failed: list[str]) -> None:
        self.delete_progress_overlay.hide_overlay()
        item = self._pending_single_delete_item
        self._pending_single_delete_item = None
        self._single_delete_worker = None

        if moved:
            src, dest = moved[0]
            if item is not None:
                self.undo_stack.append(MoveAction(src, dest, item))
                self.bottom_bar.set_undo_enabled(True)
                if item in self.filtered_items:
                    idx = self.filtered_items.index(item)
                    del self.filtered_items[idx]
                    if self.current_index >= len(self.filtered_items):
                        self.current_index = len(self.filtered_items) - 1
                self.all_items = [it for it in self.all_items if it.path != item.path]
            self.folder_panel.refresh_counts()
            self.folder_panel.set_trash_highlighted(True)
            self.bottom_bar.set_status(f'Eliminato "{item.name if item is not None else Path(src).name}".')
        elif failed:
            name = item.name if item is not None else Path(failed[0]).name
            QMessageBox.warning(self, "Errore", f"Impossibile eliminare il file:\n{name}")
            self.bottom_bar.set_status(f'Eliminazione di "{name}" fallita.')

        self._show_current()

    # -------------------------------------------------------- cartelle
    def _add_destination_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Scegli cartella di destinazione")
        if not folder:
            return
        existing_numbers = [t.number for t in self.folder_panel.get_folders()]
        next_number = max(existing_numbers, default=0) + 1
        target = FolderTarget(number=next_number, name=Path(folder).name, path=folder,
                               shortcut=str(next_number) if next_number < 10 else "")
        self.folder_panel.add_folder(target)
        self.folder_panel.refresh_counts()

    def _on_folders_changed(self, targets: list[FolderTarget]) -> None:
        self.config.set_folders(targets)

    # -------------------------------------------------------- duplicati
    def _start_duplicate_scan(self) -> None:
        if not self.all_items:
            return

        # RICHIESTA: "i duplicati devono seguire la logica dei file
        # scelti, adesso mi importa tutto nella sezione duplicati
        # senza guardare che tipo di file ho selezionato" + "farei
        # anche una finestra con scritto importa tutto oppure importa
        # solo file selezionati". Prima la scansione usava SEMPRE
        # tutti i file caricati, ignorando il filtro tipi/formati e la
        # ricerca per nome attivi. Ora, se il filtro sta davvero
        # nascondendo qualcosa (altrimenti non c'e' nulla da
        # scegliere), chiede esplicitamente quale insieme usare — cosi'
        # la scelta e' sempre chiara, invece di dipendere in silenzio
        # da cosa capitava di essere filtrato in quel momento.
        # BUG SEGNALATO ("non mi ha chiesto quando ho importato i
        # duplicati se volessi tutti o solo quelli selezionati"): al
        # PRIMO scan (chiamato dalla finestra Riepilogo subito dopo
        # aver aperto una cartella) _apply_filter() non era ancora
        # stata chiamata nemmeno una volta, quindi filtered_items era
        # ancora vuoto/non sincronizzato — il controllo qui sotto
        # vedeva "nessun filtro attivo" per mancanza di dati, non
        # perche' non ce ne fosse davvero uno. Ricalcolarlo QUI,
        # appena prima del controllo, garantisce che rispecchi sempre
        # lo stato vero e attuale del filtro.
        self._apply_filter()
        items_to_scan = self.all_items
        if self.filtered_items and len(self.filtered_items) != len(self.all_items):
            box = QMessageBox(self)
            box.setWindowTitle("Cerca duplicati")
            box.setIcon(QMessageBox.Question)
            box.setText(
                "Hai un filtro attivo (tipi di file e/o ricerca).\n\n"
                "Cercare i duplicati in TUTTI i file caricati, oppure solo "
                "tra quelli attualmente selezionati dal filtro?"
            )
            all_btn = box.addButton(f"Tutti i file ({len(self.all_items)})", QMessageBox.AcceptRole)
            filtered_btn = box.addButton(f"Solo i selezionati ({len(self.filtered_items)})", QMessageBox.AcceptRole)
            box.addButton("Annulla", QMessageBox.RejectRole)
            box.setDefaultButton(filtered_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is all_btn:
                items_to_scan = self.all_items
            elif clicked is filtered_btn:
                items_to_scan = self.filtered_items
            else:
                return  # annullato

        if not items_to_scan:
            return

        self.bottom_bar.set_status("Ricerca duplicati in corso...")
        # La scansione lavora in un thread separato, ma resta comunque
        # lavoro pesante per la CPU (hash di centinaia/migliaia di
        # file): se nel frattempo si interagisce con la lista (es. si
        # cambia l'ordinamento), Python deve dividere il tempo di CPU
        # tra i due thread e l'interfaccia puo' sembrare bloccata per
        # diversi secondi (non e' un crash: si sblocca da sola a fine
        # scansione). Per evitarlo, i controlli che rifanno lavoro
        # pesante sulla lista vengono disattivati finche' la scansione
        # non e' finita.
        self._set_list_controls_enabled(False)
        # RICHIESTA: barra di caricamento anche qui — a differenza
        # della scansione cartella, qui il TOTALE si conosce subito
        # (items_to_scan), quindi barra determinata con percentuale
        # reale invece che "a onda".
        self.bottom_bar.set_progress(0, len(items_to_scan))
        self.dup_finder = DuplicateFinder(items_to_scan)
        self.dup_finder.progress.connect(
            lambda done, total, name, eta: (
                self.bottom_bar.set_status(
                    f"Controllo duplicati: {done}/{total} — {name}"
                    + (f"  ({eta})" if eta else "")
                ),
                self.bottom_bar.set_progress(done, total),
                self._enforce_splitter_min_sizes(),
            )
        )
        self.dup_finder.finished_scan.connect(self._on_duplicates_found)
        self.dup_finder.start()

    def _set_list_controls_enabled(self, enabled: bool) -> None:
        # RICHIESTA: "evitiamo di far lavorare il programma sotto
        # stress nel momento del caricamento" — durante una scansione
        # (cartella o duplicati) si disattivano anche i comandi che
        # potrebbero far partire ALTRO lavoro pesante in parallelo
        # (aprire un'altra cartella, riaprire le Impostazioni e
        # cambiare i formati abilitati a meta' scansione), non solo
        # ordinamento/filtro/ricerca come prima.
        #
        # SEGNALATO: "dopo che la barra aveva finito di caricare avevo
        # difficolta' a navigare... se lavori mentre carica va a
        # rilento, se aspetti che finisca vai piu' veloce" — Avanti/
        # Indietro/Elimina/Undo restavano invece SEMPRE attivi durante
        # una scansione: cliccarli mentre il thread di scansione/hash
        # tiene occupata la CPU poteva sembrare lento o bloccato, dando
        # l'impressione (falsa) che il programma non rispondesse. Ora
        # restano disattivati anche loro finche' il caricamento non e'
        # finito, cosi' la barra di caricamento diventa un segnale
        # chiaro e coerente: se i pulsanti sono spenti, aspetta;
        # appena si riaccendono, si puo' lavorare a piena velocita'.
        self.sort_combo.setEnabled(enabled)
        self.type_filter.setEnabled(enabled)
        self.search_box.setEnabled(enabled)
        self.bottom_bar.btn_open.setEnabled(enabled)
        self.settings_btn.setEnabled(enabled)
        self.bottom_bar.btn_next.setEnabled(enabled)
        self.bottom_bar.btn_back.setEnabled(enabled)
        self.bottom_bar.btn_delete.setEnabled(enabled)
        # Undo ha una sua condizione a parte (attivo solo se c'e'
        # davvero qualcosa da annullare): durante il caricamento va
        # comunque spento come gli altri, ma a fine caricamento va
        # ripristinato in base allo stato REALE di undo_stack, non
        # riacceso a prescindere (altrimenti risulterebbe cliccabile
        # anche senza nulla da annullare).
        if enabled:
            self.bottom_bar.set_undo_enabled(bool(self.undo_stack))
        else:
            self.bottom_bar.btn_undo.setEnabled(False)

    def _on_duplicates_found(self, groups: list[DuplicateGroup]) -> None:
        self.bottom_bar.hide_progress()
        self._set_list_controls_enabled(True)
        self.dup_groups = groups
        if not groups:
            # BUG RISOLTO ("mi dice che ci sono circa 1600 duplicati ma
            # quando schiaccio su Controlla duplicati mi porta
            # automaticamente alla visualizzazione dei file, non alla
            # scelta dei doppi"): il numero "Candidati duplicati" nel
            # Riepilogo cartella (vedi dashboard.py) e' solo una stima
            # RAPIDA basata sulla dimensione del file — file diversi
            # possono benissimo pesare esattamente uguale per puro
            # caso (capita spesso con tanti video/foto simili), senza
            # essere affatto copie reali. Il controllo VERO (qui,
            # basato sul contenuto) puo' quindi trovare zero doppi
            # confermati anche con centinaia di "candidati". Prima, in
            # quel caso, si riapriva SILENZIOSAMENTE lo stesso
            # Riepilogo cartella con lo STESSO numero di candidati (dato
            # che i file sono sempre gli stessi) — sembrava che
            # cliccare "Controlla duplicati" non facesse nulla / desse
            # sempre lo stesso risultato /"portasse ai file". Ora si
            # spiega chiaramente il motivo con un messaggio esplicito,
            # e si torna DIRETTAMENTE alla lista file invece di
            # riproporre lo stesso Riepilogo fuorviante.
            self.bottom_bar.set_status("Nessun duplicato confermato trovato.")
            QMessageBox.information(
                self, "Nessun duplicato trovato",
                "Il Riepilogo cartella indicava alcuni file con la STESSA "
                "dimensione (\"candidati duplicati\"), ma e' solo una stima "
                "rapida: file diversi possono pesare esattamente uguale per "
                "puro caso, senza essere copie vere.\n\n"
                "Il controllo approfondito (basato sul contenuto reale dei "
                "file, non solo sulla dimensione) non ha trovato nessuna "
                "copia confermata in questa cartella."
            )
            self._apply_filter()
            return
        self.bottom_bar.set_status(f"Trovati {len(groups)} gruppi di duplicati.")

        # Il pannello di revisione prende il posto dell'anteprima nello
        # stesso riquadro (vedi self.preview_stack in _build_ui), invece
        # di aprirsi come finestra separata sopra a tutto.
        self.preview.stop_video()
        panel = DuplicateReviewPanel(groups, self)
        panel.confirmed.connect(self._on_duplicate_review_confirmed)
        panel.cancelled.connect(self._on_duplicate_review_cancelled)
        self.duplicate_panel = panel
        self.preview_stack.addWidget(panel)
        self.preview_stack.setCurrentWidget(panel)
        # BUG RISOLTO (v0.24->v0.25, segnalato con screenshot: "la
        # finestra si rimpicciolisce e si sposta"): qui si chiamava
        # anche _clamp_geometry_to_screen() dopo l'apertura dei
        # duplicati. Quel controllo pero' e' proprio la causa del
        # problema, non la cura: durante il ricalcolo del layout Qt puo'
        # riportare temporaneamente una geometria sballata (lo stesso
        # bug di base su Windows), e _clamp_geometry_to_screen scambiava
        # quella lettura per un problema reale, rimpicciolendo e
        # spostando DAVVERO una finestra che in realta' andava benissimo
        # — l'abbiamo gia' visto rompere una finestra massimizzata, e
        # qui rompeva anche una finestra normale. Il vero motivo per cui
        # il pannello cartelle spariva era un altro (vedi
        # _enforce_splitter_min_sizes, v0.24): questa e' la sola
        # protezione che serve davvero qui.
        QTimer.singleShot(0, self._enforce_splitter_min_sizes)

    def _close_duplicate_panel(self) -> None:
        """Torna a mostrare l'anteprima normale e distrugge il pannello
        di revisione (i dati di FileItem restano intatti, viene buttato
        via solo il widget con le miniature gia' caricate)."""
        self.preview_stack.setCurrentWidget(self.preview)
        if self.duplicate_panel is not None:
            self.preview_stack.removeWidget(self.duplicate_panel)
            self.duplicate_panel.deleteLater()
            self.duplicate_panel = None

    def _on_duplicate_review_confirmed(self, to_delete: list[str]) -> None:
        self._close_duplicate_panel()
        if to_delete:
            self._delete_duplicate_paths(to_delete)
        else:
            self.bottom_bar.set_status("Nessun duplicato eliminato.")
            self._apply_filter()

    def _on_duplicate_review_cancelled(self) -> None:
        self._close_duplicate_panel()
        self.bottom_bar.set_status("Controllo duplicati annullato.")
        self._apply_filter()

    def _delete_duplicate_paths(self, paths: list[str]) -> None:
        """Sposta i duplicati nel cestino interno di TUF in un thread
        separato (vedi core/delete_worker.py), mostrando una barra di
        progresso con percentuale, nome del file corrente e GB
        cancellati via via (vedi ui/delete_progress_overlay.py). Prima
        lo spostamento avveniva in modo sincrono sul thread
        dell'interfaccia: con "Cancella tutte le copie" su tante copie
        di grandi dimensioni poteva richiedere tempo, bloccando
        l'interfaccia senza dare nessun feedback nel frattempo."""
        items_by_path = {it.path: it for it in self.all_items}
        delete_items = [DeleteItem(p, items_by_path[p].size) for p in paths if p in items_by_path]
        if not delete_items:
            self._apply_filter()
            return

        self.delete_progress_overlay.show_for(len(delete_items))
        self._delete_worker = DuplicateDeleteWorker(delete_items, trash_dir())
        self._delete_worker.progress.connect(self._on_delete_progress)
        self._delete_worker.finished_delete.connect(self._on_delete_finished)
        self._delete_worker.start()

    def _on_delete_progress(self, done: int, total: int, name: str, gb_done: float, gb_total: float) -> None:
        self.delete_progress_overlay.update_progress(done, total, name, gb_done, gb_total)

    def _on_delete_finished(self, moved: list[tuple[str, str]], failed: list[str]) -> None:
        self.delete_progress_overlay.hide_overlay()
        items_by_path = {it.path: it for it in self.all_items}
        for src, dest in moved:
            item = items_by_path.get(src)
            if item is not None:
                self.undo_stack.append(MoveAction(src, dest, item))
        self.bottom_bar.set_undo_enabled(bool(self.undo_stack))
        self.folder_panel.refresh_counts()
        self.folder_panel.set_trash_highlighted(True)
        moved_paths = {src for src, _ in moved}
        self.all_items = [it for it in self.all_items if it.path not in moved_paths]
        if failed:
            self.bottom_bar.set_status(
                f"Eliminati {len(moved)} file duplicati, {len(failed)} non spostati (forse in uso)."
            )
        else:
            self.bottom_bar.set_status(f"Eliminati {len(moved)} file duplicati.")
        self._apply_filter()

    # -------------------------------------------------------- impostazioni
    def _open_settings(self) -> None:
        # RICHIESTA: "elimina la voce generale nelle impostazioni
        # tanto abbiamo il cursore sulle cartelle" — SettingsDialog non
        # ha piu' una scheda Generale (il cursore dimensione nel
        # pannello cartelle gia' calcola da solo testo/altezza/
        # spaziatura, vedi folder_panel.py _on_slider_changed), quindi
        # non serve piu' passargli/leggergli quei tre valori.
        dlg = SettingsDialog(
            set(self.config.get("enabled_extensions", list(SUPPORTED_EXT))),
            self.config.get_shortcuts(),
            self,
        )
        if dlg.exec():
            new_extensions = sorted(dlg.selected_extensions())
            self.config.set("enabled_extensions", new_extensions)
            # RICHIESTA: "la tendina è secondaria e si basa su quello
            # che è selezionato nelle impostazioni" — la tendina
            # Filtri si ricostruisce subito per riflettere le
            # estensioni appena (dis)abilitate qui.
            self.type_filter.set_enabled_extensions(set(new_extensions))

            # RICHIESTA: scorciatoie personalizzabili — si salvano e si
            # applicano SUBITO, senza dover riavviare TUF.
            self.config.set_shortcuts(dlg.selected_shortcuts())
            self._install_custom_shortcuts()

    # --------------------------------------------------- config load/save
    def _restore_config(self) -> None:
        folders = self.config.get_folders()
        self.folder_panel.set_folders(folders)
        self.folder_panel.refresh_counts()
        self.folder_panel.set_size_level(self.config.get("folder_size_level", DEFAULT_SIZE_LEVEL))

        # BUG RISOLTO (segnalato di nuovo con un log del terminale QUASI
        # IDENTICO a quello di prima, nonostante il fix precedente sul
        # pannello cartelle — quindi non era quella la causa, o non
        # l'unica): la raffica di "QWindowsWindow::setGeometry" compare
        # SEMPRE appena il programma parte, prima di qualunque azione
        # dell'utente, con valori quasi identici run dopo run — troppo
        # deterministico per essere un ciclo scatenato dall'interfaccia.
        # Il sospetto piu' forte a questo punto e' proprio la geometria
        # SALVATA che veniva ripristinata qui sotto (restoreGeometry):
        # se quel valore risulta "scomodo" per Qt su questo specifico
        # monitor/scaling, il programma lo rinegozia ad ogni avvio,
        # sempre allo stesso modo (da cui la somiglianza tra i log).
        # Invece di continuare a inseguire il sintomo, si toglie la
        # causa: la finestra non riparte piu' dalla posizione/dimensione
        # salvata, ma sempre da quella di default (impostata in
        # __init__: resize(1400, 900), posizione decisa da Windows).
        # Si perde il "si riapre dov'era rimasta", ma si guadagna un
        # avvio sempre uguale e affidabile — decisamente il compromesso
        # giusto dopo questa lunga caccia. splitter/ordinamento/cartelle
        # restano comunque salvati e ripristinati come prima.
        splitter_state = self.config.get("splitter_state")
        if splitter_state:
            self.splitter.restoreState(QByteArray.fromHex(splitter_state.encode()))

        sort_mode = self.config.get("sort_mode", "name")
        idx_map = {"name": 0, "size": 1, "date": 2}
        self.sort_combo.setCurrentIndex(idx_map.get(sort_mode, 0))

    def _clamp_geometry_to_screen(self) -> None:
        """Se la geometria della finestra supera parecchio lo spazio
        disponibile sullo schermo, la riporta a una dimensione
        ragionevole. Protegge da un bug noto di Qt su Windows
        (QWindowsWindow::setGeometry: Unable to set geometry, con la
        larghezza/altezza richiesta sempre esattamente il doppio del
        minimo consentito), legato allo scaling DPI non-100% e che puo'
        scattare non solo al ripristino della geometria salvata
        all'avvio, ma OGNI VOLTA che Qt ricalcola le dimensioni minime
        della finestra — per esempio aprendo il pannello duplicati
        (schede/scroll-area con un sizeHint minimo piu' grande di
        quello dell'anteprima singola normale). Prima veniva applicato
        solo a inizio programma; ora e' un metodo a parte richiamato
        anche da resizeEvent, cosi' si autocorregge qualunque cosa lo
        scateni, non solo l'avvio. Il flag _clamping_geometry evita che
        il resize()/move() qui dentro faccia scattare ricorsivamente
        un altro resizeEvent.

        BUG RISOLTO (introdotto da questa stessa protezione, segnalato
        subito con screenshot): quando la finestra e' GIA' massimizzata
        a schermo intero, geometry() puo' momentaneamente riportare una
        larghezza "sballata" (lo stesso bug di Qt/Windows descritto
        sopra) durante il ricalcolo del layout — ma in quel caso la
        finestra non ha affatto bisogno di essere "corretta": e' gia'
        della dimensione giusta (tutto lo schermo). Prima questo metodo
        interpretava quella lettura temporanea come "troppo larga" e
        la rimpiccioliva DAVVERO a 1400x900, rompendo una finestra
        massimizzata perfettamente funzionante (visto succedere aprendo
        Controlla duplicati). Ora, se la finestra e' massimizzata (o a
        schermo intero), il controllo viene saltato del tutto: quello
        stato lo gestisce gia' Windows, non serve la nostra correzione."""
        if self._clamping_geometry:
            return
        if self.isMaximized() or self.isFullScreen():
            return
        screen = self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.geometry()
        too_wide = geo.width() > avail.width() + 40
        too_tall = geo.height() > avail.height() + 40
        if too_wide or too_tall:
            self._clamping_geometry = True
            try:
                self.resize(min(1400, avail.width() - 40), min(900, avail.height() - 40))
                self.move(avail.x() + 20, avail.y() + 20)
            finally:
                self._clamping_geometry = False

    def _enforce_splitter_min_sizes(self) -> None:
        """Rete di sicurezza contro il pannello cartelle a destra che
        'sparisce' (larghezza vicina allo zero): visto in uno screen
        recording durante la scansione duplicati (che aggiorna lo stato
        molto spesso su liste di migliaia di file) — il pannello destro
        si riduceva quasi a niente ancora PRIMA che il pannello di
        revisione duplicati si aprisse, quindi non c'entra col resto
        del codice della revisione duplicati. setCollapsible(False)
        (v0.21) impedisce solo il collasso manuale trascinando il
        divisore, non un ridimensionamento del contenitore che erode
        gradualmente le proporzioni volute attraverso tanti ricalcoli
        di layout ravvicinati. Qui si controlla lo stato attuale dello
        splitter e, se il pannello destro e' sceso sotto una soglia
        ragionevole, lo si riporta a una proporzione sensata."""
        sizes = self.splitter.sizes()
        if len(sizes) != 2:
            return
        total = sum(sizes)
        if total <= 0:
            return
        if sizes[1] < 150:
            right_w = max(220, min(350, total // 4))
            self.splitter.setSizes([total - right_w, right_w])

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "delete_overlay"):
            self.delete_overlay.sync_geometry()
        if hasattr(self, "delete_progress_overlay"):
            self.delete_progress_overlay.sync_geometry()
        # BUG RISOLTO (v0.24->v0.25): _clamp_geometry_to_screen() NON
        # viene piu' richiamato da qui. Girava ad ogni ridimensionamento
        # della finestra "per sicurezza", ma e' risultato essere proprio
        # la causa di due regressioni diverse segnalate con screenshot
        # (finestra massimizzata rimpicciolita, poi finestra normale
        # rimpicciolita E spostata) invece che una protezione. Resta
        # attivo SOLO al ripristino della configurazione salvata
        # all'avvio (_restore_config) — il suo scopo originale dalla
        # v0.21, l'unico punto in cui e' stato verificato utile.
        self._enforce_splitter_min_sizes()

    def closeEvent(self, event) -> None:
        self.config.set_folders(self.folder_panel.get_folders())
        self.config.set("window_geometry", bytes(self.saveGeometry().toHex()).decode())
        self.config.set("splitter_state", bytes(self.splitter.saveState().toHex()).decode())
        mode_map = {0: "name", 1: "size", 2: "date"}
        self.config.set("sort_mode", mode_map.get(self.sort_combo.currentIndex(), "name"))
        self.config.save()
        self._flush_internal_trash()
        super().closeEvent(event)

    def _flush_internal_trash(self) -> None:
        """Alla chiusura del programma, sposta tutto cio' che e'
        rimasto nel cestino interno di TUF nel Cestino di Windows
        (se disponibile). Durante la sessione i file eliminati stanno
        nel cestino interno per permettere l'Undo istantaneo; una
        volta chiuso il programma non serve piu' poterli recuperare
        con Ctrl+Z, quindi passano al Cestino di sistema."""
        d = trash_dir()
        try:
            entries = list(d.iterdir())
        except OSError:
            return
        if not entries:
            return

        errors: list[str] = []
        moved = 0
        for entry in entries:
            if not entry.is_file():
                continue
            try:
                if send2trash is not None:
                    send2trash(str(entry))
                    moved += 1
                else:
                    entry.unlink()
                    errors.append(f"{entry.name}: eliminato definitivamente (modulo Cestino mancante)")
            except Exception as e:
                errors.append(f"{entry.name}: {e}")

        if errors:
            QMessageBox.warning(
                self, "Cestino di Windows",
                "Alcuni file non sono stati spostati correttamente nel Cestino "
                "di Windows:\n\n" + "\n".join(errors[:12])
                + ("\n..." if len(errors) > 12 else "")
                + "\n\nControlla che la libreria Send2Trash sia installata "
                "(pip install -r requirements.txt).",
            )
