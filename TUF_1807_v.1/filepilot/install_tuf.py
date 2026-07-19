"""
install_tuf.py
Installer minimale di TUF: SOLO due file arrivano a chi riceve il
programma — "TUF.exe" (l'app, contiene tutto) e "Installa_TUF.exe"
(generato da QUESTO script tramite Crea_Installer_TUF.bat/PyInstaller). Chi lo
riceve fa doppio click su "Installa_TUF.exe" (ha gia' l'icona di TUF)
e basta: copia TUF.exe in una cartella personale, crea l'icona sul
Desktop e la voce nel menu Start, offre di avviare TUF subito.

RICHIESTA ESPLICITA: "l'utente deve avere due soli file... uno e'
quello che contiene tutto [TUF.exe], l'altro e' il launch installer di
tuf [questo script, compilato]... l'utente schiaccia l'installer tuf,
con tanto di icona, e inizia l'installazione." Scelto di NON usare
Inno Setup per questo (un tool esterno in piu' da installare/imparare):
questo script usa solo librerie standard di Python + il componente
Windows Script Host gia' presente su ogni Windows (cscript.exe, per
creare i collegamenti .lnk), cosi' si compila con lo stesso identico
PyInstaller gia' usato per TUF.exe, nello stesso Crea_Installer_TUF.bat.

Non serve essere amministratore: installa nel profilo dell'utente
corrente (%LOCALAPPDATA%\\Programs\\TUF), non in Program Files.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

MB_OK = 0x0
MB_YESNO = 0x4
MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40
MB_ICONQUESTION = 0x20
IDYES = 6


def _msgbox(text: str, title: str = "Installazione TUF", style: int = MB_OK | MB_ICONINFORMATION) -> int:
    return ctypes.windll.user32.MessageBoxW(0, text, title, style)


def _own_dir() -> Path:
    """Cartella da cui gira questo installer: quando e' compilato con
    PyInstaller, sys.executable e' il vero percorso di
    Installa_TUF.exe (non un python.exe temporaneo)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _shell_folder(name: str) -> Path:
    """Legge il percorso VERO di cartelle speciali come Desktop o
    Menu Start dal registro di Windows, invece di assumere
    %USERPROFILE%\\Desktop: su tanti PC oggi il Desktop e' stato
    spostato dentro OneDrive, e assumere il percorso classico
    manderebbe l'icona in un posto che l'utente non vede piu'."""
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
    )
    try:
        value, _ = winreg.QueryValueEx(key, name)
    finally:
        winreg.CloseKey(key)
    return Path(os.path.expandvars(value))


def _create_shortcut(link_path: Path, target: Path, icon: Path) -> None:
    """Crea un collegamento .lnk usando Windows Script Host
    (cscript.exe), gia' presente su qualunque Windows: evita di dover
    aggiungere una libreria esterna (es. pywin32) solo per questo."""
    vbs_path = link_path.with_suffix(".vbs")
    vbs_content = (
        'Set oWS = WScript.CreateObject("WScript.Shell")\n'
        f'sLinkFile = "{link_path}"\n'
        "Set oLink = oWS.CreateShortcut(sLinkFile)\n"
        f'oLink.TargetPath = "{target}"\n'
        f'oLink.WorkingDirectory = "{target.parent}"\n'
        f'oLink.IconLocation = "{icon}, 0"\n'
        "oLink.Save\n"
    )
    vbs_path.write_text(vbs_content, encoding="utf-8")
    try:
        subprocess.run(
            ["cscript", "//nologo", str(vbs_path)],
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    finally:
        vbs_path.unlink(missing_ok=True)


def main() -> None:
    own_dir = _own_dir()
    source_exe = own_dir / "TUF.exe"

    if not source_exe.exists():
        _msgbox(
            "Non trovo TUF.exe nella stessa cartella di questo installer.\n\n"
            "Assicurati che 'TUF.exe' e 'Installa_TUF.exe' siano copiati "
            "insieme, nella stessa cartella (es. sulla chiavetta USB), "
            "prima di avviare l'installazione.",
            style=MB_OK | MB_ICONERROR,
        )
        sys.exit(1)

    proceed = _msgbox(
        "Questo installer copia TUF nel tuo profilo utente e crea "
        "un'icona sul Desktop.\n\nNon serve essere amministratore, "
        "non modifica altri programmi.\n\nProcedere?",
        style=MB_YESNO | MB_ICONQUESTION,
    )
    if proceed != IDYES:
        return

    try:
        install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "TUF"
        install_dir.mkdir(parents=True, exist_ok=True)
        dest_exe = install_dir / "TUF.exe"
        shutil.copy2(source_exe, dest_exe)

        desktop = _shell_folder("Desktop")
        _create_shortcut(desktop / "TUF.lnk", dest_exe, dest_exe)

        start_menu_programs = _shell_folder("Programs")
        _create_shortcut(start_menu_programs / "TUF.lnk", dest_exe, dest_exe)

    except OSError as e:
        _msgbox(
            f"Installazione non riuscita:\n\n{e}",
            style=MB_OK | MB_ICONERROR,
        )
        sys.exit(1)

    launch_now = _msgbox(
        "TUF e' stato installato! Trovi la sua icona sul Desktop e nel "
        "menu Start.\n\nVuoi avviarlo subito?",
        style=MB_YESNO | MB_ICONQUESTION,
    )
    if launch_now == IDYES:
        subprocess.Popen([str(dest_exe)], cwd=str(install_dir))


if __name__ == "__main__":
    main()
