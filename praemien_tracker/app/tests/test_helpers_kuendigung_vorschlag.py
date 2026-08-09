"""helpers.kuendigung_vorschlag(): reiner Tabellen-Lookup (KUENDIGUNG_HINWEISE),
keine KI-Websuche mehr - die läuft nur noch nachts im Batch, siehe
kuendigung_recherche.naechtlicher_lauf() / test_kuendigung_recherche.py."""

from __future__ import annotations

from praemien_tracker import kuendigung_recherche
from praemien_tracker.helpers import kuendigung_vorschlag
from praemien_tracker.models import Bank, Deal, Inhaber


def _deal(db, bank_name: str, kontoart: str) -> Deal:
    bank = Bank(name=bank_name)
    inhaber = Inhaber(name="Alice")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank=bank, inhaber=inhaber, kontoart=kontoart)
    db.add(deal)
    db.commit()
    return deal


def test_fest_hinterlegter_hinweis_wird_gesetzt(db):
    """C24 Bank/Girokonto ist in kuendigung_hinweise.py fest hinterlegt."""
    deal = _deal(db, "C24 Bank", "Girokonto")

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis is not None
    assert deal.kuendigung_hinweis_ki is False


def test_ohne_festen_eintrag_bleibt_hinweis_leer_ohne_api_aufruf(db, monkeypatch):
    """Kernanliegen: kein fest hinterlegter Eintrag löst keine KI-Websuche
    mehr aus - das Nachtragen übernimmt ausschließlich der nächtliche Batch
    (kuendigung_recherche.naechtlicher_lauf)."""
    monkeypatch.setattr(
        kuendigung_recherche, "hinweis_recherchieren", lambda *a, **kw: pytest_fail_if_called()
    )
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis is None
    assert deal.kuendigung_hinweis_ki is False


def pytest_fail_if_called():
    raise AssertionError("hinweis_recherchieren sollte beim Anlegen nicht mehr aufgerufen werden.")


def test_bestehender_hinweis_wird_nicht_ueberschrieben(db):
    deal = _deal(db, "C24 Bank", "Girokonto")
    deal.kuendigung_hinweis = "Eigener Text"

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis == "Eigener Text"
    assert deal.kuendigung_hinweis_ki is False


def test_ohne_bank_passiert_nichts(db):
    inhaber = Inhaber(name="Alice")
    db.add(inhaber)
    db.commit()
    deal = Deal(bank=None, inhaber=inhaber, kontoart="Girokonto")

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis is None
