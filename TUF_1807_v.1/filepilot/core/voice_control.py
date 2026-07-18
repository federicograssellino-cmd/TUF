"""
core/voice_control.py
Comando vocale ad ascolto continuo: premi un tasto per attivarlo, poi
parli quando vuoi (numero cartella, nome cartella, "elimina",
"annulla", "avanti"/"indietro") senza
dover premere stop dopo ogni comando. Il programma riconosce da solo
quando hai finito di parlare (rilevamento pausa/silenzio) ed elabora
il comando, restando in ascolto per il successivo. Premi di nuovo lo
stesso tasto solo quando vuoi disattivare del tutto l'ascolto.

NB: la trascrizione usa il motore gratuito di Google, quindi serve
una connessione internet attiva. Per un uso completamente offline
(utile in barca senza rete) si puo' passare in futuro a un motore
locale come Vosk.
"""
from __future__ import annotations

import re
import threading
from collections import deque

from PySide6.QtCore import QThread, Signal

try:
    import sounddevice as sd
    import numpy as np
    _HAS_AUDIO = True
except (ImportError, OSError):
    _HAS_AUDIO = False

try:
    import speech_recognition as sr
except ImportError:
    sr = None

# Numeri in italiano, parola -> cifra (0 = elimina, come il tasto 0)
ITALIAN_NUMBERS = {
    "zero": 0, "uno": 1, "un": 1, "una": 1, "due": 2, "tre": 3,
    "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8,
    "nove": 9, "dieci": 10,
}

DELETE_WORDS = {"elimina", "cancella", "cestina", "cestino"}

# RICHIESTA ("comando vocale per undo"): parole per annullare l'ultimo
# spostamento/eliminazione a voce, come il tasto Ctrl+Z. Non e' lo
# stesso insieme di NO_WORDS qui sotto: quello serve SOLO per
# rispondere si'/no a una richiesta di conferma eliminazione (un
# contesto diverso, gestito a parte in main_window.py), quindi non
# c'e' ambiguita' nell'usare "annulla" in entrambi — nei due contesti
# non si sovrappongono mai.
UNDO_WORDS = {"annulla", "undo", "annulla ultimo", "torna indietro"}

# RICHIESTA: comandi vocali per scorrere avanti/indietro tra i file,
# come le frecce della tastiera. "indietro" da solo vale come
# "file precedente" (non va confuso con la frase "torna indietro"
# qui sopra, che invece annulla l'ultima azione — quella e' l'unica
# controllata a frase intera, quindi non c'e' conflitto).
NEXT_WORDS = {"avanti", "prossimo", "successivo", "next"}
PREV_WORDS = {"indietro", "precedente", "prima", "back"}

YES_WORDS = {"si", "sì", "ok", "va", "bene", "confermo", "conferma", "esatto",
             "giusto", "procedi", "yes"}
NO_WORDS = {"no", "annulla", "stop", "fermati", "lascia", "niente", "sbagliato", "nope"}

SAMPLE_RATE = 16000
CHUNK_SECONDS = 0.1          # granularita' di lettura dal microfono
# RICHIESTA ("piu' velocita' nella comprensione vocale, e di
# conseguenza nello spostamento dei file"): ridotta da 0.7 a 0.45. I
# comandi di questa app sono quasi sempre parole singole o numeri
# brevi ("tre", "elimina", "cucina"), quindi non serve una pausa cosi'
# lunga per essere sicuri che la frase sia finita — 0.45s resta
# comunque sufficiente a non tagliare parole normali, ma fa scattare
# il riconoscimento prima dopo ogni comando.
SILENCE_SECONDS = 0.45       # pausa dopo la quale si considera finita la frase
MIN_SPEECH_CHUNKS = 2        # scarta rumori troppo brevi (colpi, click)
CALIBRATION_CHUNKS = 4       # quanti blocchi usare per stimare il rumore di fondo
LOOKBACK_CHUNKS = 3          # blocchi tenuti "di scorta" per non tagliare l'inizio di parole brevi (es. "uno")


