"""finder/aufwand.py: Aufwandsstufe je Bedingung und je Vorschlag,
Gebühren-Einstufung, und die Punkte-Anzeige auf der Vorschlagskarte."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from praemien_tracker.finder import matching
from praemien_tracker.finder.aufwand import aufwand, bedingung_stufe, gebuehren
from praemien_tracker.finder.extraktion import AngebotExtraktion
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.main import app
from praemien_tracker.models import VorschlagBedingung
from praemien_tracker.schemas import DealImport

from test_vorschlaege_router import _vorschlag, inhaber  # noqa: F401 (Fixture)

client = TestClient(app)


@pytest.mark.parametrize(
    ("text", "stufe"),
    [
        # 1 - nur eröffnen
        ("Neukunde sein", 1),
        ("Konto online eröffnen", 1),
        ("Kreditkarte beantragen", 1),
        ("Video-Ident durchführen", 1),
        ("Kein Gehaltseingang nötig", 1),
        ("Gratisaktie bis 100 €", 1),
        # 2 - Geld überweisen
        ("Mindesteinzahlung von 100 € innerhalb von 10 Tagen", 2),
        ("Mindesteinlage von 2.000 €", 2),
        ("regelmäßiger Geldeingang", 2),
        ("Dauerauftrag einrichten", 2),
        ("10.000 € als Festgeld anlegen", 2),
        ("Konto innerhalb der ersten 6 Monate aktiv nutzen mit mindestens drei Buchungen pro Monat", 2),
        # 3 - Karte einsetzen
        ("3 Kartenzahlungen im ersten Monat", 3),
        ("Kreditkarte innerhalb von 4 Wochen mindestens 2x für insgesamt 50 € einsetzen", 3),
        ("Mindestumsatz von 500 € mit der Karte", 3),
        ("Mit Apple Pay bezahlen", 3),
        # 4 - Wertpapiere
        ("Depotübertrag von mindestens 5.000 €", 4),
        ("Wertpapiersparplan über mind. 50 € einrichten und 3x ausführen", 4),
        ("Mindestens 3 Trades innerhalb von 3 Monaten", 4),
        # 4 - Kontowechselservice
        ("Kontowechselservice nutzen", 4),
        ("Kontowechselservice nutzen und mind. 2 Daueraufträge umziehen", 4),
        ("Nutzung des digitalen Kontowechsel-Service", 4),
        ("Kontoumzug beauftragen", 4),
        ("Wechselservice nutzen oder 3 Kartenzahlungen", 3),
        # 5 - Gehaltseingang, auch wenn "Eingang" zusätzlich nach Stufe 2 klingt
        ("Gehaltseingang von mind. 1000€", 5),
        ("In drei Monaten jeweils ein Einkommenseingang (Gehalt, Rente, BAföG oder ähnlich)", 5),
        # Mehrere Anforderungen zugleich: die höchste zählt.
        ("Gehaltseingang und 3 Kartenzahlungen pro Monat", 5),
        ("Karte 5x nutzen und monatlicher Geldeingang von 500 €", 3),
        # Aufgezählte Alternativen: die einfachste zählt.
        ("Geldeingang von mindestens 700 € (Gehalt oder Überweisung vom eigenen Konto)", 2),
        (
            "Pro Monat mindestens drei Buchungen, dazu zählen Guthaben- oder Gehaltseingänge, "
            "Kindergeld, Kartenzahlungen, Lastschriften",
            2,
        ),
    ],
)
def test_bedingung_stufe(text, stufe):
    assert bedingung_stufe(text) == stufe


def test_aufwand_nimmt_hoechste_stufe():
    bedingungen = [SimpleNamespace(beschreibung="Neukunde sein"), SimpleNamespace(beschreibung="3 Kartenzahlungen")]
    ergebnis = aufwand(bedingungen)
    assert ergebnis.stufe == 3
    assert ergebnis.label == "Karte einsetzen"


def test_aufwand_ohne_bedingungen_ist_nur_eroeffnen():
    assert aufwand([]).stufe == 1


def test_karte_zeigt_punkte_und_bedingungen_aufklappbar(db, inhaber):  # noqa: F811
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")
    vorschlag.bedingungen.append(VorschlagBedingung(beschreibung="Neukunde sein", einschaetzung="erfuellt"))
    vorschlag.bedingungen.append(VorschlagBedingung(beschreibung="Mindesteinzahlung 100 €", einschaetzung="erfuellt"))
    db.commit()

    soup = BeautifulSoup(client.get("/vorschlaege").text, "html.parser")
    karte = soup.select_one(".vorschlag-karte")
    punkte = karte.select_one(".aufwand-punkte")
    assert punkte["aria-label"] == "Aufwand 2 von 5"
    assert len(punkte.select(".punkt.an")) == 2
    assert len(punkte.select(".punkt")) == 5
    assert karte.select_one(".vk-aufwand-label").get_text(strip=True) == "Geld überweisen"
    details = karte.select_one("details.vk-bed-details")
    assert details is not None and not details.has_attr("open")
    assert "2 Bedingungen anzeigen" in details.summary.get_text()
    assert [s.get_text(strip=True) for s in details.select(".bed-stufe")] == ["Nur eröffnen", "Geld überweisen"]


# --- Kontoführungsgebühren --------------------------------------------------


@pytest.mark.parametrize(
    ("art", "euro", "stufe", "label"),
    [
        ("kostenlos", None, 1, "Kostenlos"),
        ("vermeidbar", Decimal("4.90"), 2, "Vermeidbar · 4,90 €/Monat"),
        ("fest", Decimal("3.90"), 3, "Feste Gebühr · 3,90 €/Monat"),
        ("fest", None, 3, "Feste Gebühr"),
        (None, None, None, "Unbekannt"),
    ],
)
def test_gebuehren_stufe(art, euro, stufe, label):
    ergebnis = gebuehren(SimpleNamespace(kontofuehrung=art, kontofuehrung_euro_monat=euro, kontofuehrung_hinweis=None))
    assert ergebnis.stufe == stufe
    assert ergebnis.label == label


def _ext(**kwargs) -> AngebotExtraktion:
    return AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[], **kwargs)


@pytest.mark.parametrize(
    ("art", "euro", "erwartet"),
    [("kostenlos", None, Decimal("0")), ("fest", 3.9, Decimal("3.90")), ("vermeidbar", 4.9, None), (None, None, None)],
)
def test_gebuehren_landen_beim_uebernehmen_im_deal(db, inhaber, art, euro, erwartet):  # noqa: F811
    """Kostenlos -> 0, feste Gebühr -> Betrag; vermeidbar/unbekannt bleibt
    leer und wird am Deal wie bisher als Lücke angemahnt."""
    fund = RohFund("mydealz", "https://mydealz.de/t", "t", "x")
    ergebnis = matching.bewerten(
        db, fund, _ext(kontofuehrung=art, kontofuehrung_euro_monat=euro), inhaber, Decimal("50")
    )
    assert ergebnis.kontofuehrung == art
    assert DealImport.model_validate_json(ergebnis.roh_json).kontofuehrungsgebuehren == erwartet


def test_alter_cache_eintrag_ohne_gebuehrenfeld_bleibt_lesbar():
    alt = '{"bank_name": "X", "kontoart": "Girokonto", "praemie_betrag": 50, "bedingungen": []}'
    assert AngebotExtraktion.model_validate_json(alt).kontofuehrung is None


def test_karte_zeigt_gebuehren_zeile(db, inhaber):  # noqa: F811
    _vorschlag(
        db,
        inhaber,
        "vorgeschlagen",
        kontofuehrung="vermeidbar",
        kontofuehrung_euro_monat=Decimal("4.90"),
        kontofuehrung_hinweis="entfällt ab 700 € Geldeingang pro Monat",
    )
    soup = BeautifulSoup(client.get("/vorschlaege").text, "html.parser")
    zeile = soup.select_one(".vorschlag-karte .vk-gebuehren")
    assert zeile.select_one(".aufwand-punkte")["aria-label"] == "Gebühren 2 von 3"
    assert len(zeile.select(".punkt.an")) == 2
    assert zeile.select_one(".vk-aufwand-label").get_text(strip=True) == "Vermeidbar · 4,90 €/Monat"
    assert zeile.select_one(".vk-gebuehren-hinweis").get_text(strip=True) == "entfällt ab 700 € Geldeingang pro Monat"


def test_karte_ohne_gebuehren_zeigt_unbekannt(db, inhaber):  # noqa: F811
    _vorschlag(db, inhaber, "vorgeschlagen")
    soup = BeautifulSoup(client.get("/vorschlaege").text, "html.parser")
    zeile = soup.select_one(".vorschlag-karte .vk-gebuehren")
    assert zeile.select(".punkt.an") == []
    assert zeile.select_one(".vk-aufwand-label").get_text(strip=True) == "Unbekannt"


def test_kontowechsel_bestimmt_label_der_karte():
    ergebnis = aufwand([SimpleNamespace(beschreibung="Neukunde sein"), SimpleNamespace(beschreibung="Kontowechselservice nutzen")])
    assert (ergebnis.stufe, ergebnis.label) == (4, "Kontowechselservice")
