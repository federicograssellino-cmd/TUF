"""
ui/import_dialog.py
Dopo aver scelto la cartella sorgente, l'utente decide quali tipi di
file importare tramite checkbox, organizzate per gruppo (Multimedia,
Documenti, Altro) per restare leggibili anche con molte categorie.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QLabel
)

from filepilot.models import FileCategory, CATEGORY_LABELS, CATEGORY_EXTENSIONS, CATEGORY_GROUPS
from filepilot.ui.branding import app_icon, BrandedHeader, enable_dark_titlebar


class ImportSelectionDialog(QDialog):
    """Tendina con checkbox, organizzate a gruppi: quali categorie di
    file importare."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cosa vuoi importare?")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.addWidget(BrandedHeader("Cosa vuoi importare?"))
        layout.addWidget(QLabel("Seleziona i tipi di file da caricare:"))

        self._checks: dict[FileCategory, QCheckBox] = {}
        for group_name, categories in CATEGORY_GROUPS.items():
            header = QLabel(f"<b>{group_name}</b>")
            header.setStyleSheet("color: #ccc; margin-top: 6px;")
            layout.addWidget(header)
            for cat in categories:
                cb = QCheckBox(CATEGORY_LABELS[cat])
                cb.setChecked(True)
                layout.addWidget(cb)
                self._checks[cat] = cb

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # BUG RISOLTO: vedi il commento in ui/main_window.py sullo
        # stesso argomento — va chiamata DOPO che il layout esiste,
        # non a inizio __init__.
        enable_dark_titlebar(self)

    def selected_extensions(self) -> set[str]:
        ext: set[str] = set()
        for cat, cb in self._checks.items():
            if cb.isChecked():
                ext |= CATEGORY_EXTENSIONS[cat]
        return ext
