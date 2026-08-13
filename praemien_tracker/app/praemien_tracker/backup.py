"""Manuelles Datenbank-Backup auf Knopfdruck sowie dessen Wiederherstellung
(siehe routers/backup.py) - analog zum selben Feature im Budget-Tracker
(separates Add-on, siehe auszahlungs_sync.py), dort zuerst gebaut.

sqlite3.Connection.backup() statt reinem Datei-Kopieren: die DB läuft während
des Backups weiter (Scheduler-Läufe, Web-Anfragen), eine rohe Kopie könnte
mitten in einem Schreibvorgang landen. Die Backup-API kopiert Seite für Seite
unter einer Lesesperre und liefert damit immer einen konsistenten Stand.

Der Download bündelt die Datenbank zusätzlich mit options.json (Add-on-
Konfiguration: anthropic_api_key, mindestpraemie, ...) in einem ZIP - die
Optionen stecken nicht in der Datenbank, gehören aber genauso zu einem
vollständigen Wiederherstellungsstand.

wiederherstellen() ist das Gegenstück: ein hochgeladenes Backup (ZIP oder
rohe .db-Datei) ersetzt die laufende Datenbank und, falls im ZIP enthalten,
auch options.json. Die Reihenfolge ist bewusst so gewählt, dass ein Fehler
nie die aktuell laufende Datenbank anfasst - geprüft und auf den aktuellen
Schema-Stand migriert wird ausschließlich eine Kopie außerhalb des Live-
Pfads; erst wenn das gelingt, entsteht ein Sicherheits-Backup des bisherigen
Stands und die Datei wird ausgetauscht. Ein hochgeladenes Backup kann ja von
einer älteren Add-on-Version stammen, mit einem Schema-Stand vor der zuletzt
hinzugekommenen Migration.

Wichtige Einschränkung bei options.json, siehe Warnung dazu in
templates/backup_wiederhergestellt.html: Supervisor schreibt options.json bei
jedem Add-on-Start aus seinem eigenen, hier nicht angefassten
Konfigurationsstand neu - ein Neustart würde die wiederhergestellte Datei
also wieder verwerfen.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config as AlembicConfig

from .config import BACKUP_DIR, DATA_DIR, DB_PATH, OPTIONS_PATH
from .database import engine

APP_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = APP_DIR.parent / "migrations"
ALEMBIC_INI = APP_DIR.parent / "alembic.ini"

# Gleiche Grenze wie im Budget-Tracker-Vorbild - nur die letzten Handvoll
# manuellen Backups aufheben, damit /data nicht unbegrenzt wächst.
MAX_ANZAHL = 10


def erstellen() -> Path:
    """Legt eine frische, konsistente Kopie der aktuellen Datenbank an und
    entfernt anschließend alle bis auf die MAX_ANZAHL jüngsten Backups."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    zeitstempel = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = BACKUP_DIR / f"praemien-{zeitstempel}.db"

    quelle_verbindung = sqlite3.connect(DB_PATH)
    ziel_verbindung = sqlite3.connect(ziel)
    try:
        quelle_verbindung.backup(ziel_verbindung)
    finally:
        ziel_verbindung.close()
        quelle_verbindung.close()

    _alte_backups_aufraeumen()
    return ziel


def _alte_backups_aufraeumen() -> None:
    backups = sorted(BACKUP_DIR.glob("praemien-*.db"), key=lambda p: p.name, reverse=True)
    for alt in backups[MAX_ANZAHL:]:
        alt.unlink(missing_ok=True)


def zip_erstellen() -> tuple[str, bytes]:
    """Frisches DB-Backup + options.json gebündelt als ZIP im Speicher -
    liegt nicht zusätzlich auf der Platte, das eigentliche Backup bleibt
    allein die .db-Datei in BACKUP_DIR (siehe erstellen()).

    Gibt den Downloadnamen und den ZIP-Inhalt zurück."""
    db_pfad = erstellen()
    zeitstempel = db_pfad.stem.removeprefix("praemien-")

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zip_datei:
        zip_datei.write(db_pfad, arcname=db_pfad.name)
        # Fehlt z.B. lokal außerhalb des Add-on-Containers - dann eben nur
        # die Datenbank im ZIP, kein Grund den Download abzubrechen.
        if OPTIONS_PATH.exists():
            zip_datei.write(OPTIONS_PATH, arcname="options.json")

    return f"praemien-tracker-backup-{zeitstempel}.zip", puffer.getvalue()


