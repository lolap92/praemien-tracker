"""helpers.kwk_ergebnis_anwenden() und die dazugehörigen
kwk_recherche_vorab_starten()/kwk_recherche_ergebnis_abholen()-Wrapper: die
Hintergrund-Variante von kwk_vorschlag() für den Übernehmen-Vorschau-Schritt
(routers/vorschlaege.py) - anders als dort gibt es hier bei fehlendem oder
fehlgeschlagenem Ergebnis nie einen Hinweis-Banner, sondern immer eine
konkrete Erinnerungs-Aufgabe."""

from __future__ import annotations

from praemien_tracker import kwk_recherche
from praemien_tracker.helpers import kwk_ergebnis_anwenden, kwk_recherche_ergebnis_abholen, kwk_recherche_vorab_starten
from praemien_tracker.models import Bank, Deal, Inhaber


def _deal(db, bank_name: str = "Testbank", kontoart: str = "Girokonto") -> Deal:
    bank = Bank(name=bank_name)
    inhaber = Inhaber(name="Alice")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank=bank, inhaber=inhaber, kontoart=kontoart)
    db.add(deal)
    db.commit()
    return deal


def test_erfolgreiches_ergebnis_legt_url_und_aufgabe_an(db):
    deal = _deal(db)

    kwk_ergebnis_anwenden(deal, ("https://bank.example/kwk", False))

    assert len(deal.urls) == 1
    assert deal.urls[0].url == "https://bank.example/kwk"
    assert len(deal.aufgaben) == 1
    assert "Testbank" in deal.aufgaben[0].beschreibung


def test_kein_programm_gefunden_legt_nichts_an(db):
    deal = _deal(db)

    kwk_ergebnis_anwenden(deal, (None, False))

    assert deal.urls == []
    assert deal.aufgaben == []


def test_fehlendes_ergebnis_legt_erinnerungsaufgabe_an(db):
    """None steht für "Recherche lief beim Abschließen noch" (Timeout) - statt
    eines Hinweis-Banners bekommt der Deal direkt eine konkrete Aufgabe."""
    deal = _deal(db)

    kwk_ergebnis_anwenden(deal, None)

    assert deal.urls == []
    assert len(deal.aufgaben) == 1
    assert "KwK möglich?" in deal.aufgaben[0].beschreibung


def test_fehlgeschlagenes_ergebnis_legt_erinnerungsaufgabe_an(db):
    deal = _deal(db)

    kwk_ergebnis_anwenden(deal, (None, True))

    assert deal.urls == []
    assert len(deal.aufgaben) == 1
    assert "KwK möglich?" in deal.aufgaben[0].beschreibung


def test_ohne_bank_passiert_nichts(db):
    inhaber = Inhaber(name="Alice")
    db.add(inhaber)
    db.commit()
    deal = Deal(bank=None, inhaber=inhaber, kontoart="Girokonto")

    kwk_ergebnis_anwenden(deal, None)

    assert deal.urls == []
    assert deal.aufgaben == []


def test_vorab_starten_und_ergebnis_abholen_geben_dasselbe_ergebnis_weiter(monkeypatch):
    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: ("https://bank.example/kwk", False))

    schluessel = kwk_recherche_vorab_starten("Testbank", "Girokonto")
    ergebnis = kwk_recherche_ergebnis_abholen(schluessel, timeout=2.0)

    assert ergebnis == ("https://bank.example/kwk", False)


def test_ergebnis_abholen_ohne_schluessel_liefert_none():
    assert kwk_recherche_ergebnis_abholen("", timeout=0.1) is None
