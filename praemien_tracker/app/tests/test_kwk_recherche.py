"""kwk_recherche.py - kein echtes Netzwerk, der Anthropic-Client wird
gefaked (analog zu test_kuendigung_recherche.py). Anders als bei der
Kündigungsweg-Recherche gibt es hier bewusst keinen Cache, und ein
fehlgeschlagenes Ergebnis wird explizit von einem "kein Programm" unterschieden
(siehe moeglichkeit_recherchieren-Docstring: (url, fehlgeschlagen))."""

from __future__ import annotations

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
