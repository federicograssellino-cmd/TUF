"""
ui/settings_dialog.py
Dialogo Impostazioni, a schede:
- Formati: RICHIESTA ("un menu impostazioni dove si scelgono i formati
  da una macroclasse piu' grande possibile, con ricerca per estensione,
  e poi quelli flaggati sono quelli che si trovano aprendo una
  cartella"). Ogni estensione supportata (vedi models.py, ampliato
  apposta in questa stessa versione) ha una sua checkbox, raggruppata
  per categoria (macroarea), con una casella di ricerca in cima che
  filtra live digitando anche solo un pezzo di estensione (es. "mp3").
  Ogni macroarea ha anche una sua checkbox (tri-state) per
  selezionare/deselezionare tutte le sue estensioni in un colpo solo
  — RICHIESTA: "dovresti mettermi il flag anche nelle macroaree". LA
  SCELTA FATTA QUI E' QUELLA PRINCIPALE (RICHIESTA: "la scelta dei
  formati nelle impostazioni è la principale"): la tendina "Filtri"
  nella finestra principale e' SECONDARIA e mostra solo cio' che e'
  abilitato qui (vedi multi_filter.py, set_enabled_extensions).
- Info: nome dell'app e numero di versione (da filepilot/__init__.py,
  un solo posto invece di doverlo tenere sincronizzato a mano in piu'
  punti).
- Account: RICHIESTA ("un login se servisse, lascialo un tasto
  silente al momento") — pulsante presente ma disabilitato, nessuna
  funzionalita' dietro per ora.

NOTA v0.34: la scheda "Generale" (dimensione testo/altezza riga/
spaziatura del pannello cartelle) e' stata rimossa — RICHIESTA:
"elimina la voce generale nelle impostazioni tanto abbiamo il cursore
sulle cartelle". Il cursore dimensione nel pannello cartelle
(folder_panel.py, size_slider) calcola gia' da solo tutti e tre quei
valori (vedi _on_slider_changed), quindi la scheda Generale era di
fatto ridondante: i valori che salvava non venivano nemmeno piu' letti
al riavvio (solo il livello dello slider lo e').
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QLabel, QTabWidget, QWidget, QLineEdit, QScrollArea, QCheckBox, QPushButton,
    QFrame, QPlainTextEdit, QMessageBox, QApplication, QKeySequenceEdit, QComboBox,
)

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from filepilot import __version__
from filepilot.config import CONFIG_PATH, DEFAULT_SHORTCUTS, SHORTCUT_LABELS
from filepilot.models import FileCategory, CATEGORY_LABELS, CATEGORY_EXTENSIONS, CATEGORY_GROUPS, SUPPORTED_EXT
from filepilot.ui.branding import app_icon, enable_dark_titlebar, TUF_ORANGE
from filepilot.ui.quick_guide_dialog import QuickGuideDialog
from filepilot.core.feedback_sender import FeedbackSendWorker
from filepilot.i18n import tr, SUPPORTED_LANGUAGES, LANGUAGE_NAMES, get_language, set_language

# RICHIESTA: "possiamo creare un'interfaccia dove mi arrivano le
# richieste feedback degli utenti?... piu' veloce farlo mandando una
# mail?" -> risposta scelta: "la cosa piu' veloce e semplice, che
# tuteli me e l'utente" = email precompilata (mailto). TUF non ha un
# server/backend proprio (coerente con l'app "no log": vedi
# config.py e PRIVACY.md), quindi non manda nulla da solo — apre
# semplicemente il programma di posta gia' installato sul computer
# dell'utente con oggetto e testo gia' pronti, ed e' l'UTENTE a
# decidere se premere invio. Nessuna password/credenziale email va
# quindi incorporata nell'app (che finirebbe sul computer di
# sconosciuti una volta distribuita).
DEV_FEEDBACK_EMAIL = "federicograssellino@gmail.com"


class _TriStateCheckBox(QCheckBox):
    """Checkbox tri-state ma solo per la VISUALIZZAZIONE (mostra lo
    stato 'parziale' quando alcune estensioni della macroarea sono
    spuntate e altre no). Il click dell'utente alterna sempre e solo
    tra tutto/niente, ignorando lo stato parziale nel ciclo — stesso
    comportamento della checkbox di gruppo nella tendina Filtri
    (multi_filter.py), per coerenza."""

    def nextCheckState(self) -> None:
        if self.checkState() == Qt.Checked:
            self.setCheckState(Qt.Unchecked)
        else:
            self.setCheckState(Qt.Checked)


class SettingsDialog(QDialog):
    def __init__(self, enabled_extensions: set[str] | None = None,
                 current_shortcuts: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        self._current_shortcuts = current_shortcuts or dict(DEFAULT_SHORTCUTS)
        # RICHIESTA: "rendere unica ogni copia" — letto/generato qui,
        # prima di costruire la scheda Info che lo mostra (vedi
        # config.py, get_install_id()).
        try:
            from filepilot.config import ConfigManager
            self._install_id = ConfigManager().get_install_id()
        except Exception:
            self._install_id = ""
        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}
        # RICHIESTA: "ok con telegram" — worker in corso per l'invio
        # feedback/suggerimenti a Telegram (vedi core/feedback_sender.py).
        # Tenerli in una lista finche' non finiscono evita che Python li
        # distrugga a meta' mentre girano ancora in background.
        self._active_send_workers: list[FeedbackSendWorker] = []
        self.setWindowTitle("Impostazioni")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(440)
        self.setMinimumHeight(480)

        # SEGNALATO: "qui si ripete due volte il logo TUF" — la barra
        # del titolo nativa di Windows mostra gia' l'icona TUF (da
        # setWindowIcon, sempre presente) accanto al titolo
        # "Impostazioni"; il BrandedHeader decorativo che stava qui
        # sotto e' stato tolto (era puramente decorativo in questo
        # dialogo, a differenza della finestra principale dove ospita
        # il tasto Impostazioni).
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        # SEGNALATO: "le scritte in impostazioni... sono in nero,
        # mettile in arancione e più grandi" — le linguette (Formati,
        # Info, Account) usavano il colore di default del tema, poco
        # leggibile. Ora sono arancioni (il colore del logo), piu'
        # grandi e in grassetto quando selezionate.
        tabs.setStyleSheet(
            "QTabBar::tab {"
            f" color: {TUF_ORANGE}; background-color: #262626;"
            " font-size: 13px; font-weight: 600; padding: 8px 16px;"
            " border-top-left-radius: 6px; border-top-right-radius: 6px; }"
            "QTabBar::tab:selected {"
            f" color: #1a1a1a; background-color: {TUF_ORANGE}; }}"
            "QTabBar::tab:!selected:hover { background-color: #333; }"
            "QTabWidget::pane { border: 1px solid #3a3a3a; border-radius: 4px; }"
        )
        layout.addWidget(tabs, stretch=1)

        tabs.addTab(self._build_formats_tab(enabled_extensions or set(SUPPORTED_EXT)), "Formati")
        tabs.addTab(self._build_shortcuts_tab(), "Scorciatoie")
        tabs.addTab(self._build_info_tab(), "Info")
        tabs.addTab(self._build_account_tab(), "Account")
        tabs.addTab(self._build_feedback_tab(), "Consigli")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # RICHIESTA: shortcut personalizzabili — prima di chiudere si
        # controlla che l'utente non abbia assegnato lo STESSO tasto a
        # due azioni diverse (vedi _on_ok_clicked), altrimenti solo una
        # delle due funzionerebbe davvero, in modo silenzioso e
        # confuso.
        buttons.accepted.connect(self._on_ok_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # BUG RISOLTO: vedi il commento in ui/main_window.py sullo
        # stesso argomento — va chiamata DOPO che il layout esiste,
        # non a inizio __init__.
        enable_dark_titlebar(self)

    # --------------------------------------------------- scheda Formati
    def _build_formats_tab(self, enabled_extensions: set[str]) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        intro = QLabel(
            "Seleziona quali tipi di file TUF deve riconoscere. Solo i "
            "formati spuntati qui compariranno quando apri una cartella "
            "E nella tendina \"Filtri\" della finestra principale."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #aaa; font-size: 11px;")
        v.addWidget(intro)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("🔎"))
        self.format_search = QLineEdit()
        self.format_search.setPlaceholderText("Cerca per estensione, es. mp3...")
        search_row.addWidget(self.format_search, stretch=1)
        v.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(10)

        # {categoria: [checkbox, ...]}
        self._format_checks: dict[FileCategory, list[QCheckBox]] = {}
        self._format_group_widgets: list[tuple[QWidget, list[QCheckBox]]] = []
        # checkbox "macroarea" (RICHIESTA: "mettimi il flag anche
        # nelle macroaree"), una per categoria, tri-state
        self._category_master_checks: dict[FileCategory, QCheckBox] = {}
        # RICHIESTA: "lascia visibili solo le macro, e nel caso in cui
        # mi servano specificatamente i file clicco sulla freccetta a
        # destra" — le singole estensioni di ogni macroarea sono ora
        # DENTRO un contenitore a parte, nascosto di default: si vede
        # solo la riga della macroarea (flag + nome + Tutti/Nessuno +
        # freccetta). Cliccando la freccetta si apre/chiude quel
        # contenitore, categoria per categoria.
        self._format_containers: dict[FileCategory, QWidget] = {}
        self._format_toggle_btns: dict[FileCategory, QPushButton] = {}

        for cat in CATEGORY_LABELS:
            extensions = sorted(CATEGORY_EXTENSIONS.get(cat, set()))
            if not extensions:
                continue

            group_widget = QWidget()
            group_layout = QVBoxLayout(group_widget)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(4)

            header_row = QHBoxLayout()

            master_cb = _TriStateCheckBox()
            master_cb.setTristate(True)
            header_row.addWidget(master_cb)

            header = QLabel(f"<b>{CATEGORY_LABELS[cat]}</b>")
            # SEGNALATO: nomi macroarea in nero/poco visibili -> arancione,
            # piu' grandi.
            header.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 13px;")
            header_row.addWidget(header)
            header_row.addStretch(1)
            all_btn = QPushButton("Tutti")
            none_btn = QPushButton("Nessuno")
            for b in (all_btn, none_btn):
                b.setFixedHeight(22)
                b.setStyleSheet(
                    "QPushButton { background-color: #333; color: #ccc; border: none;"
                    " border-radius: 4px; padding: 2px 8px; font-size: 10px; }"
                    "QPushButton:hover { background-color: #444; }"
                )
                header_row.addWidget(b)

            toggle_btn = QPushButton("▸")
            toggle_btn.setFixedSize(24, 22)
            toggle_btn.setStyleSheet(
                "QPushButton { background-color: #333; color: #ddd; border: none;"
                " border-radius: 4px; font-size: 11px; }"
                "QPushButton:hover { background-color: #444; }"
            )
            header_row.addWidget(toggle_btn)
            group_layout.addLayout(header_row)

            # contenitore delle estensioni della macroarea, chiuso di default
            ext_container = QWidget()
            ext_container_layout = QVBoxLayout(ext_container)
            ext_container_layout.setContentsMargins(20, 2, 0, 0)
            ext_container_layout.setSpacing(4)
            ext_container.setVisible(False)

            checks: list[QCheckBox] = []
            # righe da GRID_COLS colonne, cosi' non diventa una lista
            # lunghissima verticale per le categorie con molte estensioni
            grid_row = QHBoxLayout()
            grid_row.setSpacing(12)
            per_row = 3
            for i, ext in enumerate(extensions):
                if i % per_row == 0 and i > 0:
                    ext_container_layout.addLayout(grid_row)
                    grid_row = QHBoxLayout()
                    grid_row.setSpacing(12)
                cb = QCheckBox(ext)
                cb.setChecked(ext in enabled_extensions)
                cb.stateChanged.connect(lambda _, c=cat: self._sync_category_master(c))
                grid_row.addWidget(cb)
                checks.append(cb)
            grid_row.addStretch(1)
            ext_container_layout.addLayout(grid_row)
            group_layout.addWidget(ext_container)

            def _toggle(_checked=False, container=ext_container, btn=toggle_btn):
                opening = not container.isVisible()
                container.setVisible(opening)
                btn.setText("▾" if opening else "▸")

            toggle_btn.clicked.connect(_toggle)

            all_btn.clicked.connect(lambda _, cs=checks: [c.setChecked(True) for c in cs])
            none_btn.clicked.connect(lambda _, cs=checks: [c.setChecked(False) for c in cs])
            master_cb.stateChanged.connect(lambda state, cs=checks: self._on_category_master_changed(state, cs))

            inner_layout.addWidget(group_widget)
            self._format_checks[cat] = checks
            self._category_master_checks[cat] = master_cb
            self._format_group_widgets.append((group_widget, checks))
            self._format_containers[cat] = ext_container
            self._format_toggle_btns[cat] = toggle_btn

            self._sync_category_master(cat)

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, stretch=1)

        # RICHIESTA: "aggiungere un box nella lista formati per 'ti
        # serve un formato che non c'e'? scrivilo e lo implementeremo
        # il prima possibile'". Prima versione: apriva il programma
        # di posta (mailto:). SEGNALATO poi: "mi chiede di entrare
        # con la mail, non si puo' creare un metodo senza mail?" —
        # mailto: su molti PC senza un client di posta gia'
        # configurato scatena una richiesta di accesso account
        # invece di aprire l'email. Ora il pulsante copia il testo
        # negli appunti (vedi _copy_feedback_to_clipboard): funziona
        # SEMPRE, senza bisogno di nessun programma installato o
        # account configurato. Il testo resta anche salvato in
        # locale come backup.
        suggest_box = QFrame()
        suggest_box.setStyleSheet("background-color: #232323; border-radius: 6px;")
        suggest_layout = QVBoxLayout(suggest_box)
        suggest_label = QLabel(
            "Ti serve un formato che non c'è? Scrivilo qui sotto: lo implementeremo il prima possibile."
        )
        suggest_label.setWordWrap(True)
        suggest_label.setStyleSheet("color: #ccc; font-size: 11px;")
        suggest_layout.addWidget(suggest_label)

        suggest_row = QHBoxLayout()
        self.format_suggestion_edit = QLineEdit()
        self.format_suggestion_edit.setPlaceholderText('es. .heif, oppure "formato audio Dolby Atmos"...')
        suggest_row.addWidget(self.format_suggestion_edit, stretch=1)
        self.format_suggestion_btn = QPushButton("Invia")
        self.format_suggestion_btn.clicked.connect(self._submit_format_suggestion)
        suggest_row.addWidget(self.format_suggestion_btn)
        suggest_layout.addLayout(suggest_row)

        self.format_suggestion_status = QLabel("")
        self.format_suggestion_status.setStyleSheet("color: #6fd38a; font-size: 10px;")
        suggest_layout.addWidget(self.format_suggestion_status)

        v.addWidget(suggest_box)

        self.format_search.textChanged.connect(self._filter_formats)
        return page

    def _on_category_master_changed(self, state: int, checks: list[QCheckBox]) -> None:
        # BUG RISOLTO: 'state' qui e' l'int GREZZO passato dal segnale
        # stateChanged (non lo stesso tipo restituito da checkState()).
        # In questa versione di PySide6, confrontare direttamente
        # quell'int con l'enum Qt.Checked risulta SEMPRE False (Qt.
        # CheckState non e' un IntEnum), quindi "riattiva la macroarea"
        # non faceva mai ricomparire le estensioni — solo "disattiva"
        # sembrava funzionare, per pura coincidenza (False e' anche il
        # risultato "giusto" in quel verso). Va ricostruito l'enum
        # dall'int PRIMA di confrontarlo.
        checked = Qt.CheckState(state) == Qt.Checked
        for cb in checks:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)

    def _sync_category_master(self, cat: FileCategory) -> None:
        """RICHIESTA: "ho audio nel menu a tendina, vado in
        impostazioni, tolgo il flag a audio e mi sparisce anche dal
        menu a tendina" — la checkbox macroarea riflette SEMPRE lo
        stato vero delle sue estensioni (checked/unchecked/misto),
        anche quando cambiano una alla volta con le singole checkbox,
        non solo con Tutti/Nessuno/la checkbox stessa."""
        master = self._category_master_checks.get(cat)
        checks = self._format_checks.get(cat)
        if master is None or not checks:
            return
        states = [c.isChecked() for c in checks]
        master.blockSignals(True)
        if all(states):
            master.setCheckState(Qt.Checked)
        elif not any(states):
            master.setCheckState(Qt.Unchecked)
        else:
            master.setCheckState(Qt.PartiallyChecked)
        master.blockSignals(False)

    def _copy_feedback_to_clipboard(self, subject: str, body: str) -> None:
        """SEGNALATO: 'per darmi i consigli... mi chiede di entrare
        con la mail. non si puo' creare un metodo senza mail?' — il
        link mailto: apre il client di posta predefinito, ma su
        molti PC (soprattutto Windows senza Outlook/Mail configurato)
        quello scatena una richiesta di accesso/configurazione
        account invece di aprire subito un'email pronta. Sostituito
        con qualcosa che funziona SEMPRE, senza bisogno di nessun
        programma di posta configurato: il testo viene copiato negli
        appunti, pronto per essere incollato ovunque l'utente
        preferisca (email webmail, WhatsApp, Messaggi, ecc.)."""
        QApplication.clipboard().setText(f"{subject}\n\n{body}")

    def _send_feedback_async(self, text: str, status_label: QLabel) -> None:
        """RICHIESTA: "ok con telegram" — oltre alla copia negli
        appunti (che funziona sempre, anche senza internet), prova
        ANCHE a mandare lo stesso testo a una chat Telegram del
        developer (vedi core/feedback_sender.py), cosi' il feedback
        arriva subito senza che l'utente debba fare nulla in piu'.

        SEGNALATO ("i consigli non mi arrivano, o meglio mi arrivano
        solo se metto la mia mail"): controllato il codice, l'invio a
        Telegram viene SEMPRE tentato, indipendentemente da nome/email
        (vedi _submit_feedback: contact_line e' solo testo aggiunto in
        cima al messaggio, non una condizione). Il sospetto e' che
        prima, quando falliva in silenzio, il messaggio "copiato negli
        appunti" restava identico sia in caso di successo che di
        errore — impossibile capire dall'interfaccia se era arrivato
        o no. Ora un fallimento (Telegram irraggiungibile, token non
        valido, ecc.) mostra un messaggio ESPLICITO invece di restare
        silenzioso, cosi' si vede subito la differenza reale invece di
        doverla intuire dal fatto che sia arrivato o meno."""
        worker = FeedbackSendWorker(text, self)
        self._active_send_workers.append(worker)

        def _on_finished(success: bool, error: str, w=worker, label=status_label) -> None:
            if success:
                label.setStyleSheet("color: #6fd38a; font-size: 10px;")
                label.setText(label.text() + " — inviato anche via Telegram ✓")
            else:
                label.setStyleSheet("color: #e0a95f; font-size: 10px;")
                label.setText(
                    label.text() + f" — invio diretto via Telegram non riuscito ({error}), "
                    "ma resta copiato/salvato in locale"
                )
            if w in self._active_send_workers:
                self._active_send_workers.remove(w)

        worker.finished_send.connect(_on_finished)
        worker.start()

    def _submit_format_suggestion(self) -> None:
        text = self.format_suggestion_edit.text().strip()
        if not text:
            return
        try:
            requests_path = CONFIG_PATH.parent / "format_requests.txt"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(requests_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")
        except OSError:
            pass  # il salvataggio locale e' solo un backup

        body = f"Formato richiesto (versione TUF {__version__}):\n\n{text}"
        self._copy_feedback_to_clipboard("TUF - richiesta formato", body)
        self.format_suggestion_status.setStyleSheet("color: #6fd38a; font-size: 10px;")
        self.format_suggestion_status.setText(
            f"Copiato negli appunti! Incollalo (Ctrl+V) e mandalo a {DEV_FEEDBACK_EMAIL} ✓"
        )
        self._send_feedback_async(body, self.format_suggestion_status)
        self.format_suggestion_edit.clear()

    def _filter_formats(self, text: str) -> None:
        """Filtra live le estensioni digitando nella casella di ricerca:
        nasconde le singole checkbox che non corrispondono, e nasconde
        interi gruppi se NESSUNA delle loro estensioni corrisponde
        (cosi' con "mp3" resta visibile solo Audio, non tutte le
        categorie con una riga vuota in mezzo). Cercando qualcosa la
        macroarea con risultati si apre da sola (altrimenti non si
        vedrebbero le estensioni trovate, dato che ora sono chiuse per
        default); svuotando la ricerca torna tutto chiuso com'era."""
        needle = text.strip().lower().lstrip(".")
        # self._format_checks e self._format_group_widgets sono popolati
        # nello stesso ordine, nello stesso ciclo for cat in CATEGORY_LABELS
        # in _build_formats_tab, quindi si possono associare per indice.
        for cat, (group_widget, checks) in zip(self._format_checks.keys(), self._format_group_widgets):
            any_visible = False
            for cb in checks:
                ext_text = cb.text().lstrip(".")
                match = (not needle) or (needle in ext_text)
                cb.setVisible(match)
                any_visible = any_visible or match
            group_widget.setVisible(any_visible)

            container = self._format_containers.get(cat)
            btn = self._format_toggle_btns.get(cat)
            if container is None or btn is None:
                continue
            if needle:
                container.setVisible(any_visible)
                btn.setText("▾" if any_visible else "▸")
            else:
                container.setVisible(False)
                btn.setText("▸")

    def selected_extensions(self) -> set[str]:
        result: set[str] = set()
        for checks in self._format_checks.values():
            for cb in checks:
                if cb.isChecked():
                    result.add(cb.text())
        return result

    # --------------------------------------------------- scheda Info
    def _build_info_tab(self) -> QWidget:
        # RICHIESTA: "in info metti che e' un no log e scrivi quali
        # sono le funzioni" — questa scheda ora dichiara esplicitamente
        # la politica no-log (vedi anche PRIVACY.md e i commenti in
        # config.py) ed elenca le funzioni principali dell'app, cosi'
        # l'utente le trova subito senza dover cercare altrove.
        page = QWidget()
        outer = QVBoxLayout(page)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.addStretch(1)

        name_label = QLabel("TideUp File (TUF)")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 22px; font-weight: 700;")
        v.addWidget(name_label)

        version_label = QLabel(f"Versione {__version__}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: #ccc; font-size: 14px;")
        v.addWidget(version_label)

        desc = QLabel("Catalogazione rapida di foto, video e documenti,\ncon controllo duplicati integrato.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #999; font-size: 12px;")
        v.addWidget(desc)

        v.addSpacing(14)

        nolog_box = QFrame()
        nolog_box.setStyleSheet(
            "QFrame { background-color: #1f2a20; border: 1px solid #3a5a3d; border-radius: 6px; }"
        )
        nolog_v = QVBoxLayout(nolog_box)
        nolog_title = QLabel("🔒 App NO LOG")
        nolog_title.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 13px; font-weight: 700; border: none;")
        nolog_v.addWidget(nolog_title)
        nolog_text = QLabel(
            "TUF non salva mai il contenuto dei file che apri o visualizzi, "
            "non tiene una cronologia di cosa hai aperto e non manda nessun "
            "dato online. Tutto resta ed elabora solo sul tuo computer, "
            "in locale. Per i dettagli completi (cosa viene salvato e cosa "
            "no) vedi PRIVACY.md nella cartella del programma."
        )
        nolog_text.setWordWrap(True)
        nolog_text.setStyleSheet("color: #cfe8d1; font-size: 11px; border: none;")
        nolog_v.addWidget(nolog_text)
        v.addWidget(nolog_box)

        v.addSpacing(14)

        # RICHIESTA: "implementiamo anche le lingue!" — selettore
        # lingua richiamabile in qualsiasi momento (non solo al primo
        # avvio, vedi ui/language_dialog.py). Cambia subito
        # config["language"] e la lingua attiva del processo (usata
        # dalla guida rapida/Termini/tour la prossima volta che si
        # aprono), ma il resto della finestra principale — non ancora
        # passato a tr(), fase 2 — si aggiorna solo al prossimo avvio.
        lang_box = QFrame()
        lang_box.setStyleSheet(
            "QFrame { background-color: #232323; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        lang_v = QVBoxLayout(lang_box)
        lang_row = QHBoxLayout()
        lang_label = QLabel(tr("settings.language_label"))
        lang_label.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 13px; font-weight: 700; border: none;")
        lang_row.addWidget(lang_label)
        lang_row.addStretch(1)
        self.language_combo = QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(LANGUAGE_NAMES[code], userData=code)
        current_code = get_language()
        idx = self.language_combo.findData(current_code)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self.language_combo)
        lang_v.addLayout(lang_row)
        lang_note = QLabel(tr("settings.language_restart_note"))
        lang_note.setStyleSheet("color: #888; font-size: 10.5px; border: none;")
        lang_v.addWidget(lang_note)
        v.addWidget(lang_box)

        v.addSpacing(14)

        # RICHIESTA: "possiamo 'rendere unica' ogni copia?" — ID locale
        # univoco per installazione (vedi config.py, get_install_id()),
        # SOLO per tracciabilità volontaria via feedback Telegram: non è
        # una licenza, non blocca nulla, non viene mai inviato in
        # automatico (coerente con il no-log). Generato la prima volta
        # che questa scheda viene aperta.
        id_box = QFrame()
        id_box.setStyleSheet(
            "QFrame { background-color: #232323; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        id_v = QVBoxLayout(id_box)
        id_label = QLabel(tr("settings.install_id_label"))
        id_label.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 13px; font-weight: 700; border: none;")
        id_v.addWidget(id_label)

        id_row = QHBoxLayout()
        self.install_id_field = QLineEdit(self._install_id)
        self.install_id_field.setReadOnly(True)
        self.install_id_field.setStyleSheet(
            "QLineEdit { background-color: #1a1a1a; color: #ccc; border: 1px solid #3a3a3a;"
            " border-radius: 4px; padding: 4px; font-family: Consolas, monospace; font-size: 11px; }"
        )
        id_row.addWidget(self.install_id_field, stretch=1)
        id_copy_btn = QPushButton(tr("settings.install_id_copy_btn"))
        id_copy_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #ddd; border: 1px solid #555;"
            " border-radius: 4px; padding: 4px 10px; font-size: 11px; }"
            "QPushButton:hover { background-color: #3d3d3d; }"
        )
        id_copy_btn.clicked.connect(self._copy_install_id)
        id_row.addWidget(id_copy_btn)
        id_v.addLayout(id_row)

        id_note = QLabel(tr("settings.install_id_note"))
        id_note.setWordWrap(True)
        id_note.setStyleSheet("color: #888; font-size: 10.5px; border: none;")
        id_v.addWidget(id_note)
        v.addWidget(id_box)

        v.addSpacing(14)

        func_title = QLabel("Cosa fa TUF")
        func_title.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 13px; font-weight: 700;")
        v.addWidget(func_title)

        functions = [
            "Catalogare ed esplorare foto, video, documenti e molti altri formati in una cartella",
            "Filtrare i file per tipo/formato (in Impostazioni > Formati e nella tendina rapida)",
            "Trovare i file duplicati e rivederli fianco a fianco, per gruppo o per colonna",
            "Eliminare o tenere i duplicati con un click, con Cestino interno e Annulla (Undo)",
            "Navigare e cancellare i file anche a comando vocale (\"avanti\", \"indietro\", \"cestino\")",
            "Segnalare formati mancanti o lasciare consigli direttamente da Impostazioni",
        ]
        func_text = QLabel("\n".join(f"•  {f}" for f in functions))
        func_text.setWordWrap(True)
        func_text.setStyleSheet("color: #ccc; font-size: 11px;")
        v.addWidget(func_text)

        v.addStretch(2)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        # RICHIESTA: "metti guida rapida anche nelle impostazioni per
        # favore, cosi' da essere recuperata facilmente" — la stessa
        # guida che compare al primo avvio (vedi quick_guide_dialog.py
        # e main_window.py) resta raggiungibile qui in qualsiasi
        # momento, per chi l'ha chiusa troppo in fretta o la vuole
        # rileggere.
        btn_row2 = QHBoxLayout()
        guide_btn = QPushButton("Guida rapida")
        # RICHIESTA: "non si può creare una guida interattiva al primo
        # avvio?" -> "sarebbe figo!" — oltre alla guida testuale, ora
        # c'e' anche un tour "a riflettore" che mostra dal vivo i
        # controlli veri della finestra principale (vedi
        # ui/onboarding_tour.py). Richiamabile da qui in qualsiasi
        # momento, non solo al primissimo avvio.
        tour_btn = QPushButton("Tour interattivo")
        terms_btn = QPushButton("Termini e Condizioni")
        # RICHIESTA: nell'installer, PRIVACY.md non e' piu' un file
        # separato da vedere nella cartella di TUF (viene impacchettato
        # DENTRO TUF.exe da Crea_Installer_TUF.bat, cosi' l'unica cosa installata
        # resta il singolo eseguibile) — questo tasto lo apre comunque,
        # con lo stesso meccanismo gia' usato per i Termini e Condizioni.
        privacy_btn = QPushButton("Privacy")
        for b in (guide_btn, tour_btn, terms_btn, privacy_btn):
            b.setStyleSheet(
                "QPushButton { background-color: #333; color: #ddd; border: 1px solid #555;"
                " border-radius: 4px; padding: 8px; }"
                "QPushButton:hover { background-color: #3d3d3d; }"
            )
        guide_btn.clicked.connect(self._open_quick_guide)
        tour_btn.clicked.connect(self._replay_onboarding_tour)
        terms_btn.clicked.connect(self._open_terms)
        privacy_btn.clicked.connect(self._open_privacy)
        btn_row2.addWidget(guide_btn)
        btn_row2.addWidget(tour_btn)
        btn_row2.addWidget(terms_btn)
        btn_row2.addWidget(privacy_btn)
        outer.addLayout(btn_row2)

        return page

    def _copy_install_id(self) -> None:
        QApplication.clipboard().setText(self.install_id_field.text())
        # RICHIESTA: piccola conferma visiva, stesso pattern gia' usato
        # altrove nelle Impostazioni per "copiato negli appunti".
        self.install_id_field.setToolTip(tr("settings.install_id_copied"))

    def _on_language_changed(self, _index: int) -> None:
        code = self.language_combo.currentData()
        if not code:
            return
        set_language(code)
        try:
            from filepilot.config import ConfigManager
            cfg = ConfigManager()
            cfg.set("language", code)
            cfg.set("language_chosen", True)
            cfg.save()
        except Exception:
            pass  # la lingua resta comunque attiva per questa sessione anche se il salvataggio fallisce

    def _open_quick_guide(self) -> None:
        QuickGuideDialog(self).exec()

    def _replay_onboarding_tour(self) -> None:
        """Chiude le Impostazioni e rilancia il tour interattivo sulla
        finestra principale (deve stare completamente visibile e
        senza dialoghi sopra, quindi le Impostazioni si chiudono
        prima di farlo partire)."""
        main_window = self.parent()
        self.reject()
        if main_window is not None and hasattr(main_window, "_start_onboarding_tour"):
            QTimer.singleShot(200, main_window._start_onboarding_tour)

    def _open_terms(self) -> None:
        """RICHIESTA: "metti termini e condizioni su impostazioni" —
        apre il PDF con il visualizzatore predefinito del sistema.
        Il documento vive nella cartella principale del programma
        (accanto a filepilot/), quindi risaliamo da questo file:
        ui/settings_dialog.py -> filepilot/ -> cartella del programma."""
        base_dir = Path(__file__).resolve().parent.parent.parent
        pdf_path = base_dir / "TERMINI_E_CONDIZIONI.pdf"
        if pdf_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
        else:
            QMessageBox.warning(
                self, "Termini e Condizioni",
                "Non trovo il file TERMINI_E_CONDIZIONI.pdf nella cartella del programma."
            )

    def _open_privacy(self) -> None:
        """Apre PRIVACY.md con il visualizzatore predefinito del
        sistema, stesso meccanismo di _open_terms qui sopra."""
        base_dir = Path(__file__).resolve().parent.parent.parent
        privacy_path = base_dir / "PRIVACY.md"
        if privacy_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(privacy_path)))
        else:
            QMessageBox.warning(
                self, "Privacy",
                "Non trovo il file PRIVACY.md nella cartella del programma."
            )

    # --------------------------------------------------- scheda Account
    def _build_account_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch(1)

        header = QLabel("Account")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 16px; font-weight: 700;")
        v.addWidget(header)

        info = QLabel(
            "L'accesso con un account non è ancora disponibile.\n"
            "Per ora TUF funziona interamente in locale, senza\n"
            "bisogno di nessun account."
        )
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        info.setStyleSheet("color: #ccc; font-size: 12px;")
        v.addWidget(info)

        self.login_btn = QPushButton("Accedi")
        self.login_btn.setEnabled(False)
        self.login_btn.setFixedWidth(140)
        self.login_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #777; border: none;"
            " border-radius: 4px; padding: 8px; }"
        )
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.login_btn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        v.addStretch(2)
        return page

    # ------------------------------------------------- scheda Scorciatoie
    def _build_shortcuts_tab(self) -> QWidget:
        """RICHIESTA: 'sarebbe carino che il cestino, il comando doppio
        numero e tutte le shortcut create possano essere personalizzabili
        in impostazioni' — una riga per azione, con un QKeySequenceEdit
        (widget standard di Qt: clic e poi premi il tasto/combinazione
        voluta) e un pulsante per tornare al valore predefinito.

        I tasti numero 1-9 (cartelle) e lo "0" del tastierino NON sono
        qui: restano sempre fissi perche' legati al numero stesso di
        ogni cartella (vedi commento su DEFAULT_SHORTCUTS in config.py).
        Il conflitto tra due azioni con lo stesso tasto viene controllato
        alla chiusura (vedi _on_ok_clicked), non riga per riga: durante
        la digitazione e' normale passare per stati temporaneamente
        duplicati (es. scambiando due tasti tra loro)."""
        page = QWidget()
        v = QVBoxLayout(page)

        header = QLabel("Scorciatoie da tastiera")
        header.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 15px; font-weight: 700;")
        v.addWidget(header)

        info = QLabel(
            "Clicca su una scorciatoia e premi il tasto (o la combinazione, "
            "es. Ctrl+Z) che vuoi usare al suo posto.\n\n"
            "I tasti numero 1-9 (cartelle) e lo 0 (cestino) del tastierino "
            "restano sempre fissi, perché legati al numero stesso di ogni "
            "cartella — qui sotto puoi personalizzare tutto il resto."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 11px; padding-bottom: 6px;")
        v.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        rows_widget = QWidget()
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setSpacing(8)

        for action_id, label in SHORTCUT_LABELS.items():
            row = QHBoxLayout()
            name_label = QLabel(label)
            name_label.setStyleSheet("color: #ddd; font-size: 12px;")
            row.addWidget(name_label, stretch=1)

            edit = QKeySequenceEdit(
                QKeySequence(self._current_shortcuts.get(action_id, DEFAULT_SHORTCUTS[action_id]))
            )
            try:
                edit.setMaximumSequenceLength(1)  # una sola combinazione, non una catena di tasti
            except AttributeError:
                pass  # versioni piu' vecchie di Qt non hanno questo limite: va comunque bene
            edit.setFixedWidth(150)
            edit.setStyleSheet(
                "background-color: #262626; border: 1px solid #3a3a3a;"
                " border-radius: 4px; color: #fff; padding: 4px;"
            )
            row.addWidget(edit)

            reset_btn = QPushButton("↺")
            reset_btn.setToolTip("Ripristina il tasto predefinito")
            reset_btn.setFixedWidth(30)
            reset_btn.setStyleSheet(
                "QPushButton { color: #999; border: none; background: transparent; }"
                "QPushButton:hover { color: #fff; }"
            )
            reset_btn.clicked.connect(
                lambda _, e=edit, a=action_id: e.setKeySequence(QKeySequence(DEFAULT_SHORTCUTS[a]))
            )
            row.addWidget(reset_btn)

            self._shortcut_edits[action_id] = edit
            rows_layout.addLayout(row)

        rows_layout.addStretch(1)
        scroll.setWidget(rows_widget)
        v.addWidget(scroll, stretch=1)
        return page

    def selected_shortcuts(self) -> dict[str, str]:
        """Legge il tasto scelto in ogni riga; se un campo e' stato
        svuotato del tutto (nessun tasto premuto), si ricade sul
        predefinito invece di lasciare quell'azione senza scorciatoia."""
        result: dict[str, str] = {}
        for action_id, edit in self._shortcut_edits.items():
            text = edit.keySequence().toString()
            result[action_id] = text or DEFAULT_SHORTCUTS[action_id]
        return result

    def _on_ok_clicked(self) -> None:
        seen: dict[str, str] = {}
        for action_id, key_str in self.selected_shortcuts().items():
            if key_str in seen:
                other_label = SHORTCUT_LABELS[seen[key_str]]
                this_label = SHORTCUT_LABELS[action_id]
                QMessageBox.warning(
                    self, "Scorciatoia duplicata",
                    f'Il tasto "{key_str}" è assegnato sia a "{this_label}" '
                    f'sia a "{other_label}".\n\nScegli un tasto diverso per '
                    "una delle due prima di continuare."
                )
                return
            seen[key_str] = action_id
        self.accept()

    # --------------------------------------------------- scheda Consigli
    def _build_feedback_tab(self) -> QWidget:
        """RICHIESTA: 'Hai altri consigli? Tuf ti aiuta, aiutaci ad
        aiutarti' (spazio di feedback libero) — a differenza del box
        suggerimento formati (specifico per un'estensione mancante),
        questo e' uno spazio libero per QUALSIASI consiglio/idea su
        TUF. AGGIORNATO (mailto: dava problemi su PC senza client di
        posta configurato): il pulsante 'Invia' copia il testo negli
        appunti, pronto da incollare ovunque (vedi
        _copy_feedback_to_clipboard), con salvataggio locale di
        backup in feedback.txt. Nessun server/credenziale email
        dentro l'app."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch(1)

        header = QLabel("Hai altri consigli?")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(f"color: {TUF_ORANGE}; font-size: 16px; font-weight: 700;")
        v.addWidget(header)

        subtitle = QLabel("TUF ti aiuta, aiutaci ad aiutarti.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #ccc; font-size: 12px;")
        v.addWidget(subtitle)

        intro = QLabel(
            "Scrivi qui sotto qualunque consiglio, idea o segnalazione: "
            "verrà salvato e letto per migliorare TUF."
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignCenter)
        intro.setStyleSheet("color: #999; font-size: 11px; padding: 4px 12px;")
        v.addWidget(intro)

        # RICHIESTA: "il nome e pass servono nel caso in cui qualcuno
        # abbia un problema, così riesco subito a creare un canale
        # mail diretto con l'utente" — per questo obiettivo non serve
        # un account con password: basta che chi scrive un feedback
        # lasci (facoltativamente) nome ed email, cosi' si puo'
        # rispondere direttamente. Nessun dato obbligatorio, nessun
        # login: se questi due campi restano vuoti il feedback viene
        # comunque inviato in forma anonima come prima.
        contact_row = QHBoxLayout()
        self.feedback_name_edit = QLineEdit()
        self.feedback_name_edit.setPlaceholderText("Nome (facoltativo)")
        self.feedback_email_edit = QLineEdit()
        self.feedback_email_edit.setPlaceholderText("Email (facoltativa, per poterti rispondere)")
        contact_row.addWidget(self.feedback_name_edit)
        contact_row.addWidget(self.feedback_email_edit)
        v.addLayout(contact_row)

        self.feedback_edit = QPlainTextEdit()
        self.feedback_edit.setPlaceholderText(
            "Es. \"vorrei poter...\", \"sarebbe utile se...\", oppure un problema che hai notato."
        )
        self.feedback_edit.setFixedHeight(110)
        v.addWidget(self.feedback_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.feedback_btn = QPushButton("Invia")
        self.feedback_btn.clicked.connect(self._submit_feedback)
        btn_row.addWidget(self.feedback_btn)
        v.addLayout(btn_row)

        self.feedback_status = QLabel("")
        self.feedback_status.setAlignment(Qt.AlignCenter)
        self.feedback_status.setStyleSheet("color: #6fd38a; font-size: 10px;")
        v.addWidget(self.feedback_status)

        v.addStretch(2)
        return page

    def _submit_feedback(self) -> None:
        text = self.feedback_edit.toPlainText().strip()
        if not text:
            return
        name = self.feedback_name_edit.text().strip()
        email = self.feedback_email_edit.text().strip()
        contact_line = ""
        if name or email:
            contact_line = f"Da: {name or '(nome non indicato)'} <{email or 'email non indicata'}>\n"

        try:
            feedback_path = CONFIG_PATH.parent / "feedback.txt"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(feedback_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}]\n{contact_line}{text}\n\n")
        except OSError:
            pass  # il salvataggio locale e' solo un backup

        body = f"Consiglio/feedback (versione TUF {__version__}):\n\n{contact_line}{text}"
        self._copy_feedback_to_clipboard("TUF - consiglio", body)
        self.feedback_status.setStyleSheet("color: #6fd38a; font-size: 10px;")
        self.feedback_status.setText(
            f"Copiato negli appunti! Incollalo (Ctrl+V) e mandalo a {DEV_FEEDBACK_EMAIL} ✓"
        )
        self._send_feedback_async(body, self.feedback_status)
        self.feedback_edit.clear()
