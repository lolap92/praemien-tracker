"""kuendigung_recherche.py - kein echtes Netzwerk, der Anthropic-Client wird
gefaked (analog zu finder/test_finder_extraktion.py)."""

from __future__ import annotations

from types import SimpleNamespace

from praemien_tracker import kuendigung_recherche
from praemien_tracker.models import Bank, Deal, Inhaber, KuendigungRecherche


class _FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output
        self.aufrufe = 0

    def parse(self, **kwargs):
        self.aufrufe += 1
        return SimpleNamespace(parsed_output=self._parsed_output)


class _FakeClient:
    def __init__(self, parsed_output):
        self.messages = _FakeMessages(parsed_output)


def _ergebnis(**overrides):
    daten = {"gefunden": True, "anleitung": "Online im Kundenportal kündbar.", "quelle_url": "https://bank.example/faq"}
    daten.update(overrides)
    return kuendigung_recherche._KuendigungswegErgebnis(**daten)


def test_ohne_api_key_liefert_none_und_legt_nichts_an(db, monkeypatch):
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: None)

    ergebnis = kuendigung_recherche.hinweis_recherchieren(db, "Testbank", "Girokonto")

    assert ergebnis is None
    assert db.query(KuendigungRecherche).count() == 0


def test_erfolgreiche_recherche_wird_gecacht(db, monkeypatch):
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)

    ergebnis = kuendigung_recherche.hinweis_recherchieren(db, "Testbank", "Girokonto")

    assert ergebnis == ("Online im Kundenportal kündbar.", "https://bank.example/faq")
    gecacht = db.query(KuendigungRecherche).one()
    assert gecacht.bank_name == "Testbank"
    assert gecacht.kontoart == "Girokonto"
    assert client.messages.aufrufe == 1


def test_zweiter_aufruf_nutzt_cache_ohne_erneuten_api_aufruf(db, monkeypatch):
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)

    kuendigung_recherche.hinweis_recherchieren(db, "Testbank", "Girokonto")
    ergebnis = kuendigung_recherche.hinweis_recherchieren(db, "Testbank", "Girokonto")

    assert ergebnis == ("Online im Kundenportal kündbar.", "https://bank.example/faq")
    assert client.messages.aufrufe == 1


def test_nichts_gefunden_liefert_none_und_legt_nichts_an(db, monkeypatch):
    client = _FakeClient(_ergebnis(gefunden=False, anleitung="", quelle_url=""))
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)

    ergebnis = kuendigung_recherche.hinweis_recherchieren(db, "Unbekannte Bank", "Girokonto")

    assert ergebnis is None
    assert db.query(KuendigungRecherche).count() == 0


def test_kein_auswertbares_ergebnis_ist_konservativ(db, monkeypatch):
    client = _FakeClient(None)
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)

    ergebnis = kuendigung_recherche.hinweis_recherchieren(db, "Testbank", "Girokonto")

    assert ergebnis is None


def test_api_fehler_wird_abgefangen(db, monkeypatch):
    class _KaputterClient:
        class messages:
            @staticmethod
            def parse(**kwargs):
                raise RuntimeError("kaputt")

    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: _KaputterClient())

    ergebnis = kuendigung_recherche.hinweis_recherchieren(db, "Testbank", "Girokonto")

    assert ergebnis is None
    assert db.query(KuendigungRecherche).count() == 0


def _deal(db, bank_name: str, kontoart: str = "Girokonto", inhaber_name: str | None = None, **kwargs) -> Deal:
    bank = db.query(Bank).filter_by(name=bank_name).one_or_none() or Bank(name=bank_name)
    inhaber = Inhaber(name=inhaber_name or f"Inhaber-{bank_name}-{kontoart}")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank=bank, inhaber=inhaber, kontoart=kontoart, **kwargs)
    db.add(deal)
    db.commit()
    return deal


