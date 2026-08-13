"""backup.py + die Download-/Upload-Endpunkte (routers/backup.py).

Zusammen in einer Datei, weil die Endpunkte nur dünne Wrapper um
zip_erstellen()/wiederherstellen() sind - eigene Tests dafür würden denselben
Fall doppelt prüfen.

_auf_aktuellen_stand_migrieren() wird in den wiederherstellen()-Tests
gemockt: die "db"-Fixture baut das Schema über Base.metadata.create_all()
statt über echte Alembic-Migrationen auf (siehe conftest.py) und legt dabei
keine alembic_version-Tabelle an - ein echter "alembic upgrade head"-Lauf
gegen eine Kopie davon würde beim Versuch, bereits vorhandene Tabellen erneut
anzulegen, fehlschlagen. Dass die Migration selbst funktioniert, prüft
test_migrieren_bringt_leere_datei_auf_aktuellen_schema_stand für sich.
"""
from __future__ import annotations

import json
import sqlite3
import zipfile
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient

from praemien_tracker import backup
from praemien_tracker.config import BACKUP_DIR, DB_PATH
from praemien_tracker.main import app as fastapi_app
from praemien_tracker.models import Bank


@pytest.fixture
def client():
    return TestClient(fastapi_app)


@pytest.fixture
def baenke(db):
    """Ein paar Banken - schlanke, unabhängige Tabelle, gut geeignet, um
    zu prüfen, ob wiederherstellen() tatsächlich den hochgeladenen Stand
    übernimmt."""
    for name in ("Testbank Eins", "Testbank Zwei", "Testbank Drei"):
        db.add(Bank(name=name))
    db.commit()
    return db.query(Bank).all()


def test_erstellen_legt_datei_im_backup_verzeichnis_an(db):
    pfad = backup.erstellen()

    assert pfad.parent == BACKUP_DIR
    assert pfad.exists()
    assert pfad.name.startswith("praemien-")


def test_erstellen_liefert_konsistente_kopie_der_aktuellen_daten(db, baenke):
    pfad = backup.erstellen()

    kopie = sqlite3.connect(pfad)
    try:
        anzahl = kopie.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
    finally:
        kopie.close()
    assert anzahl == len(baenke)


def test_aufraeumen_behaelt_nur_die_juengsten_backups(db):
    # Direkt präparierte Dateinamen statt vier echter erstellen()-Aufrufe:
    # der Zeitstempel hat nur Sekundenauflösung, in einem schnellen Testlauf
    # würden mehrere Aufrufe denselben Dateinamen erzeugen und sich
    # gegenseitig überschreiben statt die Aufräum-Logik zu prüfen.
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for alt in BACKUP_DIR.glob("praemien-*.db"):
        alt.unlink()
    namen = [f"praemien-2026081{i}-000000.db" for i in range(4)]
    for name in namen:
        (BACKUP_DIR / name).write_bytes(b"")

    alte_grenze = backup.MAX_ANZAHL
    try:
        backup.MAX_ANZAHL = 2
        backup._alte_backups_aufraeumen()
    finally:
        backup.MAX_ANZAHL = alte_grenze

    vorhandene = {p.name for p in BACKUP_DIR.glob("praemien-*.db")}
    assert vorhandene == {namen[-1], namen[-2]}


def test_zip_erstellen_enthaelt_datenbank_und_optionen(db):
    backup.OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup.OPTIONS_PATH.write_text(json.dumps({"demo_modus": False}), encoding="utf-8")
    try:
        dateiname, inhalt = backup.zip_erstellen()

        assert dateiname.startswith("praemien-tracker-backup-")
        assert dateiname.endswith(".zip")
        with zipfile.ZipFile(BytesIO(inhalt)) as zip_datei:
            namen = zip_datei.namelist()
            assert "options.json" in namen
            assert any(n.startswith("praemien-") and n.endswith(".db") for n in namen)
            optionen = json.loads(zip_datei.read("options.json"))
            assert optionen == {"demo_modus": False}
    finally:
        backup.OPTIONS_PATH.unlink(missing_ok=True)


def test_zip_erstellen_ohne_options_json_enthaelt_nur_datenbank(db):
    backup.OPTIONS_PATH.unlink(missing_ok=True)

    _, inhalt = backup.zip_erstellen()

    with zipfile.ZipFile(BytesIO(inhalt)) as zip_datei:
        assert zip_datei.namelist() == [n for n in zip_datei.namelist() if n.endswith(".db")]


def test_download_endpunkt_liefert_zip_mit_datenbank(client, db):
    antwort = client.get("/backup/herunterladen")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "application/zip"
    assert "attachment" in antwort.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(antwort.content)) as zip_datei:
        assert any(n.endswith(".db") for n in zip_datei.namelist())


def _banken_anzahl_live() -> int:
    """Zählt Banken über eine frische sqlite3-Verbindung, nicht über die
    "db"-Fixture-Session - deren Verbindung kann nach einem Dateitausch durch
    wiederherstellen() noch den alten, inzwischen ausgehängten Dateiinhalt
    sehen (offenes File-Handle unter POSIX überlebt den Austausch)."""
    verbindung = sqlite3.connect(DB_PATH)
    try:
        return verbindung.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
    finally:
        verbindung.close()


