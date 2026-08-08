"""Tests für Normalisierung, Monatsformat, Zeitanzeige und Fremdschlüssel."""

from __future__ import annotations

import datetime
import pytest
import sqlalchemy

from praemien_tracker import derived
from praemien_tracker.schemas import DealImport, PraemieIn
from praemien_tracker.templating import format_zeitpunkt

# --- Quelle (B11) --------------------------------------------------------


@pytest.mark.parametrize(
    "eingabe, erwartet",
    [
        ("spartanien", "spartanien"),
        ("Spartanien", "spartanien"),
        (" SPARTANIEN ", "spartanien"),
        ("bank", "bank"),
        ("Bank", "bank"),
        ("Kombi", None),
        ("", None),
        (None, None),
    ],
)
def test_quelle_normalisieren(eingabe, erwartet):
    assert derived.normalisiere_quelle(eingabe) == erwartet


def test_schema_verzeiht_schreibweise():
    assert PraemieIn(quelle="Bank", betrag=1).quelle == "bank"


def test_schema_weist_unbekannte_quelle_ab():
    """Fachlich gibt es nur zwei Quellen - alles andere ist ein Schreibfehler
    und würde beim nächsten Speichern still zu "spartanien" umgedeutet."""
    with pytest.raises(ValueError):
        PraemieIn(quelle="Kombi", betrag=1)


# --- Monatsformat (B12) --------------------------------------------------


@pytest.mark.parametrize(
    "eingabe, erwartet",
    [
        ("2026-07", datetime.date(2026, 7, 1)),
        ("2026-7", datetime.date(2026, 7, 1)),
        ("07.26", datetime.date(2026, 7, 1)),
        ("5.26", datetime.date(2026, 5, 1)),
        ("12.2024", datetime.date(2024, 12, 1)),
        ("2026-13", None),
        ("13.26", None),
        ("quatsch", None),
        ("2026", None),
        ("", None),
        (None, None),
    ],
)
def test_monat_parsen(eingabe, erwartet):
    assert derived.parse_monat(eingabe) == erwartet


def test_altes_format_bleibt_lesbar():
    """Bewusst tolerant beim Lesen: ein nach der Migration übrig gebliebener
    MM.YY-Wert darf nicht lautlos als "kein Datum" gelten, sonst fällt der
    Deal aus der Sperrfristen-Auswertung."""
    assert derived.parse_monat("03.25") == datetime.date(2025, 3, 1)


def test_geschrieben_wird_nur_iso():
    assert derived.format_monat(datetime.date(2026, 5, 1)) == "2026-05"


def test_monat_wird_beim_import_auf_iso_gebracht():
    deal = DealImport(bank="X", kontoart="Depot", inhaber="Max", gekuendigt_im_monat="05.26")
    assert deal.gekuendigt_im_monat == "2026-05"


def test_unlesbarer_monat_wird_beim_import_abgewiesen():
    with pytest.raises(ValueError):
        DealImport(bank="X", kontoart="Depot", inhaber="Max", gekuendigt_im_monat="quatsch")


def test_auszahlung_erwartet_wird_ebenfalls_geprueft():
    assert PraemieIn(quelle="bank", betrag=1, auszahlung_erwartet="8.26").auszahlung_erwartet == "2026-08"
    with pytest.raises(ValueError):
        PraemieIn(quelle="bank", betrag=1, auszahlung_erwartet="irgendwann")


# --- Zeitanzeige (B14) ---------------------------------------------------


def test_gespeicherte_utc_wird_in_ortszeit_angezeigt():
    """Gespeichert wird UTC (func.now/CURRENT_TIMESTAMP), angezeigt Ortszeit."""
    utc_wert = datetime.datetime(2026, 7, 30, 16, 31, 39)
    berlin = datetime.timezone(datetime.timedelta(hours=2))
    erwartet = utc_wert.replace(tzinfo=datetime.timezone.utc).astimezone(berlin)
    ausgabe = format_zeitpunkt(utc_wert)
    # Ohne feste Zeitzone im Testlauf wird nur die Umrechnung selbst geprüft.
    if datetime.datetime.now().astimezone().utcoffset() == berlin.utcoffset(None):
        assert ausgabe == erwartet.strftime("%d.%m.%Y %H:%M:%S")
    assert ausgabe.endswith(":39")


def test_zeitpunkt_ohne_wert():
    assert format_zeitpunkt(None) == "–"


# --- Vollständigkeit (B1) ------------------------------------------------


def test_kuendbar_ab_ist_kein_wuenschenswertes_feld():
    """Ein leeres Feld bedeutet "keine Sperrfrist" und ist damit keine Lücke."""
    assert "kuendbar_ab" not in derived.WUENSCHENSWERTE_FELDER


# --- Fremdschlüssel (A12) -----------------------------------------------


def test_fremdschluessel_sind_aktiv(db):
    assert db.execute(sqlalchemy.text("PRAGMA foreign_keys")).scalar() == 1


def test_waise_wird_abgewiesen(db):
    """Eine Prämie ohne zugehörigen Deal würde in keiner Ansicht auftauchen."""
    from praemien_tracker.models import Praemie

    db.add(Praemie(deal_id=99999, quelle="bank", betrag=5))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()


def test_loeschen_eines_deals_funktioniert_mit_fremdschluesseln(db):
    """Mit aktivem PRAGMA foreign_keys darf das Löschen eines Deals nicht an
    seinen Kindern scheitern - SQLAlchemy muss sie zuerst entfernen. Genau
    das tut die Route deal_delete."""
    from praemien_tracker.helpers import build_deal_from_import
    from praemien_tracker.models import Aufgabe, Bedingung, Deal, DealUrl, Praemie

    build_deal_from_import(
        db,
        DealImport(
            bank="Loeschbank",
            kontoart="Depot",
            inhaber="Max",
            praemien=[{"quelle": "bank", "betrag": 10}],
            bedingungen=[{"beschreibung": "b"}],
            aufgaben=[{"beschreibung": "a"}],
            urls=[{"url": "https://x"}],
        ),
    )
    db.commit()

    db.delete(db.query(Deal).one())
    db.commit()

    assert db.query(Deal).count() == 0
    for modell in (Praemie, Bedingung, Aufgabe, DealUrl):
        assert db.query(modell).count() == 0


def test_bank_wird_beim_import_trotz_abweichender_schreibweise_wiederverwendet(db):
    """get_or_create_bank soll "SMARTBROKER" und "Smart Broker" als dieselbe
    Bank erkennen - sonst entstehen beim Übernehmen eines KI-Vorschlags mit
    leicht abweichender Schreibweise doppelte Bank-Datensätze."""
    from praemien_tracker.helpers import build_deal_from_import
    from praemien_tracker.models import Bank

    build_deal_from_import(db, DealImport(bank="Smart Broker", kontoart="Depot", inhaber="Max"))
    db.commit()

    build_deal_from_import(db, DealImport(bank="SMARTBROKER", kontoart="Girokonto", inhaber="Max"))
    db.commit()

    assert db.query(Bank).count() == 1