def wiederherstellen(inhalt: bytes) -> bool:
    """Ersetzt die laufende Datenbank durch ein hochgeladenes Backup und,
    falls im ZIP enthalten, auch options.json.

    Wirft ValueError mit einer für die Oberfläche geeigneten Meldung, wenn
    die Datei kein gültiges Backup ist oder sich nicht migrieren lässt - die
    laufende Datenbank bleibt in dem Fall unangetastet. Beide Teile werden
    vorab geprüft, bevor irgendetwas geschrieben wird, damit ein kaputtes
    options.json nicht eine ansonsten gültige DB-Wiederherstellung zur
    Hälfte durchführt.

    Gibt zurück, ob zusätzlich options.json wiederhergestellt wurde.
    """
    db_bytes, optionen_bytes = _inhalte_extrahieren(inhalt)
    if optionen_bytes is not None:
        _optionen_validieren(optionen_bytes)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    staging = DATA_DIR / f".wiederherstellung-{uuid4().hex}.db"
    staging.write_bytes(db_bytes)
    try:
        if not _ist_praemien_tracker_datenbank(staging):
            raise ValueError("Die hochgeladene Datei ist keine gültige Prämien-Tracker-Datenbank.")
        _auf_aktuellen_stand_migrieren(staging)

        erstellen()  # Sicherheitskopie des noch aktuellen Stands, bevor er weg ist.
        engine.dispose()  # keine gepoolte Verbindung darf die alte Datei noch offen halten.
        staging.replace(DB_PATH)
    finally:
        staging.unlink(missing_ok=True)

    if optionen_bytes is not None:
        OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        options_staging = DATA_DIR / f".wiederherstellung-{uuid4().hex}.json"
        options_staging.write_bytes(optionen_bytes)
        options_staging.replace(OPTIONS_PATH)

    return optionen_bytes is not None


def _inhalte_extrahieren(inhalt: bytes) -> tuple[bytes, bytes | None]:
    """Liest die Datenbank und, falls vorhanden, options.json aus einem
    hochgeladenen ZIP - oder behandelt den Inhalt als rohe .db-Datei ohne
    Konfiguration."""
    if inhalt.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(inhalt)) as zip_datei:
            namen = zip_datei.namelist()
            db_eintraege = [n for n in namen if n.endswith(".db")]
            if len(db_eintraege) != 1:
                raise ValueError("Das ZIP enthält nicht genau eine .db-Datei.")
            db_bytes = zip_datei.read(db_eintraege[0])
            optionen_bytes = zip_datei.read("options.json") if "options.json" in namen else None
            return db_bytes, optionen_bytes
    if inhalt.startswith(b"SQLite format 3\x00"):
        return inhalt, None
    raise ValueError("Die Datei ist weder ein Backup-ZIP noch eine SQLite-Datenbank.")


def _optionen_validieren(optionen_bytes: bytes) -> None:
    try:
        json.loads(optionen_bytes)
    except json.JSONDecodeError as fehler:
        raise ValueError(f"Die enthaltene options.json ist kein gültiges JSON: {fehler}") from fehler


def _ist_praemien_tracker_datenbank(pfad: Path) -> bool:
    try:
        verbindung = sqlite3.connect(pfad)
    except sqlite3.DatabaseError:
        return False
    try:
        ergebnis = verbindung.execute("PRAGMA integrity_check").fetchone()
        if ergebnis is None or ergebnis[0] != "ok":
            return False
        tabellen = {
            zeile[0]
            for zeile in verbindung.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        return {"deals", "banks"} <= tabellen
    except sqlite3.DatabaseError:
        return False
    finally:
        verbindung.close()


def _auf_aktuellen_stand_migrieren(pfad: Path) -> None:
    """Bringt eine (möglicherweise ältere) Datenbank per Alembic auf den
    Schema-Stand dieser Add-on-Version.

    Eigene AlembicConfig statt Wiederverwendung von main.py:_alembic_config()
    - main.py registriert den Backup-Router aus diesem Modul, ein Import in
    die andere Richtung wäre ein Zyklus. migrations/env.py liest die URL
    ausschließlich aus der übergebenen Config (kein fester Import aus
    config.py), das Umbiegen auf die Staging-Datei funktioniert deshalb ohne
    Umweg über einen Subprozess."""
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{pfad}")
    try:
        command.upgrade(cfg, "head")
    except Exception as fehler:
        raise ValueError(
            "Die hochgeladene Datenbank ließ sich nicht auf den aktuellen Stand migrieren "
            f"(vermutlich beschädigt oder kein Prämien-Tracker-Backup): {fehler}"
        ) from fehler
