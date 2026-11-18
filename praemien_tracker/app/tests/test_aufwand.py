"""finder/aufwand.py: Aufwandsstufe je Bedingung und je Vorschlag, und die
Punkte-Anzeige auf der Vorschlagskarte."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from praemien_tracker.finder.aufwand import aufwand, bedingung_stufe
from praemien_tracker.main import app
from praemien_tracker.models import VorschlagBedingung

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
        ("Kontowechselservice nutzen", 2),
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
