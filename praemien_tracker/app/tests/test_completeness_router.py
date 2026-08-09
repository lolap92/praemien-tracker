"""routers/completeness.py: abgeschlossene und gekündigte Deals sind für die
Datenqualität nicht mehr relevant und sollen auf der Vollständigkeits-Seite
weder auftauchen noch mitgezählt werden."""

from __future__ import annotations

from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber

client = TestClient(app)


_zaehler = 0


def _deal(db, **kwargs) -> Deal:
    global _zaehler
    _zaehler += 1
    bank = Bank(name=f"Bank {_zaehler}")
    inhaber = Inhaber(name=f"Inhaber {_zaehler}")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank=bank, inhaber=inhaber, kontoart="Girokonto", **kwargs)
    db.add(deal)
    db.commit()
    return deal


def test_offener_deal_erscheint_in_der_liste(db):
    deal = _deal(db)

    antwort = client.get("/completeness")

    assert deal.bank.name in antwort.text
    assert "/ 1 Deals" in antwort.text


def test_stornierter_deal_wird_ausgeblendet_und_nicht_mitgezaehlt(db):
    offen = _deal(db)
    _deal(db, storniert=True)

    antwort = client.get("/completeness")

    assert offen.bank.name in antwort.text
    assert "/ 1 Deals" in antwort.text


def test_bestaetigt_gekuendigter_deal_wird_ausgeblendet(db):
    offen = _deal(db)
    _deal(db, gekuendigt=True, kuendigung_bestaetigt=True)

    antwort = client.get("/completeness")

    assert offen.bank.name in antwort.text
    assert "/ 1 Deals" in antwort.text


def test_gekuendigt_aber_unbestaetigt_bleibt_sichtbar(db):
    """Nur *bestätigt* gekündigt ist terminal (siehe derived.status) - eine
    Kündigung ohne Bestätigung ist noch nicht abgeschlossen."""
    deal = _deal(db, gekuendigt=True, kuendigung_bestaetigt=False)

    antwort = client.get("/completeness")

    assert deal.bank.name in antwort.text
    assert "/ 1 Deals" in antwort.text
