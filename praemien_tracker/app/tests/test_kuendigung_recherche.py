"""kuendigung_recherche.py - kein echtes Netzwerk, der Anthropic-Client wird
gefaked (analog zu finder/test_finder_extraktion.py)."""

from __future__ import annotations

import threading
import time
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


def test_hintergrund_starten_liefert_ergebnis_ueber_ergebnis_abholen(db, monkeypatch):
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", lambda: client)

    kuendigung_recherche.hintergrund_starten("hintergrund-testbank|girokonto", "Hintergrund-Testbank", "Girokonto")
    ergebnis = kuendigung_recherche.ergebnis_abholen("hintergrund-testbank|girokonto", timeout=2.0)

    assert ergebnis == ("Online im Kundenportal kündbar.", "https://bank.example/faq")
    # Der Hintergrund-Thread nutzt eine eigene Session (SessionLocal), landet
    # aber in derselben Datenbank wie der Test - der Cache-Eintrag muss also
    # trotzdem entstehen.
    assert db.query(KuendigungRecherche).filter_by(bank_name="Hintergrund-Testbank").count() == 1


def test_ergebnis_abholen_ohne_vorherigen_hintergrund_starten_liefert_none():
    assert kuendigung_recherche.ergebnis_abholen("nie-gestartet", timeout=0.1) is None


def test_hintergrund_starten_dedupliziert_laufenden_schluessel(monkeypatch):
    """Analog zu test_kwk_recherche.test_hintergrund_starten_dedupliziert_
    laufenden_schluessel: ein zweiter hintergrund_starten() für denselben
    Schlüssel, während der erste Thread noch läuft, darf keine zweite
    (kostenpflichtige) Recherche auslösen."""
    aufrufe = []
    laeuft = threading.Event()
    weitermachen = threading.Event()

    def _blockierender_client():
        class _Blockierend:
            class messages:
                @staticmethod
                def parse(**kwargs):
                    aufrufe.append(1)
                    laeuft.set()
                    weitermachen.wait(2.0)
                    raise RuntimeError("nur zum Zaehlen der Aufrufe")

        return _Blockierend()

    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", _blockierender_client)

    kuendigung_recherche.hintergrund_starten("dedup-kuendigung", "C24", "Girokonto")
    assert laeuft.wait(2.0)
    kuendigung_recherche.hintergrund_starten("dedup-kuendigung", "C24", "Girokonto")
    weitermachen.set()
    kuendigung_recherche.ergebnis_abholen("dedup-kuendigung", timeout=2.0)

    assert len(aufrufe) == 1


def test_ergebnis_abholen_bei_zu_kurzem_timeout_liefert_none(monkeypatch):
    def _langsamer_client():
        class _Langsam:
            class messages:
                @staticmethod
                def parse(**kwargs):
                    time.sleep(0.3)
                    raise RuntimeError("absichtlich langsam und fehlschlagend")

        return _Langsam()

    monkeypatch.setattr(kuendigung_recherche, "anthropic_client", _langsamer_client)

    kuendigung_recherche.hintergrund_starten("langsam-kuendigung", "Langsam", "Depot")
    ergebnis = kuendigung_recherche.ergebnis_abholen("langsam-kuendigung", timeout=0.01)

    assert ergebnis is None


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
