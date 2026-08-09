"""kwk_recherche.py - kein echtes Netzwerk, der Anthropic-Client wird
gefaked (analog zu test_kuendigung_recherche.py). Anders als bei der
Kündigungsweg-Recherche gibt es hier bewusst keinen Cache, und ein
fehlgeschlagenes Ergebnis wird explizit von einem "kein Programm" unterschieden
(siehe moeglichkeit_recherchieren-Docstring: (url, fehlgeschlagen))."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from praemien_tracker import kwk_recherche


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
    daten = {"moeglich": True, "url": "https://bank.example/kwk"}
    daten.update(overrides)
    return kwk_recherche._KwkErgebnis(**daten)


def test_ohne_api_key_liefert_kein_ergebnis_und_keinen_fehler(monkeypatch):
    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: None)

    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert url is None
    assert fehlgeschlagen is False


def test_moeglich_liefert_die_url_ohne_fehler(monkeypatch):
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: client)

    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert url == "https://bank.example/kwk"
    assert fehlgeschlagen is False
    assert client.messages.aufrufe == 1


def test_nicht_moeglich_ist_kein_fehler(monkeypatch):
    """Ein verlässlich ermitteltes 'gibt es nicht' ist kein Fehlschlag -
    dafür soll kein Hinweis auf manuelle Prüfung erscheinen."""
    client = _FakeClient(_ergebnis(moeglich=False, url=""))
    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: client)

    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert url is None
    assert fehlgeschlagen is False


def test_moeglich_ohne_url_gilt_als_fehlgeschlagen(monkeypatch):
    """moeglich=True ohne belastbare URL ist ein unvollständiges Ergebnis -
    weder Aufgabe noch Link wären sinnvoll, also als Fehlschlag behandelt."""
    client = _FakeClient(_ergebnis(url=""))
    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: client)

    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert url is None
    assert fehlgeschlagen is True


def test_kein_auswertbares_ergebnis_gilt_als_fehlgeschlagen(monkeypatch):
    client = _FakeClient(None)
    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: client)

    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert url is None
    assert fehlgeschlagen is True


def test_api_fehler_gilt_als_fehlgeschlagen(monkeypatch):
    class _KaputterClient:
        class messages:
            @staticmethod
            def parse(**kwargs):
                raise RuntimeError("kaputt")

    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: _KaputterClient())

    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert url is None
    assert fehlgeschlagen is True


def test_zweiter_aufruf_ruft_erneut_die_api_auf(monkeypatch):
    """Bewusst kein Cache (anders als Kündigungsweg-Recherche): ein
    KwK-Programm ändert sich häufiger, ein veraltetes Ergebnis wäre riskanter
    als der zusätzliche Aufruf."""
    client = _FakeClient(_ergebnis())
    monkeypatch.setattr(kwk_recherche, "anthropic_client", lambda: client)

    kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")
    kwk_recherche.moeglichkeit_recherchieren("Testbank", "Girokonto")

    assert client.messages.aufrufe == 2


def test_hintergrund_starten_liefert_ergebnis_ueber_ergebnis_abholen(monkeypatch):
    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", lambda bank, kontoart: ("https://bank.example/kwk", False))

    kwk_recherche.hintergrund_starten("testbank|girokonto", "Testbank", "Girokonto")
    ergebnis = kwk_recherche.ergebnis_abholen("testbank|girokonto", timeout=2.0)

    assert ergebnis == ("https://bank.example/kwk", False)


def test_ergebnis_abholen_ohne_vorherigen_hintergrund_starten_liefert_none():
    assert kwk_recherche.ergebnis_abholen("nie-gestartet", timeout=0.1) is None


def test_hintergrund_starten_dedupliziert_laufenden_schluessel(monkeypatch):
    """Ein zweiter hintergrund_starten() für denselben Schlüssel, während der
    erste Thread noch läuft, darf keine zweite (kostenpflichtige) Recherche
    auslösen - die gefakte Recherche blockiert hier bewusst auf einem Event,
    damit der erste Thread beim zweiten Aufruf garantiert noch aktiv ist
    (sonst wäre der Test von der Ausführungsreihenfolge der Threads
    abhängig, siehe hintergrund_starten: ein schon *fertiger* Thread für
    denselben Schlüssel löst dagegen bewusst eine neue Recherche aus, siehe
    nächster Test)."""
    aufrufe = []
    laeuft = threading.Event()
    weitermachen = threading.Event()

    def _blockierende_recherche(bank, kontoart):
        aufrufe.append((bank, kontoart))
        laeuft.set()
        weitermachen.wait(2.0)
        return None, False

    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", _blockierende_recherche)

    kwk_recherche.hintergrund_starten("dedup-schluessel", "C24", "Girokonto")
    assert laeuft.wait(2.0)
    kwk_recherche.hintergrund_starten("dedup-schluessel", "C24", "Girokonto")
    weitermachen.set()
    kwk_recherche.ergebnis_abholen("dedup-schluessel", timeout=2.0)

    assert len(aufrufe) == 1


def test_hintergrund_starten_recherchiert_erneut_wenn_voriger_thread_fertig_ist(monkeypatch):
    """Anders als beim noch laufenden Thread (siehe voriger Test): ist die
    vorige Recherche für denselben Schlüssel schon fertig, aber nie über
    ergebnis_abholen() abgeholt worden (z.B. eine nie bestätigte Vorschau),
    soll ein späterer, unabhängiger Übernehmen-Vorgang trotzdem frisch
    recherchieren statt für immer auf dem alten Ergebnis sitzen zu bleiben -
    bewusst kein Cache, siehe Moduldocstring."""
    aufrufe = []
    monkeypatch.setattr(
        kwk_recherche,
        "moeglichkeit_recherchieren",
        lambda bank, kontoart: aufrufe.append((bank, kontoart)) or (None, False),
    )

    kwk_recherche.hintergrund_starten("nie-abgeholt", "C24", "Girokonto")
    kwk_recherche._threads["nie-abgeholt"].join(2.0)  # sicherstellen, dass der erste Thread fertig ist

    kwk_recherche.hintergrund_starten("nie-abgeholt", "C24", "Girokonto")
    kwk_recherche.ergebnis_abholen("nie-abgeholt", timeout=2.0)

    assert len(aufrufe) == 2


def test_ergebnis_abholen_bei_zu_kurzem_timeout_liefert_none(monkeypatch):
    """Läuft die Recherche länger als der Aufrufer warten will (siehe
    helpers.KWK_TIMEOUT_SEKUNDEN), gibt es kein Ergebnis statt einer
    blockierenden Wartezeit - der Aufrufer fällt dann auf eine einfache
    Erinnerungs-Aufgabe zurück (helpers.kwk_ergebnis_anwenden)."""

    def _langsame_recherche(bank, kontoart):
        time.sleep(0.3)
        return "https://bank.example/kwk", False

    monkeypatch.setattr(kwk_recherche, "moeglichkeit_recherchieren", _langsame_recherche)

    kwk_recherche.hintergrund_starten("langsam|depot", "Langsam", "Depot")
    ergebnis = kwk_recherche.ergebnis_abholen("langsam|depot", timeout=0.01)

    assert ergebnis is None
