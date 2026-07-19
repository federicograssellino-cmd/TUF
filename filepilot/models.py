"""
models.py
Strutture dati centrali di TideUp File (TUF).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class FileCategory(Enum):
    IMAGE = auto()
    VIDEO = auto()
    AUDIO = auto()       # RICHIESTA: musica/audio (mp3, wav, ...)
    PDF = auto()
    WORD = auto()
    EXCEL = auto()
    POWERPOINT = auto()
    EBOOK = auto()        # RICHIESTA: ebook (epub, mobi, ...)
    SUBTITLE = auto()     # RICHIESTA: sottotitoli (srt, vtt, ...)
    TEXT_DATA = auto()    # RICHIESTA: testo/dati semplici (txt, csv, ...)
    FONT = auto()         # RICHIESTA: font (ttf, otf, ...)
    MODEL = auto()       # CAD e file 3D: STL, OBJ, DWG, ecc.
    ACTION = auto()      # GoPro, Insta360, droni DJI
    ARCHIVE = auto()     # zip e altri compressi
    CODE = auto()        # Arduino (.ino), Python (.py), ecc.
    APP = auto()         # RICHIESTA: applicazioni/eseguibili (exe, apk, ...)
    OTHER = auto()


# RICHIESTA ("formati... da una macroclasse piu' grande possibile"):
# catalogo ampliato rispetto a prima (RAW fotocamera, piu' formati
# video/archivio, e le categorie nuove Audio/Ebook/Sottotitoli/
# Testo-dati/Font qui sotto) — resta comunque una lista che si puo'
# sempre allargare ulteriormente in futuro, non pretende di coprire
# LETTERALMENTE ogni formato esistente al mondo.
IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".heic", ".dng",
    ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".svg", ".ico", ".avif",
    # grafica/design (raster e vettoriale)
    ".psd", ".ai", ".indd", ".sketch", ".fig", ".xd", ".eps",
}
VIDEO_EXT = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".mpg", ".mpeg",
    ".flv", ".webm", ".3gp", ".mts", ".m2ts", ".ts", ".vob", ".ogv",
}
AUDIO_EXT = {
    ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".aiff", ".opus",
    ".mid", ".midi", ".aif",
}
PDF_EXT = {".pdf"}
WORD_EXT = {".doc", ".docx", ".odt", ".rtf"}
EXCEL_EXT = {".xls", ".xlsx", ".xlsm", ".ods", ".csv"}
POWERPOINT_EXT = {".ppt", ".pptx", ".odp"}
EBOOK_EXT = {".epub", ".mobi", ".azw", ".azw3", ".fb2"}
SUBTITLE_EXT = {".srt", ".vtt", ".ass", ".ssa", ".sub"}
TEXT_DATA_EXT = {".txt", ".md", ".json", ".xml", ".log", ".yaml", ".yml", ".ini", ".cfg"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}
# CAD e modellazione 3D insieme (RICHIESTA esplicita di includere il CAD)
MODEL_EXT = {
    ".stl", ".obj", ".3mf", ".ply", ".fbx", ".gltf", ".glb",
    ".dwg", ".dxf", ".step", ".stp", ".iges", ".igs", ".skp",
    ".blend", ".max", ".c4d", ".dae",
}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"}
CODE_EXT = {
    ".ino", ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
    ".c", ".cpp", ".h", ".java", ".sh", ".bat", ".ps1", ".cs", ".php",
    ".rb", ".go", ".rs", ".swift", ".kt", ".sql",
}
# RICHIESTA: applicazioni/eseguibili
APP_EXT = {".exe", ".msi", ".apk", ".dmg", ".app", ".deb", ".rpm", ".appimage"}

# GoPro (.lrv proxy, .thm thumbnail, .360 Max, .gpr RAW),
# Insta360 (.insv video, .insp foto), droni DJI (.lrf proxy)
ACTION_EXT = {".lrv", ".thm", ".360", ".gpr", ".insv", ".insp", ".lrf"}

SUPPORTED_EXT = (
    IMAGE_EXT | VIDEO_EXT | AUDIO_EXT | PDF_EXT | WORD_EXT | EXCEL_EXT | POWERPOINT_EXT
    | EBOOK_EXT | SUBTITLE_EXT | TEXT_DATA_EXT | FONT_EXT
    | MODEL_EXT | ACTION_EXT | ARCHIVE_EXT | CODE_EXT | APP_EXT
)

CATEGORY_LABELS = {
    FileCategory.IMAGE: "Foto",
    FileCategory.VIDEO: "Video",
    FileCategory.AUDIO: "Audio",
    FileCategory.PDF: "PDF",
    FileCategory.WORD: "Word",
    FileCategory.EXCEL: "Excel",
    FileCategory.POWERPOINT: "PowerPoint",
    FileCategory.EBOOK: "Ebook",
    FileCategory.SUBTITLE: "Sottotitoli",
    FileCategory.TEXT_DATA: "Testo / dati",
    FileCategory.FONT: "Font",
    FileCategory.MODEL: "CAD / Modelli 3D",
    FileCategory.ACTION: "GoPro / 360 / Drone",
    FileCategory.ARCHIVE: "Archivi",
    FileCategory.CODE: "Codice / Programmazione",
    FileCategory.APP: "Applicazioni",
}

CATEGORY_EXTENSIONS = {
    FileCategory.IMAGE: IMAGE_EXT,
    FileCategory.VIDEO: VIDEO_EXT,
    FileCategory.AUDIO: AUDIO_EXT,
    FileCategory.PDF: PDF_EXT,
    FileCategory.WORD: WORD_EXT,
    FileCategory.EXCEL: EXCEL_EXT,
    FileCategory.POWERPOINT: POWERPOINT_EXT,
    FileCategory.EBOOK: EBOOK_EXT,
    FileCategory.SUBTITLE: SUBTITLE_EXT,
    FileCategory.TEXT_DATA: TEXT_DATA_EXT,
    FileCategory.FONT: FONT_EXT,
    FileCategory.MODEL: MODEL_EXT,
    FileCategory.ACTION: ACTION_EXT,
    FileCategory.ARCHIVE: ARCHIVE_EXT,
    FileCategory.CODE: CODE_EXT,
    FileCategory.APP: APP_EXT,
}

# Gruppi per il filtro/import a tendina: ogni gruppo raccoglie piu'
# categorie sotto un'unica voce espandibile ("Multimedia",
# "Documenti"...). Le categorie non elencate qui restano a se' stanti.
CATEGORY_GROUPS: dict[str, list[FileCategory]] = {
    "Multimedia": [FileCategory.IMAGE, FileCategory.VIDEO, FileCategory.AUDIO, FileCategory.ACTION],
    "Documenti": [
        FileCategory.PDF, FileCategory.WORD, FileCategory.EXCEL, FileCategory.POWERPOINT,
        FileCategory.EBOOK, FileCategory.TEXT_DATA,
    ],
    "Altro": [
        FileCategory.SUBTITLE, FileCategory.FONT, FileCategory.MODEL,
        FileCategory.ARCHIVE, FileCategory.CODE, FileCategory.APP,
    ],
}


def categorize(path: Path) -> FileCategory:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return FileCategory.IMAGE
    if ext in VIDEO_EXT:
        return FileCategory.VIDEO
    if ext in AUDIO_EXT:
        return FileCategory.AUDIO
    if ext in PDF_EXT:
        return FileCategory.PDF
    if ext in WORD_EXT:
        return FileCategory.WORD
    if ext in EXCEL_EXT:
        return FileCategory.EXCEL
    if ext in POWERPOINT_EXT:
        return FileCategory.POWERPOINT
    if ext in EBOOK_EXT:
        return FileCategory.EBOOK
    if ext in SUBTITLE_EXT:
        return FileCategory.SUBTITLE
    if ext in TEXT_DATA_EXT:
        return FileCategory.TEXT_DATA
    if ext in FONT_EXT:
        return FileCategory.FONT
    if ext in MODEL_EXT:
        return FileCategory.MODEL
    if ext in ACTION_EXT:
        return FileCategory.ACTION
    if ext in ARCHIVE_EXT:
        return FileCategory.ARCHIVE
    if ext in CODE_EXT:
        return FileCategory.CODE
    if ext in APP_EXT:
        return FileCategory.APP
    return FileCategory.OTHER


@dataclass
class FileItem:
    path: str
    size: int
    mtime: float
    category: FileCategory
    ctime: float = 0.0  # data di creazione (st_ctime; su Windows e' la vera data di creazione)
    file_hash: str | None = None  # calcolato solo per candidati duplicati

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()

    @staticmethod
    def from_path(p: Path) -> "FileItem":
        st = p.stat()
        return FileItem(
            path=str(p),
            size=st.st_size,
            mtime=st.st_mtime,
            category=categorize(p),
            ctime=st.st_ctime,
        )