@pytest.fixture
def migration_ueberspringen(monkeypatch):
    """_auf_aktuellen_stand_migrieren() gemockt - siehe Modul-Docstring."""
    monkeypatch.setattr(backup, "_auf_aktuellen_stand_migrieren", lambda pfad: None)


def test_wiederherstellen_ersetzt_live_datenbank(db, baenke, migration_ueberspringen):
    vorher_bytes = backup.erstellen().read_bytes()

    for b in db.query(Bank).all():
        db.delete(b)
    db.commit()
    assert _banken_anzahl_live() == 0

    backup.wiederherstellen(vorher_bytes)

    assert _banken_anzahl_live() == len(baenke)


def test_wiederherstellen_legt_zuvor_sicherheitsbackup_an(db, baenke, monkeypatch, migration_ueberspringen):
    vorher_bytes = backup.erstellen().read_bytes()
    aufrufe = []
    echtes_erstellen = backup.erstellen
    monkeypatch.setattr(backup, "erstellen", lambda: aufrufe.append(1) or echtes_erstellen())

    backup.wiederherstellen(vorher_bytes)

    assert aufrufe, "erstellen() hätte als Sicherheitskopie aufgerufen werden müssen"


def test_wiederherstellen_akzeptiert_zip(db, baenke, migration_ueberspringen):
    _, zip_bytes = backup.zip_erstellen()

    for b in db.query(Bank).all():
        db.delete(b)
    db.commit()
    assert _banken_anzahl_live() == 0

    backup.wiederherstellen(zip_bytes)

    assert _banken_anzahl_live() == len(baenke)


def test_wiederherstellen_lehnt_ungueltige_datei_ab(db, baenke, migration_ueberspringen):
    with pytest.raises(ValueError):
        backup.wiederherstellen(b"das ist kein Backup")

    assert _banken_anzahl_live() == len(baenke)


def test_wiederherstellen_lehnt_zip_ohne_db_datei_ab(db, migration_ueberspringen):
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, "w") as zip_datei:
        zip_datei.writestr("options.json", "{}")

    with pytest.raises(ValueError):
        backup.wiederherstellen(puffer.getvalue())


def test_wiederherstellen_lehnt_sqlite_datei_ohne_erwartete_tabellen_ab(db, tmp_path, migration_ueberspringen):
    # Eine echte, gültige SQLite-Datei - aber keine Prämien-Tracker-Datenbank,
    # die erwarteten Tabellen fehlen.
    fremde_datei = tmp_path / "fremd.db"
    verbindung = sqlite3.connect(fremde_datei)
    verbindung.execute("CREATE TABLE irgendwas (id INTEGER)")
    verbindung.commit()
    verbindung.close()

    with pytest.raises(ValueError):
        backup.wiederherstellen(fremde_datei.read_bytes())


def test_wiederherstellen_bricht_bei_fehlgeschlagener_migration_ab(db, baenke, monkeypatch):
    vorher_bytes = backup.erstellen().read_bytes()
    monkeypatch.setattr(
        backup,
        "_auf_aktuellen_stand_migrieren",
        lambda pfad: (_ for _ in ()).throw(ValueError("Migration kaputt")),
    )

    with pytest.raises(ValueError):
        backup.wiederherstellen(vorher_bytes)

    assert _banken_anzahl_live() == len(baenke)


def test_migrieren_bringt_leere_datei_auf_aktuellen_schema_stand(tmp_path):
    """Echter Alembic-Lauf (kein Mock) gegen eine noch nicht existierende
    Datei - im Unterschied zu einer per create_all() gebauten Test-DB gibt es
    hier keine bereits vorhandenen Tabellen, die die Migration stören."""
    ziel = tmp_path / "frisch.db"

    backup._auf_aktuellen_stand_migrieren(ziel)

    verbindung = sqlite3.connect(ziel)
    try:
        tabellen = {
            zeile[0]
            for zeile in verbindung.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        verbindung.close()
    assert {"deals", "banks", "alembic_version"} <= tabellen


def test_wiederherstellen_endpunkt_erfolgreich(client, db, migration_ueberspringen):
    _, zip_bytes = backup.zip_erstellen()

    antwort = client.post(
        "/backup/wiederherstellen",
        files={"datei": ("backup.zip", zip_bytes, "application/zip")},
    )

    assert antwort.status_code == 200
    assert "wiederhergestellt" in antwort.text.lower()


def test_wiederherstellen_endpunkt_lehnt_ungueltige_datei_ab(client, db):
    antwort = client.post(
        "/backup/wiederherstellen",
        files={"datei": ("kaputt.db", b"kein sqlite", "application/octet-stream")},
    )

    assert antwort.status_code == 400


def _zip_bauen(db_bytes: bytes, optionen: str | None) -> bytes:
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, "w") as zip_datei:
        zip_datei.writestr("praemien-test.db", db_bytes)
        if optionen is not None:
            zip_datei.writestr("options.json", optionen)
    return puffer.getvalue()


