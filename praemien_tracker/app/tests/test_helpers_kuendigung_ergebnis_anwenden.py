"""helpers.kuendigung_ergebnis_anwenden() und die dazugehörigen
kuendigung_hinweis_vorab_starten()/kuendigung_hinweis_ergebnis_abholen()-
Wrapper: die Hintergrund-Variante von kuendigung_vorschlag() für den
Übernehmen-Vorschau-Schritt (routers/vorschlaege.py)."""

from __future__ import annotations

from praemien_tracker import kuendigung_recherche
from praemien_tracker.helpers import (
    kuendigung_ergebnis_anwenden,
    kuendigung_hinweis_ergebnis_abholen,
    kuendigung_hinweis_vorab_starten,
)
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


def test_fest_hinterlegter_hinweis_geht_vor_dem_ki_ergebnis(db):
    """C24 Bank/Girokonto ist in kuendigung_hinweise.py fest hinterlegt - der
    geht vor, auch wenn (theoretisch) ein KI-Ergebnis vorliegt."""
    deal = _deal(db, "C24 Bank", "Girokonto")

    kuendigung_ergebnis_anwenden(deal, ("KI-Text", "https://ki.example"))

    assert deal.kuendigung_hinweis is not None
    assert deal.kuendigung_hinweis != "KI-Text"
    assert deal.kuendigung_hinweis_ki is False


def test_ki_ergebnis_wird_uebernommen_wenn_nichts_fest_hinterlegt_ist(db):
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")

    kuendigung_ergebnis_anwenden(deal, ("Online kündbar.", "https://bank.example/faq"))

    assert deal.kuendigung_hinweis == "Online kündbar."
    assert deal.kuendigung_hinweis_url == "https://bank.example/faq"
    assert deal.kuendigung_hinweis_ki is True


def test_ohne_ki_ergebnis_bleibt_hinweis_leer(db):
    """None deckt sowohl Timeout als auch eine legitim erfolglose Recherche
    ab - in beiden Fällen bleibt das Feld leer, siehe Docstring."""
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")

    kuendigung_ergebnis_anwenden(deal, None)

    assert deal.kuendigung_hinweis is None
    assert deal.kuendigung_hinweis_ki is False


def test_bestehender_hinweis_wird_nicht_ueberschrieben(db):
    deal = _deal(db, "Ganz Unbekannte Bank", "Girokonto")
    deal.kuendigung_hinweis = "Eigener Text"

    kuendigung_ergebnis_anwenden(deal, ("KI-Text", "https://ki.example"))

    assert deal.kuendigung_hinweis == "Eigener Text"
    assert deal.kuendigung_hinweis_ki is False


def test_vorab_starten_ueberspringt_recherche_wenn_fest_hinterlegt(monkeypatch):
    """Für C24 Bank/Girokonto gibt es schon einen festen Eintrag - keine
    (kostenpflichtige) KI-Recherche nötig, also kein Hintergrund-Thread."""
    monkeypatch.setattr(
        kuendigung_recherche, "hintergrund_starten", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("sollte nicht laufen"))
    )

    kuendigung_hinweis_vorab_starten("C24 Bank", "Girokonto")


def test_vorab_starten_und_ergebnis_abholen_geben_dasselbe_ergebnis_weiter(monkeypatch):
    monkeypatch.setattr(
        kuendigung_recherche, "hinweis_recherchieren", lambda db_, bank, kontoart: ("Online kündbar.", "https://bank.example/faq")
    )

    schluessel = kuendigung_hinweis_vorab_starten("Ganz Unbekannte Bank", "Girokonto")
    ergebnis = kuendigung_hinweis_ergebnis_abholen(schluessel, timeout=2.0)

    assert ergebnis == ("Online kündbar.", "https://bank.example/faq")


def test_ergebnis_abholen_ohne_schluessel_liefert_none():
    assert kuendigung_hinweis_ergebnis_abholen("", timeout=0.1) is None