def test_alle_ohne_hinweis_nachtragen_nutzt_feste_tabelle_ohne_api_aufruf(db, monkeypatch):
    """C24 Bank/Girokonto ist fest hinterlegt - kein API-Aufruf nötig."""
    monkeypatch.setattr(
        kuendigung_recherche, "hinweis_recherchieren", lambda *a, **kw: pytest_fail_if_called()
    )
    deal = _deal(db, "C24 Bank")

    anzahl = kuendigung_recherche.alle_ohne_hinweis_nachtragen(db)

    assert anzahl == 1
    assert deal.kuendigung_hinweis is not None
    assert deal.kuendigung_hinweis_ki is False


def pytest_fail_if_called():
    raise AssertionError("hinweis_recherchieren sollte bei fest hinterlegtem Eintrag nicht aufgerufen werden.")


def test_alle_ohne_hinweis_nachtragen_recherchiert_wenn_nichts_fest_hinterlegt_ist(db, monkeypatch):
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)
    deal = _deal(db, "Ganz Unbekannte Bank")

    anzahl = kuendigung_recherche.alle_ohne_hinweis_nachtragen(db)

    assert anzahl == 1
    assert deal.kuendigung_hinweis == "Online im Kundenportal kündbar."
    assert deal.kuendigung_hinweis_ki is True


def test_alle_ohne_hinweis_nachtragen_dedupliziert_ueber_mehrere_deals(db, monkeypatch):
    """Zwei Deals mit derselben Bank+Kontoart teilen sich den DB-Cache aus
    hinweis_recherchieren - nur ein API-Aufruf für beide."""
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)
    deal_a = _deal(db, "Ganz Unbekannte Bank", inhaber_name="Alice")
    deal_b = _deal(db, "Ganz Unbekannte Bank", inhaber_name="Max")

    anzahl = kuendigung_recherche.alle_ohne_hinweis_nachtragen(db)

    assert anzahl == 2
    assert deal_a.kuendigung_hinweis == "Online im Kundenportal kündbar."
    assert deal_b.kuendigung_hinweis == "Online im Kundenportal kündbar."
    assert client.messages.aufrufe == 1


def test_alle_ohne_hinweis_nachtragen_laesst_bestehenden_hinweis_unangetastet(db):
    deal = _deal(db, "Ganz Unbekannte Bank", kuendigung_hinweis="Eigener Text")

    anzahl = kuendigung_recherche.alle_ohne_hinweis_nachtragen(db)

    assert anzahl == 0
    assert deal.kuendigung_hinweis == "Eigener Text"


def test_alle_ohne_hinweis_nachtragen_ueberspringt_stornierte_deals(db, monkeypatch):
    monkeypatch.setattr(
        kuendigung_recherche, "hinweis_recherchieren", lambda *a, **kw: pytest_fail_if_called()
    )
    deal = _deal(db, "Ganz Unbekannte Bank", storniert=True)

    anzahl = kuendigung_recherche.alle_ohne_hinweis_nachtragen(db)

    assert anzahl == 0
    assert deal.kuendigung_hinweis is None


def test_alle_ohne_hinweis_nachtragen_ohne_treffer_bleibt_leer(db, monkeypatch):
    client = _FakeClient(_ergebnis(gefunden=False, anleitung="", quelle_url=""))
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)
    deal = _deal(db, "Ganz Unbekannte Bank")

    anzahl = kuendigung_recherche.alle_ohne_hinweis_nachtragen(db)

    assert anzahl == 0
    assert deal.kuendigung_hinweis is None


def test_naechtlicher_lauf_faengt_fehler_ab(monkeypatch):
    """Ein Fehler im Batch darf den Scheduler nicht zum Absturz bringen -
    analog zu finder.lauf.geplanter_lauf()."""

    def _kaputt(db):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(kuendigung_recherche, "alle_ohne_hinweis_nachtragen", _kaputt)

    kuendigung_recherche.naechtlicher_lauf()  # darf nicht raisen
