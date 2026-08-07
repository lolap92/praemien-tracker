"""helpers.kuendigung_vorschlag(): fest hinterlegter Hinweis geht vor,
KI-Recherche ist nur der Fallback und wird als solcher markiert."""

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


def test_fest_hinterlegter_hinweis_wird_nicht_als_ki_markiert(db, monkeypatch):
    """C24 Bank/Girokonto ist in kuendigung_hinweise.py fest hinterlegt."""
    monkeypatch.setattr(
        kuendigung_recherche, "hinweis_recherchieren", lambda *a, **kw: pytest_fail_if_called()
    )
    deal = _deal(db, "C24 Bank", "Girokonto")

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis is not None
    assert deal.kuendigung_hinweis_ki is False


def pytest_fail_if_called():
    raise AssertionError("Recherche sollte bei fest hinterlegtem Hinweis nicht aufgerufen werden.")


def test_ki_recherche_greift_wenn_nichts_fest_hinterlegt_ist(db, monkeypatch):
    monkeypatch.setattr(
        kuendigung_recherche,
        "hinweis_recherchieren",
        lambda db_, bank, kontoart: ("Online kündbar.", "https://bank.example/faq"),
    )
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis == "Online kündbar."
    assert deal.kuendigung_hinweis_url == "https://bank.example/faq"
    assert deal.kuendigung_hinweis_ki is True


def test_ohne_treffer_bleibt_hinweis_leer(db, monkeypatch):
    monkeypatch.setattr(kuendigung_recherche, "hinweis_recherchieren", lambda *a, **kw: None)
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis is None
    assert deal.kuendigung_hinweis_ki is False


def test_bestehender_hinweis_wird_nicht_ueberschrieben(db, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(
        kuendigung_recherche,
        "hinweis_recherchieren",
        lambda *a, **kw: aufrufe.append(1) or ("x", "https://x"),
    )
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")
    deal.kuendigung_hinweis = "Eigener Text"

    kuendigung_vorschlag(db, deal)

    assert deal.kuendigung_hinweis == "Eigener Text"
    assert deal.kuendigung_hinweis_ki is False
    assert aufrufe == []
