"""finder/matching.py - die deterministische Prüfung, ohne KI und ohne
Netzwerk (die Extraktion wird hier direkt als AngebotExtraktion vorgegeben)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from praemien_tracker.finder import matching
from praemien_tracker.finder.extraktion import AngebotExtraktion, BedingungExtraktion, PraemieExtraktion
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.models import Bank, Deal, DealVorschlag, Inhaber
from praemien_tracker.schemas import DealImport

MINDESTPRAEMIE = Decimal("50")


@pytest.fixture()
def alice(db):
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


def test_echter_neukunde_wird_vorgeschlagen(db, alice):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "x")
    ext = AngebotExtraktion(
        bank_name="C24",
        kontoart="Girokonto",
        praemie_betrag=125.0,
        bedingungen=[BedingungExtraktion(beschreibung="3 Kartenzahlungen", einschaetzung="erfuellt")],
    )
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_VORGESCHLAGEN
    assert ergebnis.ablehnungsgruende is None
    # roh_json muss unverändert vom bestehenden JSON-Import validiert werden
    # können (Konzept: "Übernehmen" nutzt genau diesen Mechanismus).
    DealImport.model_validate_json(ergebnis.roh_json)


def test_bedingung_kennzahlen_landen_in_bewertung_und_roh_json(db, alice):
    """Die strukturierten Kennzahlen einer Bedingung (Anzahl/Betrag/Frist)
    fließen in die Bewertung und ins roh_json, damit sie über 'Übernehmen'
    bis zur späteren Bedingung erhalten bleiben (awa7-Fall)."""
    fund = RohFund("dealdoktor", "https://www.dealdoktor.de/awa7-bonus-deal/", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Hanseatic Bank",
        kontoart="Kreditkarte",
        praemie_betrag=50.0,
        bedingungen=[
            BedingungExtraktion(
                beschreibung="Karte innerhalb von 4 Wochen mindestens 2x für insgesamt 50 € einsetzen",
                einschaetzung="erfuellt",
                anzahl=2,
                betrag_euro=50.0,
                frist_wochen=4,
            )
        ],
    )
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)

    (bewertet,) = ergebnis.bedingungen
    assert bewertet.anzahl == 2
    assert bewertet.betrag_euro == Decimal("50")
    assert bewertet.frist_wochen == 4

    daten = DealImport.model_validate_json(ergebnis.roh_json)
    (bed_in,) = daten.bedingungen
    assert bed_in.anzahl == 2
    assert bed_in.betrag_euro == Decimal("50")
    assert bed_in.frist_wochen == 4


def test_bedingung_gilt_fuer_landet_in_bewertung_und_roh_json(db, alice):
    """Teilprämien-Zuordnung einer Bedingung (Santander: 250 € nur für den
    Kontowechselservice) fließt in Bewertung und roh_json - eine
    Grundvoraussetzung bleibt ohne Label."""
    fund = RohFund("spartanien", "https://www.spartanien.de/Santander+BestGiro", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Santander",
        kontoart="Girokonto",
        praemie_betrag=300.0,
        praemien=[
            PraemieExtraktion(betrag=50.0, geber="Spartanien", wofuer="für die Kontoeröffnung"),
            PraemieExtraktion(betrag=250.0, geber="Santander", wofuer="für den Kontowechselservice"),
        ],
        bedingungen=[
            BedingungExtraktion(beschreibung="Neukunde sein", einschaetzung="erfuellt"),
            BedingungExtraktion(
                beschreibung="Kontowechselservice nutzen",
                einschaetzung="zu_pruefen",
                gilt_fuer="250 € für den Kontowechselservice",
            ),
        ],
    )
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)

    nach_beschreibung = {b.beschreibung: b for b in ergebnis.bedingungen}
    assert nach_beschreibung["Neukunde sein"].gilt_fuer is None
    assert nach_beschreibung["Kontowechselservice nutzen"].gilt_fuer == "250 € für den Kontowechselservice"

    daten = DealImport.model_validate_json(ergebnis.roh_json)
    labels = {b.beschreibung: b.gilt_fuer for b in daten.bedingungen}
    assert labels["Kontowechselservice nutzen"] == "250 € für den Kontowechselservice"
    assert labels["Neukunde sein"] is None


def test_mehrere_teilpraemien_werden_aufgeschluesselt_und_summiert(db, alice):
    """Beispiel Santander: 50 EUR von Spartanien für die Kontoeröffnung + 250
    EUR von der Bank für den Kontowechselservice. Gesamtprämie = Summe, jede
    Teilprämie einzeln (mit Geber/Bedingung) sichtbar, und im roh_json die
    kanonische Quelle je Teilprämie (spartanien/bank)."""
    fund = RohFund("spartanien", "https://www.spartanien.de/Santander+BestGiro", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Santander",
        kontoart="Girokonto",
        praemie_betrag=300.0,
        praemien=[
            PraemieExtraktion(betrag=50.0, geber="Spartanien", wofuer="für die Kontoeröffnung"),
            PraemieExtraktion(betrag=250.0, geber="Santander", wofuer="für den Kontowechselservice"),
        ],
        bedingungen=[],
    )
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)

    assert ergebnis.praemie_betrag == Decimal("300.00")
    assert len(ergebnis.praemien) == 2
    assert ergebnis.praemien[0].betrag == Decimal("50.00")
    assert ergebnis.praemien[0].geber == "Spartanien"
    assert ergebnis.praemien[0].bedingung == "für die Kontoeröffnung"

    daten = DealImport.model_validate_json(ergebnis.roh_json)
    quellen = {(p.betrag, p.quelle) for p in daten.praemien}
    assert quellen == {(Decimal("50"), "spartanien"), (Decimal("250"), "bank")}


def test_einzelpraemie_ohne_aufteilung_bleibt_eine_zeile(db, alice):
    """Ohne KI-Aufteilung (praemien leer) genau eine Teilprämie über die
    Gesamtsumme - die Karte zeigt dann keine Aufschlüsselung."""
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.praemie_betrag == Decimal("125.00")
    assert len(ergebnis.praemien) == 1
    assert ergebnis.praemien[0].geber is None


def test_praemie_unter_mindestbetrag_wird_abgelehnt(db, alice):
    fund = RohFund("mydealz", "https://mydealz.de/norwegian", "t", "x")
    ext = AngebotExtraktion(bank_name="Bank Norwegian", kontoart="Kreditkarte", praemie_betrag=15.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "Mindestprämie" in ergebnis.ablehnungsgruende


def test_zwingender_gehaltseingang_wird_abgelehnt(db, alice):
    fund = RohFund("spartanien", "https://spartanien.de/consors", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Consorsbank",
        kontoart="Depot",
        praemie_betrag=80.0,
        bedingungen=[
            BedingungExtraktion(beschreibung="Gehaltseingang von mind. 1000€", einschaetzung="nicht_erfuellt")
        ],
    )
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "Gehaltseingang" in ergebnis.ablehnungsgruende


def test_unklare_bedingung_fuehrt_zu_pruefen_nicht_zu_ablehnung(db, alice):
    """Zentrale Idee des Konzepts: im Zweifel eher vorschlagen als
    ausschließen."""
    fund = RohFund("mydealz", "https://mydealz.de/unklar", "t", "x")
    ext = AngebotExtraktion(
        bank_name="Testbank",
        kontoart="Girokonto",
        praemie_betrag=100.0,
        bedingungen=[BedingungExtraktion(beschreibung="regelmäßiger Geldeingang", einschaetzung="zu_pruefen")],
    )
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ZU_PRUEFEN
    assert "unklar" in ergebnis.ablehnungsgruende.lower() or "regelmäßiger" in ergebnis.ablehnungsgruende


def test_sperrfrist_noch_nicht_erreicht_wird_abgelehnt(db, alice):
    santander = Bank(name="Santander")
    db.add(santander)
    db.commit()
    db.add(
        Deal(
            bank=santander,
            inhaber=alice,
            kontoart="Girokonto",
            gekuendigt=True,
            gekuendigt_im_monat=_monat_vor(3),
        )
    )
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/santander", "t", "x")
    ext = AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=12, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "Sperrfrist" in ergebnis.ablehnungsgruende


def test_sperrfrist_erreicht_wird_vorgeschlagen(db, alice):
    santander = Bank(name="Santander")
    db.add(santander)
    db.commit()
    db.add(
        Deal(
            bank=santander,
            inhaber=alice,
            kontoart="Girokonto",
            gekuendigt=True,
            gekuendigt_im_monat=_monat_vor(13),
        )
    )
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/santander", "t", "x")
    ext = AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=12, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_VORGESCHLAGEN


def test_unbekannte_sperrfrist_fuehrt_zu_pruefen(db, alice):
    bank = Bank(name="Testbank")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=alice, kontoart="Girokonto", gekuendigt=True, gekuendigt_im_monat=_monat_vor(3)))
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/testbank", "t", "x")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=None, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ZU_PRUEFEN


def test_bereits_aktiver_kunde_ohne_kuendigung_wird_abgelehnt(db, alice):
    bank = Bank(name="Testbank")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=alice, kontoart="Girokonto", gekuendigt=False))
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/testbank2", "t", "x")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "bereits Kundin" in ergebnis.ablehnungsgruende


def test_bank_wird_trotz_abweichender_schreibweise_erkannt(db, alice):
    """Regressionstest: "SMARTBROKER" (aus einem Angebot) muss dieselbe Bank
    treffen wie die selbst erfasste "Smart Broker" - sonst gilt ein
    bestehender Kunde fälschlich als Neukunde, nur weil ein Leerzeichen
    fehlt oder die Schreibweise abweicht."""
    bank = Bank(name="Smart Broker")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=alice, kontoart="Depot", gekuendigt=False))
    db.commit()

    fund = RohFund("spartanien", "https://www.spartanien.de/smartbroker", "t", "x")
    ext = AngebotExtraktion(bank_name="SMARTBROKER", kontoart="Depot", praemie_betrag=50.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_ABGELEHNT
    assert "bereits Kundin" in ergebnis.ablehnungsgruende


def test_stornierter_deal_zaehlt_nicht_als_vorkunde(db, alice):
    """Analog zum Kernmodell (Deal.storniert): ein Deal, der nie zustande kam,
    darf die Sperrfristen-Prüfung nicht beeinflussen."""
    bank = Bank(name="Testbank")
    db.add(bank)
    db.commit()
    db.add(Deal(bank=bank, inhaber=alice, kontoart="Girokonto", gekuendigt=True, storniert=True))
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/testbank3", "t", "x")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert ergebnis.status == matching.STATUS_VORGESCHLAGEN


def test_mydealz_quelle_wird_beim_uebernehmen_auf_bank_gemappt(db, alice):
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    daten = DealImport.model_validate_json(ergebnis.roh_json)
    assert daten.praemien[0].quelle == "bank"
    assert daten.urls[0].url == fund.quelle_url


def test_spartanien_quelle_bleibt_spartanien(db, alice):
    fund = RohFund("spartanien", "https://spartanien.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    daten = DealImport.model_validate_json(ergebnis.roh_json)
    assert daten.praemien[0].quelle == "spartanien"


def test_dealdoktor_quelle_wird_beim_uebernehmen_auf_bank_gemappt(db, alice):
    """dealdoktor-Funde verlinken auf das Angebot der Bank - die Prämie wird
    (wie bei mydealz) der Bank als Geber zugeordnet, nicht dem Portal."""
    fund = RohFund("dealdoktor", "https://www.dealdoktor.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    daten = DealImport.model_validate_json(ergebnis.roh_json)
    assert daten.praemien[0].quelle == "bank"
    assert daten.urls[0].url == fund.quelle_url


def test_dedup_erkennt_unveraenderten_fund(db, alice):
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, alice, MINDESTPRAEMIE)
    assert matching.bestehenden_vorschlag_finden(db, fund.quelle_url, alice.id, ergebnis.inhalt_hash) is None

    db.add(
        DealVorschlag(
            inhaber_id=alice.id,
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

    gefunden = matching.bestehenden_vorschlag_finden(db, fund.quelle_url, alice.id, ergebnis.inhalt_hash)
    assert gefunden is not None
    assert gefunden.bank_name == "C24"


def test_geaenderte_praemie_ist_kein_duplikat(db, alice):
    """Explizite Entscheidung: bei geänderten Daten (z.B. höhere Prämie)
    entsteht ein neuer Datensatz statt eines stillen Updates."""
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext_alt = AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ergebnis_alt = matching.bewerten(db, fund, ext_alt, alice, MINDESTPRAEMIE)
    db.add(
        DealVorschlag(
            inhaber_id=alice.id,
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
    ergebnis_neu = matching.bewerten(db, fund, ext_neu, alice, MINDESTPRAEMIE)
    assert ergebnis_neu.inhalt_hash != ergebnis_alt.inhalt_hash
    assert matching.bestehenden_vorschlag_finden(db, fund.quelle_url, alice.id, ergebnis_neu.inhalt_hash) is None


def test_anders_formulierte_gleichwertige_bedingung_ist_kein_duplikat(db, alice):
    """Bug (mehrfach identischer 'Deal öffnen'-Link in der Vorschläge-Liste):
    schwankt der Rohtext derselben Quelle-URL geringfügig (z.B. Kommentar-/
    Bewertungszahlen im mydealz-RSS-Feed), löst das eine erneute KI-
    Extraktion aus, die eine inhaltlich gleiche Bedingung nicht immer
    wortgleich formuliert. Das allein darf keinen neuen Datensatz erzeugen,
    solange Anzahl und Einschätzung der Bedingungen gleich bleiben."""
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext_alt = AngebotExtraktion(
        bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0,
        bedingungen=[BedingungExtraktion(beschreibung="Mindesteinlage von 2.000 €", einschaetzung="erfuellt")],
    )
    ergebnis_alt = matching.bewerten(db, fund, ext_alt, alice, MINDESTPRAEMIE)

    ext_neu = AngebotExtraktion(
        bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0,
        bedingungen=[BedingungExtraktion(beschreibung="Es ist eine Mindesteinlage von 2000 Euro nötig", einschaetzung="erfuellt")],
    )
    ergebnis_neu = matching.bewerten(db, fund, ext_neu, alice, MINDESTPRAEMIE)

    assert ergebnis_neu.inhalt_hash == ergebnis_alt.inhalt_hash


def test_tatsaechlich_geaenderte_bedingungen_bleiben_kein_duplikat(db, alice):
    """Ändert sich dagegen die Einschätzung oder Anzahl der Bedingungen
    wirklich (z.B. eine zusätzliche, unklare Bedingung), soll weiterhin ein
    neuer Datensatz entstehen."""
    fund = RohFund("mydealz", "https://mydealz.de/x", "t", "x")
    ext_alt = AngebotExtraktion(
        bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0,
        bedingungen=[BedingungExtraktion(beschreibung="Mindesteinlage von 2.000 €", einschaetzung="erfuellt")],
    )
    ergebnis_alt = matching.bewerten(db, fund, ext_alt, alice, MINDESTPRAEMIE)

    ext_neu = AngebotExtraktion(
        bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0,
        bedingungen=[BedingungExtraktion(beschreibung="Mindesteinlage von 2.000 €", einschaetzung="zu_pruefen")],
    )
    ergebnis_neu = matching.bewerten(db, fund, ext_neu, alice, MINDESTPRAEMIE)

    assert ergebnis_neu.inhalt_hash != ergebnis_alt.inhalt_hash
