"""Bei manueller Deal-Anlage (Formular /deals/new und JSON-Import) soll eine
fehlgeschlagene KwK-Recherche - wie beim Übernehmen eines Vorschlags
(kwk_ergebnis_anwenden) - eine konkrete Erinnerungs-Aufgabe hinterlassen,
statt folgenlos zu bleiben."""

from __future__ import annotations

from fastapi.testclient import TestClient

from praemien_tracker import kwk_recherche
from praemien_tracker.helpers import KWK_FALLBACK_AUFGABE_TEXT, build_deal_from_import
from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber
from praemien_tracker.schemas import DealImport

client = TestClient(app)


def test_json_import_legt_erinnerungsaufgabe_bei_fehlgeschlagener_recherche_an(db, monkeypatch):
    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: (None, True))
    daten = DealImport(bank="Testbank", kontoart="Girokonto", inhaber="Alice")

    deal = build_deal_from_import(db, daten)

    assert any(a.beschreibung == KWK_FALLBACK_AUFGABE_TEXT for a in deal.aufgaben)


def test_json_import_legt_keine_erinnerungsaufgabe_bei_erfolg_an(db, monkeypatch):
    monkeypatch.setattr(
        kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: ("https://bank.example/kwk", False)
    )
    daten = DealImport(bank="Testbank", kontoart="Girokonto", inhaber="Alice")

    deal = build_deal_from_import(db, daten)

    assert not any(a.beschreibung == KWK_FALLBACK_AUFGABE_TEXT for a in deal.aufgaben)


def test_uebernehmen_pfad_legt_trotz_uebersprungener_recherche_keine_doppelte_aufgabe_an(db, monkeypatch):
    """kwk_recherche_ueberspringen=True (Übernehmen-Ablauf) darf kwk_vorschlag
    gar nicht erst aufrufen - kwk_ergebnis_anwenden() kümmert sich dort
    separat um Erfolg/Fehlschlag (siehe test_helpers_kwk_ergebnis_anwenden.py)."""

    def _fail(bank, kontoart):
        raise AssertionError("kwk_vorschlag sollte bei kwk_recherche_ueberspringen=True nicht laufen.")

    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", _fail)
    daten = DealImport(bank="Testbank", kontoart="Girokonto", inhaber="Alice")

    deal = build_deal_from_import(db, daten, kwk_recherche_ueberspringen=True)

    assert deal.aufgaben == []


def test_formular_legt_erinnerungsaufgabe_bei_fehlgeschlagener_recherche_an(db, monkeypatch):
    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: (None, True))

    antwort = client.post(
        "/deals/new",
        data={"bank": "Testbank", "inhaber": "Alice", "kontoart": "Girokonto"},
        follow_redirects=False,
    )

    assert antwort.status_code == 303
    deal = db.query(Deal).join(Bank).filter(Bank.name == "Testbank").one()
    assert any(a.beschreibung == KWK_FALLBACK_AUFGABE_TEXT for a in deal.aufgaben)
