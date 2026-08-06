"""finder/matching.py - die deterministische Prüfung, ohne KI und ohne
Netzwerk (die Extraktion wird hier direkt als AngebotExtraktion vorgegeben)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from praemien_tracker.finder import matching
from praemien_tracker.finder.extraktion import AngebotExtraktion, BedingungExtraktion
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.models import Bank, Deal, DealVorschlag, Inhaber
from praemien_tracker.schemas import DealImport

MINDESTPRAEMIE = Decimal("50")


@pytest.fixture()
def Alice(db):
    inhaber = Inhaber(name="Alice")
    db.add(inhaber)
    db.commit()
    return inhaber


def _monat_vor(monate: int, heute: datetime.date | None = None) -> str:
    heute = heute or datetime.date.today()
    jahr, monat = heute.year, heute.month - monate
    while monat <= 0:
        monat += 12
        jahr -= 1
    return f"{jahr:04d}-{monat:02d}"


def test_echter_neukunde_wird_vorgeschlagen(db, Alice):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "x")
    ext = AngebotExtraktion(
        bank_name="C24",
        kontoart="Girokonto",
        praemie_betrag=125.0,
        bedingungen=[BedingungExtraktion(beschreibung="3 Kartenzahlungen", einschaetzung="erfuellt")],
    )
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_VORGESCHLAGEN
    assert ergebnis.ablehnungsgruende is None
    # roh_json muss unverändert vom bestehenden JSON-Import validiert werden
    # können (Konzept: "Übernehmen" nutzt genau diesen Mechanismus).
    DealImport.model_validate_json(ergebnis.roh_json)


def test_praemie_unter_mindestbetrag_wird_abgelehnt(db, Alice):
    fund = RohFund("mydealz", "https://mydealz.de/norwegian", "t", "x")
    ext = AngebotExtraktion(bank_name="Bank Norwegian", kontoart="Kreditkarte", praemie_betrag=15.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "Mindestprämie" in ergebnis.ablehnungsgruende


def test_zwingender_gehaltseingang_wird_abgelehnt(db, Alice):
    fund = RohFund("spartanien", "https://spartanien.de/consors", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Consorsbank",
        kontoart="Depot",
        praemie_betrag=80.0,
        bedingungen=[
            BedingungExtraktion(beschreibung="Gehaltseingang von mind. 1000€", einschaetzung="nicht_erfuellt")
        ],
    )
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "Gehaltseingang" in ergebnis.ablehnungsgruende


def test_unklare_bedingung_fuehrt_zu_pruefen_nicht_zu_ablehnung(db, Alice):
    """Zentrale Idee des Konzepts: im Zweifel eher vorschlagen als
    ausschließen."""
    fund = RohFund("mydealz", "https://mydealz.de/unklar", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Testbank",
        kontoart="Girokonto",
        praemie_betrag=100.0,
        bedingungen=[BedingungExtraktion(beschreibung="regelmäßiger Geldeingang", einschaetzung="zu_pruefen")],
    )
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ZU_PRUEFEN
    assert "unklar" in ergebnis.ablehnungsgruende.lower() or "regelmäßiger" in ergebnis.ablehnungsgruende


def test_sperrfrist_noch_nicht_erreicht_wird_abgelehnt(db, Alice):
    santander = Bank(name="Santander")
    db.add(santander)
    db.commit()
    db.add(
        Deal(
            bank=santander,
            inhaber=Alice,
            kontoart="Girokonto",
            gekuendigt=True,
            gekuendigt_im_monat=_monat_vor(3),
        )
    )
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/santander", "t", "x")
    ext = AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=12, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "Sperrfrist" in ergebnis.ablehnungsgruende


def test_sperrfrist_erreicht_wird_vorgeschlagen(db, Alice):
    santander = Bank(name="Santander")
    db.add(santander)
    db.commit()
    db.add(
        Deal(
            bank=santander,
            inhaber=Alice,
            kontoart="Girokonto",
            gekuendigt=True,
            gekuendigt_im_monat=_monat_vor(13),
        )
    )
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/santander", "t", "x")
    ext = AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=12, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_VORGESCHLAGEN


def test_unbekannte_sperrfrist_fuehrt_zu_pruefen(db, Alice):
    bank = Bank(name="Testbank")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=Alice, kontoart="Girokonto", gekuendigt=True, gekuendigt_im_monat=_monat_vor(3)))
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/testbank", "t", "x")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=None, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ZU_PRUEFEN


def test_bereits_aktiver_kunde_ohne_kuendigung_wird_abgelehnt(db, Alice):
    bank = Bank(name="Testbank")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=Alice, kontoart="Girokonto", gekuendigt=False))
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/testbank2", "t", "x")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "bereits Kundin" in ergebnis.ablehnungsgruende


def test_stornierter_deal_zaehlt_nicht_als_vorkunde(db, Alice):
    """Analog zum Kernmodell (Deal.storniert): ein Deal, der nie zustande kam,
    darf die Sperrfristen-Prüfung nicht beeinflussen."""
    bank = Bank(name="Testbank")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=Alice, kontoart="Girokonto", gekuendigt=True, storniert=True))
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/testbank3", "t", "x")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_VORGESCHLAGEN


def test_mydealz_quelle_wird_beim_uebernehmen_auf_bank_gemappt(db, Alice):
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    daten = DealImport.model_validate_json(ergebnis.roh_json)
    assert daten.praemien[0].quelle == "bank"
    assert daten.urls[0].url == fund.quelle_url


def test_spartanien_quelle_bleibt_spartanien(db, Alice):
    fund = RohFund("spartanien", "https://spartanien.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    daten = DealImport.model_validate_json(ergebnis.roh_json)
    assert daten.praemien[0].quelle == "spartanien"


def test_dedup_erkennt_unveraenderten_fund(db, Alice):
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, Alice, MINDESTPRAEMIE)
    assert not matching.ist_duplikat(db, fund.quelle_url, Alice.id, ergebnis.inhalt_hash)

    db.add(
        DealVorschlag(
            inhaber_id=Alice.id,
            quelle=fund.quelle,
            quelle_url=fund.quelle_url,
            bank_name=ext.bank_name,
            kontoart=ext.kontoart,
            praemie_betrag=ergebnis.praemie_betrag,
            sperrfrist_monate=ergebnis.sperrfrist_monate,
            ablehnungsgruende=ergebnis.ablehnungsgruende,
            roh_json=ergebnis.roh_json,
            inhalt_hash=ergebnis.inhalt_hash,
            status=ergebnis.status,
        )
    )
    db.commit()

    assert matching.ist_duplikat(db, fund.quelle_url, Alice.id, ergebnis.inhalt_hash)


def test_geaenderte_praemie_ist_kein_duplikat(db, Alice):
    """Explizite Entscheidung: bei geänderten Daten (z.B. höhere Prämie)
    entsteht ein neuer Datensatz statt eines stillen Updates."""
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext_alt = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis_alt = matching.bewerten(db, fund, ext_alt, Alice, MINDESTPRAEMIE)
    db.add(
        DealVorschlag(
            inhaber_id=Alice.id,
            quelle=fund.quelle,
            quelle_url=fund.quelle_url,
            bank_name=ext_alt.bank_name,
            kontoart=ext_alt.kontoart,
            praemie_betrag=ergebnis_alt.praemie_betrag,
            sperrfrist_monate=ergebnis_alt.sperrfrist_monate,
            ablehnungsgruende=ergebnis_alt.ablehnungsgruende,
            roh_json=ergebnis_alt.roh_json,
            inhalt_hash=ergebnis_alt.inhalt_hash,
            status=ergebnis_alt.status,
        )
    )
    db.commit()

    ext_neu = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=150.0, bedingungen=[])
    ergebnis_neu = matching.bewerten(db, fund, ext_neu, Alice, MINDESTPRAEMIE)
    assert ergebnis_neu.inhalt_hash != ergebnis_alt.inhalt_hash
    assert not matching.ist_duplikat(db, fund.quelle_url, Alice.id, ergebnis_neu.inhalt_hash)
