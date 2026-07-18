@echo off
REM ============================================================
REM  Crea_Installer_TUF.bat — crea i DUE file da consegnare a chi riceve TUF
REM  (Windows). Doppio click e basta: installa tutto il necessario e
REM  genera dentro "dist":
REM    - TUF.exe            (l'app vera e propria, contiene tutto)
REM    - Installa_TUF.exe   (il piccolo installer con l'icona di TUF:
REM                          chi lo riceve fa doppio click SOLO su
REM                          questo, copia TUF nel suo profilo utente
REM                          e crea l'icona sul Desktop da solo)
REM  Vanno consegnati SEMPRE INSIEME, nella stessa cartella (es. sulla
REM  stessa chiavetta USB): Installa_TUF.exe cerca TUF.exe accanto a
REM  se stesso.
REM ============================================================

setlocal

echo.
echo === TUF - creazione di TUF.exe e Installa_TUF.exe ===
echo.

REM --- controlla che Python sia installato ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] Python non trovato. Installalo da https://www.python.org/downloads/
    echo          ^(durante l'installazione, spunta "Add python.exe to PATH"^)
    pause
    exit /b 1
)

echo [1/5] Installo le librerie necessarie di TUF...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRORE] Installazione librerie fallita. Controlla il messaggio sopra.
    pause
    exit /b 1
)

echo.
echo [2/5] Installo PyInstaller ^(serve per creare i file .exe^)...
python -m pip install pyinstaller
if errorlevel 1 (
    echo [ERRORE] Installazione PyInstaller fallita.
    pause
    exit /b 1
)

echo.
echo [3/5] Pulisco eventuali build precedenti...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist TUF.spec del /q TUF.spec
if exist Installa_TUF.spec del /q Installa_TUF.spec

echo.
echo [4/5] Creo TUF.exe ^(puo' richiedere qualche minuto^)...
python -m PyInstaller --onefile --windowed --name TUF ^
    --icon "filepilot\assets\tuf_icon.ico" ^
    --add-data "filepilot/assets;filepilot/assets" ^
    --add-data "TERMINI_E_CONDIZIONI.pdf;." ^
    --add-data "PRIVACY.md;." ^
    filepilot\main.py

if errorlevel 1 (
    echo.
    echo [ERRORE] La creazione di TUF.exe e' fallita. Controlla il messaggio sopra.
    pause
    exit /b 1
)

echo.
echo [5/5] Creo Installa_TUF.exe ^(il piccolo installer con l'icona^)...
python -m PyInstaller --onefile --windowed --name Installa_TUF ^
    --icon "filepilot\assets\tuf_icon.ico" ^
    install_tuf.py

if errorlevel 1 (
    echo.
    echo [ERRORE] La creazione di Installa_TUF.exe e' fallita. Controlla il messaggio sopra.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  FATTO! Dentro la cartella "dist" trovi DUE file:
echo    - TUF.exe
echo    - Installa_TUF.exe
echo  Prendili ENTRAMBI (nella stessa cartella) e mandali a chi vuoi
echo  far provare TUF: dira' doppio click solo su Installa_TUF.exe,
echo  che si occupa di tutto il resto da solo.
echo ============================================================
echo.
pause
