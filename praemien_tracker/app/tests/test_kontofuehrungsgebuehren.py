"""Kontoführungsgebühren: Pflichtangabe für jeden Deal, und im
Kündigen-Reiter das Argument fürs Kündigen.

Die Unterscheidung, um die es überall geht: NULL heißt "noch nicht erfasst"
(Lücke, wird unter "Deal pflegen" angemahnt), 0 heißt "kostenlos" (erfasst,
keine Lücke). Ein Betrag über 0 wird im Kündigen-Reiter rot hervorgehoben -
jeder Monat, den das Konto offen steht, kostet dann Geld.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from praemien_tracker import derived
from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber, Praemie

client = TestClient(app)


@pytest.fixture()
def kuendbarer_deal(db):
    """Ein Deal im Status "Kündigen": Prämie erhalten, keine Sperrfrist,
    keine offenen Bedingungen."""
    deal = Deal(
        kontoart="Girokonto",
        kontonummer="DE1",
        zugangsdaten_gespeichert=True,
        bank=Bank(name="Gebuehrenbank"),
        inhaber=Inhaber(name="Max"),
    )
    deal.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=True))
    db.add(deal)
    db.commit()
    return deal


# --- Pflichtangabe ---


def test_fehlende_gebuehr_ist_eine_luecke(db, kuendbarer_deal):
    assert kuendbarer_deal.kontofuehrungsgebuehren is None
    offen = {f.feld for f in derived.offene_felder(kuendbarer_deal)}
    assert "kontofuehrungsgebuehren" in offen


def test_null_euro_ist_eine_erfasste_angabe(db, kuendbarer_deal):
    """Die häufigste Antwort ist "kostenlos" - sie darf nicht wie ein leer
    gelassenes Feld behandelt werden."""
    kuendbarer_deal.kontofuehrungsgebuehren = Decimal("0")
    db.commit()
    offen = {f.feld for f in derived.offene_felder(kuendbarer_deal)}
    assert "kontofuehrungsgebuehren" not in offen


def test_gebuehr_kann_uebersprungen_werden(db, kuendbarer_deal):
    derived.uebersprungene_felder_speichern(kuendbarer_deal, ["kontofuehrungsgebuehren"])
    db.commit()
    offen = {f.feld for f in derived.offene_felder(kuendbarer_deal)}
    assert "kontofuehrungsgebuehren" not in offen


def test_gekuendigter_deal_braucht_keine_gebuehr_mehr(db, kuendbarer_deal):
    """Wie bei den Zugangsdaten: ab der Kündigung ist die Gebühr
    gegenstandslos - das Konto läuft aus, der Betrag ändert an keiner
    Entscheidung mehr etwas."""
    kuendbarer_deal.gekuendigt = True
    kuendbarer_deal.gekuendigt_im_monat = "2026-08"
    db.commit()
    offen = {f.feld for f in derived.offene_felder(kuendbarer_deal)}
    assert "kontofuehrungsgebuehren" not in offen


def test_stornierter_deal_braucht_keine_gebuehr_mehr(db, kuendbarer_deal):
    kuendbarer_deal.storniert = True
    db.commit()
    offen = {f.feld for f in derived.offene_felder(kuendbarer_deal)}
    assert "kontofuehrungsgebuehren" not in offen


def test_offene_gebuehr_erzeugt_deal_pflegen_zeile(db, kuendbarer_deal):
    html = client.get("/todos?tab=pflegen").text
    assert "Kontoführungsgebühren" in html


# --- kostet_gebuehren ---


@pytest.mark.parametrize(
    "wert, erwartet",
    [(None, False), (Decimal("0"), False), (Decimal("0.01"), True), (Decimal("4.90"), True)],
)
def test_kostet_gebuehren(wert, erwartet):
    deal = Deal(kontoart="Giro", kontofuehrungsgebuehren=wert, bank=Bank(name="B"), inhaber=Inhaber(name="I"))
    assert derived.kostet_gebuehren(deal) is erwartet


# --- Kündigen-Reiter ---


def _kuendigen_panel(html: str):
    return BeautifulSoup(html, "html.parser").select_one("#panel-kuendigen")


def test_kuendigen_hebt_laufende_gebuehren_hervor(db, kuendbarer_deal):
    kuendbarer_deal.kontofuehrungsgebuehren = Decimal("4.90")
    db.commit()

    panel = _kuendigen_panel(client.get("/todos?tab=kuendigen").text)
    warnung = panel.select_one(".gebuehr-warnung")
    assert warnung is not None
    assert "4,90" in warnung.get_text()


def test_kuendigen_ohne_gebuehren_zeigt_keine_warnung(db, kuendbarer_deal):
    kuendbarer_deal.kontofuehrungsgebuehren = Decimal("0")
    db.commit()

    panel = _kuendigen_panel(client.get("/todos?tab=kuendigen").text)
    assert panel.select_one(".gebuehr-warnung") is None


def test_kuendigen_ohne_erfasste_gebuehr_zeigt_keine_warnung(db, kuendbarer_deal):
    """Nicht erfasst heißt nicht "kostenlos", aber auch nicht "kostet" - eine
    Vermutung wird nicht rot angezeigt."""
    panel = _kuendigen_panel(client.get("/todos?tab=kuendigen").text)
    assert panel.select_one(".gebuehr-warnung") is None


def test_warnfarbe_ist_im_css_definiert():
    """Ohne die Klasse bliebe die Hervorhebung unsichtbar."""
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    assert ".gebuehr-warnung {" in css
    assert "background: var(--danger);" in css


# --- Speichern ---


def test_pflegen_dialog_speichert_null_euro(db, kuendbarer_deal):
    antwort = client.post(
        f"/deals/{kuendbarer_deal.id}/felder",
        data={"kontofuehrungsgebuehren": "0"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    db.refresh(kuendbarer_deal)
    assert kuendbarer_deal.kontofuehrungsgebuehren == Decimal("0")


def test_pflegen_dialog_akzeptiert_komma(db, kuendbarer_deal):
    client.post(
        f"/deals/{kuendbarer_deal.id}/felder",
        data={"kontofuehrungsgebuehren": "4,90"},
        follow_redirects=False,
    )
    db.refresh(kuendbarer_deal)
    assert kuendbarer_deal.kontofuehrungsgebuehren == Decimal("4.90")


def test_pflegen_dialog_leeres_feld_bleibt_offen(db, kuendbarer_deal):
    client.post(
        f"/deals/{kuendbarer_deal.id}/felder",
        data={"kontofuehrungsgebuehren": ""},
        follow_redirects=False,
    )
    db.refresh(kuendbarer_deal)
    assert kuendbarer_deal.kontofuehrungsgebuehren is None


def test_bearbeiten_seite_speichert_die_gebuehr(db, kuendbarer_deal):
    client.post(
        f"/deals/{kuendbarer_deal.id}",
        data={
            "bank": "Gebuehrenbank",
            "inhaber": "Max",
            "kontoart": "Girokonto",
            "kontonummer": "DE1",
            "kontofuehrungsgebuehren": "2,50",
            "zugangsdaten_gespeichert": "on",
        },
        follow_redirects=False,
    )
    db.refresh(kuendbarer_deal)
    assert kuendbarer_deal.kontofuehrungsgebuehren == Decimal("2.50")


def test_feld_filter_kennt_die_gebuehren(db, kuendbarer_deal):
    """Ein Filterwert ohne Gegenstück im Router fiele stillschweigend auf
    "alle" zurück."""
    kuendbarer_deal.kontonummer = None
    db.commit()

    html = client.get("/todos?tab=pflegen&feld=kontofuehrungsgebuehren").text
    panel = BeautifulSoup(html, "html.parser").select_one("#panel-pflegen")
    assert "Kontoführungsgebühren" in panel.get_text()
    assert "Kontonummer" not in panel.get_text()


def test_json_import_uebernimmt_die_gebuehr(db):
    """Backup und JSON-Import müssen das Feld mitführen, sonst geht es beim
    Wiedereinspielen verloren."""
    from praemien_tracker.helpers import build_deal_from_import
    from praemien_tracker.schemas import DealImport

    daten = DealImport.model_validate(
        {
            "bank": "Import-Bank",
            "kontoart": "Girokonto",
            "inhaber": "Max",
            "kontofuehrungsgebuehren": "3.90",
            "praemien": [],
            "bedingungen": [],
        }
    )
    deal = build_deal_from_import(db, daten)
    assert deal.kontofuehrungsgebuehren == Decimal("3.90")
