"""
main.py
Entry point di FilePilot.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from filepilot.config import _config_dir
from filepilot.ui.main_window import MainWindow


DARK_STYLESHEET = """
QWidget { background-color: #181818; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QLineEdit, QComboBox, QSpinBox {
    background-color: #262626; border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;
}
QScrollBar:vertical { background: #1a1a1a; width: 10px; }
QScrollBar::handle:vertical { background: #444; border-radius: 5px; }
QSplitter::handle { background-color: #2a2a2a; }
QToolTip {
    background-color: #2a2a2a;
    color: #f0f0f0;
    border: 1px solid #444;
    padding: 4px 8px;
}
"""
# BUG RISOLTO ("la descrizione dell'icona modifica/cestino e' scritta
# in nero e non si legge"): il resto del tema scuro viene dalla regola
# generica "QWidget { color: #e0e0e0 }" qui sopra, che in teoria
# dovrebbe valere anche per i tooltip (QToolTip e' comunque un
# QWidget) — ma su Windows i tooltip nativi non seguono sempre in modo
# affidabile lo stile ereditato da una regola QWidget generica, e
# restava un tooltip con testo scuro poco leggibile. Aggiunta una
# regola ESPLICITA per QToolTip (sfondo scuro coerente col resto
# dell'app, testo chiaro), che e' anche la pratica raccomandata da Qt
# per i tooltip invece di affidarsi all'ereditarieta' da QWidget.


def _install_crash_handler() -> None:
    """Installa un gestore globale per le eccezioni non catturate.

    BUG RISOLTO ("il programma va in crash"): senza un gestore
    personalizzato, se un'eccezione Python esce da una funzione
    collegata a un segnale Qt (un clic su un pulsante, un segnale
    emesso da un thread in background, ecc.) PySide6 puo' terminare
    di colpo l'intero processo, senza nessun messaggio ne' modo di
    continuare — anche per errori minori che non dovrebbero fermare
    tutto il programma. Prima questo gestore non c'era, quindi
    qualunque eccezione imprevista chiudeva l'app senza lasciare
    traccia di cosa fosse successo, rendendo impossibile capire la
    causa a posteriori.

    Ora l'eccezione viene invece registrata su file (nella cartella di
    configurazione di TUF, "crash_log.txt", cosi' i dettagli restano
    disponibili anche dopo aver chiuso l'app) e mostrata in un
    messaggio a schermo, ma il resto del programma resta aperto e
    utilizzabile: l'azione che ha causato l'errore semplicemente non
    va a buon fine, invece di portarsi via tutta l'applicazione."""
    log_path = _config_dir() / "crash_log.txt"

    def handle_exception(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now().isoformat()} ---\n{text}\n")
        except OSError:
            pass
        print(text, file=sys.stderr)

        try:
            QMessageBox.warning(
                None,
                "Errore imprevisto",
                "Si e' verificato un errore imprevisto durante un'operazione.\n"
                "TUF prova a restare aperto: se qualcosa sembra bloccato o non "
                "funziona come previsto, riprova l'operazione o riavvia il "
                "programma.\n\n"
                f"Dettagli salvati in:\n{log_path}\n\n"
                f"{exc_type.__name__}: {exc_value}",
            )
        except Exception:
            pass  # non deve mai far crashare il gestore di crash stesso

    sys.excepthook = handle_exception


def main() -> None:
    # BUG RISOLTO ("la finestra continua a ridimensionarsi"/crash aprendo
    # i duplicati): un utente ci ha mandato il log di Qt, che mostrava
    # ripetuti "QWindowsWindow::setGeometry: Unable to set geometry"
    # con la larghezza richiesta SEMPRE esattamente il doppio (2x)
    # della larghezza minima riportata da Windows. Questo e' il sintomo
    # tipico di un noto problema di Qt su Windows con PIU' MONITOR a
    # scaling DPI diverso (es. portatile al 150%, monitor esterno al
    # 100% o 200%): Qt puo' finire per calcolare la geometria in uno
    # spazio DPI e applicarla in un altro, raddoppiando i valori. La
    # policy "PassThrough" (quella raccomandata da Qt stesso per questo
    # esatto scenario) fa sì che il fattore di scala di ogni monitor
    # venga usato cosi' com'e', senza arrotondamenti/composizioni che
    # possono disallinearsi tra un monitor e l'altro. Va impostata PRIMA
    # di creare la QApplication.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("TideUp File")
    app.setStyleSheet(DARK_STYLESHEET)

    _install_crash_handler()

    window = MainWindow()
    # RICHIESTA: "riesci a farla diventare già da subito a schermo
    # intero?" — prima si apriva sempre alla dimensione di default
    # (1400x900, vedi MainWindow.__init__), non massimizzata.
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
