"""kuendigung_recherche.py - kein echtes Netzwerk, der Anthropic-Client wird
gefaked (analog zu finder/test_finder_extraktion.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praemien_tracker import kuendigung_recherche
from praemien_tracker.models import KuendigungRecherche


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