class VoiceWorker(QThread):
    """Ascolta in continuo dal microfono, individua da solo l'inizio e
    la fine di ogni frase (in base al volume) e per ognuna emette il
    testo riconosciuto. Continua finche' non viene chiamato stop()."""

    recognized = Signal(str)
    error = Signal(str)
    phrase_started = Signal()   # emesso quando rileva che si sta parlando
    audio_level = Signal(float)  # livello microfono in tempo reale (0.0-1.0), per l'onda visiva

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag = False

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        if not _HAS_AUDIO:
            self.error.emit(
                "Microfono non disponibile: installa 'sounddevice' e 'numpy' "
                "(pip install sounddevice numpy)."
            )
            return
        if sr is None:
            self.error.emit(
                "Riconoscimento vocale non disponibile: installa 'SpeechRecognition' "
                "(pip install SpeechRecognition)."
            )
            return

        self._stop_flag = False
        recognizer = sr.Recognizer()
        chunk_frames = int(SAMPLE_RATE * CHUNK_SECONDS)
        silence_chunks_needed = max(1, int(SILENCE_SECONDS / CHUNK_SECONDS))

        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
            stream.start()
        except Exception as e:
            self.error.emit(f"Microfono non disponibile: {e}")
            return

        try:
            # stima rapida del rumore di fondo, per non scattare sul silenzio
            calib_frames = []
            for _ in range(CALIBRATION_CHUNKS):
                if self._stop_flag:
                    stream.stop()
                    stream.close()
                    return
                data, _ = stream.read(chunk_frames)
                calib_frames.append(data)
            calib = np.concatenate(calib_frames, axis=0).astype(np.float64)
            noise_rms = float(np.sqrt(np.mean(calib ** 2)) if calib.size else 0.0)
            threshold = max(noise_rms * 2.0, 130.0)

            buffer: list = []
            rolling: deque = deque(maxlen=LOOKBACK_CHUNKS)
            speaking = False
            silence_chunks = 0
            speech_chunks = 0

            while not self._stop_flag:
                data, _ = stream.read(chunk_frames)
                rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))

                # livello normalizzato 0.0-1.0 per l'onda visiva sul pulsante microfono
                level = min(1.0, rms / max(threshold * 2.5, 1.0))
                self.audio_level.emit(level)

                if rms > threshold:
                    if not speaking:
                        # includi anche i blocchi appena precedenti, cosi'
                        # non si perde l'attacco di parole brevi come "uno"
                        buffer = list(rolling)
                        self.phrase_started.emit()
                    speaking = True
                    silence_chunks = 0
                    speech_chunks += 1
                    buffer.append(data.copy())
                else:
                    if speaking:
                        buffer.append(data.copy())  # tieni un po' di coda per non tagliare l'ultima parola
                        silence_chunks += 1
                        if silence_chunks >= silence_chunks_needed:
                            if speech_chunks >= MIN_SPEECH_CHUNKS:
                                segment = np.concatenate(buffer, axis=0)
                                self._recognize_segment(recognizer, segment)
                            buffer = []
                            speaking = False
                            silence_chunks = 0
                            speech_chunks = 0
                    else:
                        rolling.append(data.copy())
        except Exception as e:  # pragma: no cover - protezione generica
            self.error.emit(f"Errore comando vocale: {e}")
        finally:
            stream.stop()
            stream.close()

    def _recognize_segment(self, recognizer, segment) -> None:
        # RICHIESTA ("piu' velocita' nella comprensione vocale, e di
        # conseguenza nello spostamento dei file"): prima questa
        # funzione girava DENTRO al ciclo principale di cattura audio
        # (vedi run()), quindi la chiamata di rete a Google (l'unica
        # parte davvero lenta, puo' richiedere anche piu' di un
        # secondo) bloccava anche la lettura del microfono per tutta
        # la sua durata. Risultato: durante quell'attesa TUF non
        # "sentiva" un eventuale comando successivo, dando l'impressione
        # generale di lentezza, soprattutto spostando piu' file di
        # fila a comandi rapidi ("tre... due... elimina..."). Ora la
        # parte di rete gira in un thread Python separato (non blocca
        # ne' l'interfaccia — gia' su un QThread — ne' il ciclo di
        # cattura, che puo' cosi' individuare subito la frase
        # successiva mentre quella precedente e' ancora "in viaggio"
        # verso Google). Un nuovo sr.Recognizer() per ogni chiamata
        # (oggetto leggero) evita qualunque dubbio su un uso
        # concorrente dello stesso Recognizer da piu' thread insieme.
        def worker() -> None:
            try:
                raw_bytes = segment.tobytes()
                audio = sr.AudioData(raw_bytes, SAMPLE_RATE, 2)  # 2 byte = int16
                text = sr.Recognizer().recognize_google(audio, language="it-IT")
                self.recognized.emit(text)
            except sr.UnknownValueError:
                pass  # rumore/parola non capita: ignora e resta in ascolto
            except sr.RequestError as e:
                self.error.emit(f"Riconoscimento vocale non raggiungibile (serve internet): {e}")
            except Exception as e:  # pragma: no cover - protezione generica
                self.error.emit(f"Errore comando vocale: {e}")

        threading.Thread(target=worker, daemon=True).start()


def parse_yes_no(text: str) -> bool | None:
    """Interpreta una risposta di conferma/diniego a voce.
    Ritorna True (si'), False (no), oppure None se non capito."""
    clean = re.sub(r"[^\w\s]", "", text.strip().lower())
    words = set(clean.split())
    if words & NO_WORDS:
        return False
    if words & YES_WORDS:
        return True
    return None


def parse_voice_command(text: str, folder_names: dict[str, int]) -> tuple[str, int | None]:
    """Interpreta il testo trascritto. Ritorna una tupla (azione, numero):
    - ("delete", None) se e' un comando di eliminazione
    - ("undo", None) se e' un comando di annullamento ultima azione
    - ("next", None) se e' un comando "avanti" (file successivo)
    - ("prev", None) se e' un comando "indietro" (file precedente)
    - ("move", numero_cartella) se e' un numero o un nome cartella riconosciuto
    - ("unknown", None) se non e' stato capito

    `folder_names` e' un dict {nome_cartella_lower: numero}.
    """
    clean = text.strip().lower()
    clean = re.sub(r"[^\w\s]", "", clean)

    words = clean.split()
    if any(w in UNDO_WORDS for w in words) or clean in UNDO_WORDS:
        return "undo", None
    if any(w in DELETE_WORDS for w in words):
        return "delete", None
    if any(w in NEXT_WORDS for w in words):
        return "next", None
    if any(w in PREV_WORDS for w in words):
        return "prev", None

    # cifra scritta direttamente, es. "vai a 3" o "3"
    digit_match = re.search(r"\b(\d+)\b", clean)
    if digit_match:
        num = int(digit_match.group(1))
        if num == 0:
            return "delete", None
        return "move", num

    # numero scritto in lettere
    for w in words:
        if w in ITALIAN_NUMBERS:
            num = ITALIAN_NUMBERS[w]
            if num == 0:
                return "delete", None
            return "move", num

    # nome di una cartella pronunciato per intero
    for name_lower, number in folder_names.items():
        if name_lower and name_lower in clean:
            return "move", number

    return "unknown", None