def test_wiederherstellen_uebernimmt_options_json_aus_zip(db, monkeypatch, migration_ueberspringen):
    # SUPERVISOR_TOKEN bewusst nicht gesetzt: dieser Test prüft nur die
    # lokale Übernahme, die dauerhafte Übernahme via Supervisor-API hat
    # eigene Tests weiter unten.
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    db_bytes = backup.erstellen().read_bytes()
    zip_bytes = _zip_bauen(db_bytes, json.dumps({"mindestpraemie": 75}))

    try:
        konfiguration_wiederhergestellt, konfiguration_dauerhaft = backup.wiederherstellen(zip_bytes)

        assert konfiguration_wiederhergestellt is True
        assert konfiguration_dauerhaft is False
        assert json.loads(backup.OPTIONS_PATH.read_text()) == {"mindestpraemie": 75}
    finally:
        backup.OPTIONS_PATH.unlink(missing_ok=True)


def test_wiederherstellen_ohne_options_json_gibt_false_zurueck(db, migration_ueberspringen):
    db_bytes = backup.erstellen().read_bytes()
    zip_bytes = _zip_bauen(db_bytes, optionen=None)

    assert backup.wiederherstellen(zip_bytes) == (False, False)


def test_wiederherstellen_rohe_db_datei_gibt_false_zurueck(db, migration_ueberspringen):
    db_bytes = backup.erstellen().read_bytes()

    assert backup.wiederherstellen(db_bytes) == (False, False)


def test_supervisor_optionen_setzen_ohne_token_gibt_false_zurueck(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    assert backup._supervisor_optionen_setzen({"demo_modus": True}) is False


def test_supervisor_optionen_setzen_erfolgreich(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []

    def gefakter_post(url, *, headers, json, timeout):
        aufrufe.append((url, headers, json))
        assert url == backup.SUPERVISOR_OPTIONS_URL
        assert headers["Authorization"] == "Bearer geheim"
        return httpx.Response(200, json={"result": "ok"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(backup.httpx, "post", gefakter_post)

    assert backup._supervisor_optionen_setzen({"demo_modus": True}) is True
    assert aufrufe == [
        (backup.SUPERVISOR_OPTIONS_URL, aufrufe[0][1], {"options": {"demo_modus": True}})
    ]


def test_supervisor_optionen_setzen_bei_ablehnung_false(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    monkeypatch.setattr(
        backup.httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200,
            json={"result": "error", "message": "Unbekannte Option"},
            request=httpx.Request("POST", url),
        ),
    )

    assert backup._supervisor_optionen_setzen({"veraltete_option": True}) is False


def test_supervisor_optionen_setzen_bei_netzwerkfehler_false(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")

    def kaputter_post(url, **kwargs):
        raise httpx.ConnectError("nicht erreichbar")

    monkeypatch.setattr(backup.httpx, "post", kaputter_post)

    assert backup._supervisor_optionen_setzen({"demo_modus": True}) is False


def test_wiederherstellen_uebernimmt_konfiguration_dauerhaft_bei_erfolgreicher_supervisor_api(
    db, monkeypatch, migration_ueberspringen
):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    monkeypatch.setattr(backup, "_supervisor_optionen_setzen", lambda optionen: True)
    db_bytes = backup.erstellen().read_bytes()
    zip_bytes = _zip_bauen(db_bytes, json.dumps({"demo_modus": True}))

    try:
        ergebnis = backup.wiederherstellen(zip_bytes)

        assert ergebnis == (True, True)
    finally:
        backup.OPTIONS_PATH.unlink(missing_ok=True)


def test_wiederherstellen_lehnt_ungueltiges_json_in_optionen_ab(db, baenke, migration_ueberspringen):
    backup.OPTIONS_PATH.unlink(missing_ok=True)
    db_bytes = backup.erstellen().read_bytes()
    zip_bytes = _zip_bauen(db_bytes, optionen="{kaputtes json")

    with pytest.raises(ValueError):
        backup.wiederherstellen(zip_bytes)

    # Weder DB noch Optionen wurden angefasst - die Prüfung läuft vor jedem Schreibzugriff.
    assert _banken_anzahl_live() == len(baenke)
    assert not backup.OPTIONS_PATH.exists()


def test_wiederherstellen_endpunkt_uebergibt_konfiguration_wiederhergestellt_an_vorlage(
    client, db, migration_ueberspringen
):
    db_bytes = backup.erstellen().read_bytes()
    zip_bytes = _zip_bauen(db_bytes, json.dumps({"demo_modus": False}))

    try:
        antwort = client.post(
            "/backup/wiederherstellen",
            files={"datei": ("backup.zip", zip_bytes, "application/zip")},
        )

        assert antwort.status_code == 200
        assert "options.json" in antwort.text
    finally:
        backup.OPTIONS_PATH.unlink(missing_ok=True)
