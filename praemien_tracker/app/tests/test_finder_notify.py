"""finder/notify.py - kein echtes Netzwerk, httpx.post wird gefaked."""

from __future__ import annotations

from praemien_tracker.finder import notify


class _FakeAntwort:
    def raise_for_status(self):
        pass


def test_ohne_token_wird_nur_geloggt_kein_aufruf(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, geraete=["sm_g990b"])

    assert aufrufe == []


def test_deaktiviert_loest_keinen_aufruf_aus_selbst_mit_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, aktiv=False, geraete=["sm_g990b"])

    assert aufrufe == []


def test_ohne_zielgeraete_wird_nur_geloggt_kein_aufruf(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, geraete=[])

    assert aufrufe == []


def test_aktiv_mit_token_ruft_das_benachrichtigungsskript_auf(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(2, 1, geraete=["sm_g990b", "fp5"])

    assert len(aufrufe) == 1
    (url, *_), kwargs = aufrufe[0]
    assert url == "http://supervisor/core/api/services/script/benachrichtigung_senden"
    assert kwargs["headers"]["Authorization"] == "Bearer geheim"
    assert kwargs["json"]["geraete"] == ["sm_g990b", "fp5"]
    assert kwargs["json"]["titel"] == "Prämien-Tracker"
    assert kwargs["json"]["quelle"] == "Prämien-Tracker"
    assert "2 neue Vorschläge" in kwargs["json"]["nachricht"]
    assert "1 zu prüfen" in kwargs["json"]["nachricht"]


def test_konfigurierte_geraete_werden_in_einem_aufruf_gebuendelt(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, geraete=["sm_g990b", "sm_g990u"])

    assert len(aufrufe) == 1
    (_, *_), kwargs = aufrufe[0]
    assert kwargs["json"]["geraete"] == ["sm_g990b", "sm_g990u"]


def test_fehlgeschlagener_skript_aufruf_gibt_false_zurueck(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")

    class _FehlerAntwort:
        def raise_for_status(self):
            raise RuntimeError("HTTP 404")

    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: _FehlerAntwort())

    ergebnis = notify.benachrichtigen(1, 0, geraete=["sm_g990b"])

    assert ergebnis is False
