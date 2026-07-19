"""
core/feedback_sender.py
Invio del feedback/consigli utente direttamente a una chat Telegram
del developer, in background.

RICHIESTA: "ok con telegram" — a differenza del resto di TUF (vedi
config.py, politica no-log), QUESTA e' un'eccezione esplicita e
volontaria: il testo che l'utente scrive nella scheda "Consigli" (o
nel box "suggerisci un formato") delle Impostazioni, e SOLO quello,
viene mandato a un bot Telegram del developer, cosi' arriva subito
senza che l'utente debba copiare/incollare/mandare un'email a mano.
Nessun altro dato lascia mai il PC dell'utente per questa via: non il
nome dei file, non la cronologia, non l'elenco delle cartelle — solo
il testo scritto volontariamente in quel campo (piu' nome/email se
l'utente li ha compilati).

Se l'invio fallisce (niente internet, token non configurato, Telegram
irraggiungibile), fallisce in silenzio lato interfaccia: il testo
resta comunque copiato negli appunti e salvato in locale come backup
(vedi ui/settings_dialog.py), quindi l'utente non perde mai nulla.

SICUREZZA: il token del bot qui sotto finisce, in chiaro, dentro ogni
copia distribuita di TUF (e' un'app desktop, non un server: non c'e'
un posto "segreto" dove nasconderlo). Un bot Telegram puo' pero' SOLO
mandare messaggi nella chat configurata (sendMessage) — non puo'
leggere altre chat dell'utente, non puo' accedere a nessun suo dato.
Il rischio pratico, nel peggiore dei casi, e' che qualcuno estragga il
token dall'app e lo usi per mandare messaggi/spam nella tua chat:
fastidioso, ma non un problema di sicurezza per chi usa TUF. Se in
futuro diventasse un problema reale, la soluzione e' passare da un
piccolo server proxy invece di chiamare Telegram direttamente
dall'app (puoi sempre rigenerare il token da @BotFather nel frattempo).
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from urllib.error import URLError

from PySide6.QtCore import QThread, Signal

# Token del bot e ID della chat dove arrivano i messaggi. Per
# ottenerli: 1) su Telegram cerca @BotFather, manda /newbot e segui le
# istruzioni per avere il TOKEN; 2) apri una chat col bot appena
# creato e mandagli un messaggio qualsiasi (es. "ciao"); 3) apri nel
# browser https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates e
# cerca "chat":{"id": ...} nel testo che compare — quel numero e' il
# CHAT_ID. Finche' questi due valori restano vuoti, l'invio via
# Telegram e' disattivato silenziosamente (resta comunque il backup
# su appunti + file locale, vedi ui/settings_dialog.py).
TELEGRAM_BOT_TOKEN = "8804066266:AAGd-mYULPlYhWRw6Oi8Xe9D2aT91JXtI7A"
TELEGRAM_CHAT_ID = "306479142"

_TIMEOUT_SECONDS = 6


class FeedbackSendWorker(QThread):
    """Manda `text` alla chat Telegram configurata, in un thread
    separato per non bloccare l'interfaccia mentre aspetta la rete."""

    finished_send = Signal(bool, str)  # (successo, messaggio_errore)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self) -> None:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            self.finished_send.emit(False, "non configurato")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": self.text,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                self.finished_send.emit(True, "")
            else:
                self.finished_send.emit(False, str(body.get("description", "errore sconosciuto")))
        except (URLError, OSError, json.JSONDecodeError, ValueError) as e:
            self.finished_send.emit(False, str(e))
