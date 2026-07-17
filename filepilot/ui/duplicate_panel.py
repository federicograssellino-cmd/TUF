"""
ui/duplicate_panel.py
Quando si incontra un gruppo di duplicati, questo pannello sostituisce
la normale anteprima mostrando 2, 3 o 4 file affiancati con i pulsanti
di risoluzione. Niente popup: tutto avviene dentro l'area di anteprima.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QMessageBox,
)

from filepilot.core.duplicates import DuplicateGroup
from filepilot.ui.preview_widget import render_pixmap
from filepilot.models import FileItem


class _Candidate(QFrame):
    def __init__(self, item: FileItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333; border-radius: 4px;")
        layout = QVBoxLayout(self)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumSize(240, 240)
        pix = render_pixmap(item, QSize(360, 360))
        if pix:
            self.img_label.setPixmap(pix)
        else:
            self.img_label.setText(Path(item.path).name)
        layout.addWidget(self.img_label, stretch=1)

        info = QLabel(f"{Path(item.path).name}\n{item.size / 1024:.0f} KB")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(info)

        self.keep_btn = QPushButton("Tieni questa")
        self.keep_btn.setCheckable(True)
        self.keep_btn.setChecked(True)  # default: tenute tutte finche' non si sceglie
        layout.addWidget(self.keep_btn)


class DuplicatePanel(QWidget):
    resolved = Signal()  # emesso quando il gruppo corrente e' stato gestito

    def __init__(self, parent=None):
        super().__init__(parent)
        self._group: DuplicateGroup | None = None
        self._on_delete_callback = None

        outer = QVBoxLayout(self)
        header = QLabel("File duplicati trovati")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #eee; padding: 6px;")
        outer.addWidget(header)

        self.cards_row = QHBoxLayout()
        outer.addLayout(self.cards_row, stretch=1)

        actions = QHBoxLayout()
        self.btn_keep_selected = QPushButton("Tieni selezionate / elimina altre")
        self.btn_keep_all = QPushButton("Tieni tutte")
        self.btn_skip = QPushButton("Salta")
        for b in (self.btn_keep_selected, self.btn_keep_all, self.btn_skip):
            actions.addWidget(b)
        outer.addLayout(actions)

        self.btn_keep_selected.clicked.connect(self._apply_keep_selected)
        self.btn_keep_all.clicked.connect(self._keep_all)
        self.btn_skip.clicked.connect(self._skip)

        self._cards: list[_Candidate] = []

    def show_group(self, group: DuplicateGroup, delete_callback) -> None:
        """delete_callback(paths_to_delete: list[str]) -> None, dovrebbe
        gestire l'eliminazione effettiva (con undo) nel MainWindow."""
        self._group = group
        self._on_delete_callback = delete_callback

        while self.cards_row.count():
            item = self.cards_row.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._cards.clear()

        for it in group.items:
            card = _Candidate(it)
            self._cards.append(card)
            self.cards_row.addWidget(card)

    def _apply_keep_selected(self) -> None:
        if not self._group:
            return
        to_delete = [c.item.path for c in self._cards if not c.keep_btn.isChecked()]
        if not to_delete:
            QMessageBox.information(self, "Nessuna selezione",
                                     "Nessun file e' stato deselezionato da eliminare.")
            return
        reply = QMessageBox.question(
            self, "Conferma eliminazione",
            f"Eliminare {len(to_delete)} file duplicati? L'azione sara' annullabile con Undo.",
        )
        if reply == QMessageBox.Yes and self._on_delete_callback:
            self._on_delete_callback(to_delete)
        self.resolved.emit()

    def _keep_all(self) -> None:
        self.resolved.emit()

    def _skip(self) -> None:
        self.resolved.emit()
