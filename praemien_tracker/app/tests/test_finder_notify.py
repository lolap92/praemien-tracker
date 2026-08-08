"""finder/notify.py - kein echtes Netzwerk, httpx.post wird gefaked."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praemien_tracker.finder import notify


class _FakeAntwort:
    def raise_for_status(self):
        pass


def test_ohne_token_wird_nur_geloggt_kein_aufruf(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0)

    assert aufrufe == []


def test_deaktiviert_loest_keinen_aufruf_aus_selbst_mit_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, aktiv=False)

    assert aufrufe == []


def test_aktiv_mit_token_ruft_standarddienst_notify_auf(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(2, 1)

    assert len(aufrufe) == 1
    (url, *_), kwargs = aufrufe[0]
    assert url == "http://supervisor/core/api/services/notify/notify"
    assert kwargs["headers"]["Authorization"] == "Bearer geheim"
    assert "2 neue Vorschläge" in kwargs["json"]["message"]
    assert "1 zu prüfen" in kwargs["json"]["message"]


def test_konfigurierter_dienst_adressiert_gezielt_ein_geraet(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, geraete=["mobile_app_pixel_8"])

    (url, *_), _ = aufrufe[0]
    assert url == "http://supervisor/core/api/services/notify/mobile_app_pixel_8"


def test_mehrere_geraete_werden_alle_benachrichtigt(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufrufe = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: aufrufe.append((a, kw)) or _FakeAntwort())

    notify.benachrichtigen(1, 0, geraete=["mobile_app_pixel_8", "mobile_app_iphone_anna"])

    urls = [a[0] for a, _ in aufrufe]
    assert urls == [
        "http://supervisor/core/api/services/notify/mobile_app_pixel_8",
        "http://supervisor/core/api/services/notify/mobile_app_iphone_anna",
    ]


def test_fehlerhaftes_geraet_blockiert_die_anderen_nicht(monkeypatch):
    """Ein Tippfehler im Dienstnamen eines Geräts soll die Benachrichtigung
    an die übrigen konfigurierten Geräte nicht verhindern."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")

    class _FehlerAntwort:
        def raise_for_status(self):
            raise RuntimeError("HTTP 404")

    aufrufe = []

    def fake_post(url, **kwargs):
        aufrufe.append(url)
        if "kaputt" in url:
            return _FehlerAntwort()
        return _FakeAntwort()

    monkeypatch.setattr(notify.httpx, "post", fake_post)

    notify.benachrichtigen(1, 0, geraete=["mobile_app_kaputt", "mobile_app_pixel_8"])

    assert len(aufrufe) == 2  # beide Geräte wurden versucht, keins übersprungen
