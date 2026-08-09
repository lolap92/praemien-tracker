"""Ohne Jahresangabe fällt ein gesetzter Freibetrag-Betrag auf das laufende
Jahr - sonst wäre er in der Freibetrag-Übersicht (statistiken.py) keiner
Jahresspalte zugeordnet und praktisch unsichtbar (siehe
helpers.freibetrag_jahr_bestimmen). Geprüft an allen drei Stellen, die
freibetrag setzen: die reine Fallback-Funktion, der JSON-Import
(build_deal_from_import) und die Bearbeiten-Seite (routers/deals.py)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from praemien_tracker.helpers import build_deal_from_import, freibetrag_jahr_bestimmen
from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber
from praemien_tracker.schemas import DealImport

client = TestClient(app)
HEUTE = datetime.date.today().year


def test_betrag_ohne_jahr_faellt_auf_laufendes_jahr():
    assert freibetrag_jahr_bestimmen(None, Decimal("500")) == HEUTE


def test_betrag_mit_jahr_bleibt_unveraendert():
    assert freibetrag_jahr_bestimmen(2020, Decimal("500")) == 2020


def test_jahr_ohne_betrag_bleibt_stehen():
    assert freibetrag_jahr_bestimmen(2020, None) == 2020


def test_weder_jahr_noch_betrag():
    assert freibetrag_jahr_bestimmen(None, None) is None


def test_json_import_mit_freibetrag_ohne_jahr_bekommt_laufendes_jahr(db):
    daten = DealImport(bank="Testbank", inhaber="Alice", kontoart="Girokonto", freibetrag=Decimal("500"))

    deal = build_deal_from_import(db, daten)

    assert deal.freibetrag == Decimal("500")
    assert deal.freibetrag_jahr == HEUTE


def test_json_import_mit_explizitem_jahr_wird_uebernommen(db):
    daten = DealImport(
        bank="Testbank", inhaber="Alice", kontoart="Girokonto", freibetrag=Decimal("500"), freibetrag_jahr=2022
    )

    deal = build_deal_from_import(db, daten)

    assert deal.freibetrag_jahr == 2022


def test_json_import_ohne_freibetrag_bleibt_jahr_leer(db):
    daten = DealImport(bank="Testbank", inhaber="Alice", kontoart="Girokonto")

    deal = build_deal_from_import(db, daten)

    assert deal.freibetrag is None
    assert deal.freibetrag_jahr is None


def _deal(db) -> Deal:
    bank = Bank(name="Testbank")
    inhaber = Inhaber(name="Alice")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank=bank, inhaber=inhaber, kontoart="Girokonto")
    db.add(deal)
    db.commit()
    return deal


def test_bearbeiten_seite_mit_freibetrag_ohne_jahresfeld_faellt_auf_laufendes_jahr(db):
    deal = _deal(db)

    client.post(
        f"/deals/{deal.id}",
        data={
            "bank": "Testbank",
            "inhaber": "Alice",
            "kontoart": "Girokonto",
            "freibetrag": "500",
            "freibetrag_jahr": "",
        },
    )

    db.refresh(deal)
    assert deal.freibetrag_jahr == HEUTE
