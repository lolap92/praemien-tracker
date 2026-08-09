"""helpers.kwk_vorschlag(): legt beim Anlegen eines Deals automatisch eine
Aufgabe mit Link an, wenn die Bank laut KI-Recherche ein "Kunden wirbt
Kunden"-Programm für diese Kontoart anbietet. Liefert True, wenn die
Recherche selbst fehlgeschlagen ist (Aufrufer zeigt dann einen Hinweis) -
das Anlegen des Deals wird dadurch nie blockiert."""

from __future__ import annotations

from praemien_tracker import kwk_recherche
from praemien_tracker.helpers import kwk_vorschlag
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


def test_moeglich_legt_url_und_aufgabe_an(db, monkeypatch):
    monkeypatch.setattr(
        kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: ("https://bank.example/kwk", False)
    )
    deal = _deal(db)

    fehlgeschlagen = kwk_vorschlag(db, deal)

    assert fehlgeschlagen is False
    assert len(deal.urls) == 1
    assert deal.urls[0].url == "https://bank.example/kwk"
    assert deal.urls[0].bezeichnung == "Kunden wirbt Kunden"
    assert len(deal.aufgaben) == 1
    assert "Testbank" in deal.aufgaben[0].beschreibung
    assert "https://bank.example/kwk" in deal.aufgaben[0].beschreibung


def test_ohne_treffer_bleibt_nichts_angelegt_und_kein_fehler(db, monkeypatch):
    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: (None, False))
    deal = _deal(db)

    fehlgeschlagen = kwk_vorschlag(db, deal)

    assert fehlgeschlagen is False
    assert deal.urls == []
    assert deal.aufgaben == []


def test_fehlgeschlagene_recherche_legt_nichts_an_meldet_aber_den_fehler(db, monkeypatch):
    """Kernanliegen: eine fehlgeschlagene Recherche blockiert die Deal-Anlage
    nicht, wird aber an den Aufrufer zurückgemeldet, damit der einen Hinweis
    zur manuellen Prüfung zeigen kann."""
    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: (None, True))
    deal = _deal(db)

    fehlgeschlagen = kwk_vorschlag(db, deal)

    assert fehlgeschlagen is True
    assert deal.urls == []
    assert deal.aufgaben == []


def test_recherche_bekommt_bank_und_kontoart_uebergeben(db, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(
        kwk_recherche,
        "moeglichkeit_recherchieren",
        lambda bank, kontoart: aufrufe.append((bank, kontoart)) or (None, False),
    )
    deal = _deal(db, bank_name="Consorsbank", kontoart="Depot")

    kwk_vorschlag(db, deal)

    assert aufrufe == [("Consorsbank", "Depot")]


def test_ohne_bank_wird_nicht_recherchiert(db, monkeypatch):
    """Verteidigende Prüfung wie bei kuendigung_vorschlag() - in der Praxis
    hat ein Deal beim Aufruf aus build_deal_from_import() immer schon eine
    Bank gesetzt (bank_id ist nicht nullable), das Attribut kann zu diesem
    Zeitpunkt aber noch None sein, solange der Deal noch nicht committed ist."""

    def _fail(bank, kontoart):
        raise AssertionError("Recherche sollte ohne Bank nicht aufgerufen werden.")

    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", _fail)
    inhaber = Inhaber(name="Alice")
    db.add(inhaber)
    db.commit()
    deal = Deal(bank=None, inhaber=inhaber, kontoart="Girokonto")

    fehlgeschlagen = kwk_vorschlag(db, deal)

    assert fehlgeschlagen is False
    assert deal.urls == []
