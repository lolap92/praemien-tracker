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

    notify.benachrichtigen(1, 0, dienst="mobile_app_pixel_8")

    (url, *_), _ = aufrufe[0]
    assert url == "http://supervisor/core/api/services/notify/mobile_app_pixel_8"
