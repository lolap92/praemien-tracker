"""auszahlungs_sync.py - kein echtes Netzwerk, httpx.post wird gefaked."""

from __future__ import annotations

from decimal import Decimal

import pytest

from praemien_tracker import auszahlungs_sync
from praemien_tracker.models import Bank, Deal, Inhaber, Praemie


class _FakeAntwort:
    def raise_for_status(self):
        pass


@pytest.fixture
def deal(db):
    d = Deal(kontoart="Girokonto", bank=Bank(name="Testbank"), inhaber=Inhaber(name="Max"))
    db.add(d)
    db.commit()
    return d


@pytest.fixture
def aufrufe(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufgezeichnet = []
    monkeypatch.setattr(
        auszahlungs_sync.httpx,
        "post",
        lambda *a, **kw: aufgezeichnet.append(kw["json"]) or _FakeAntwort(),
    )
    return aufgezeichnet


def test_ohne_token_wird_nichts_gesendet(db, deal, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    aufgerufen = []
    monkeypatch.setattr(
        auszahlungs_sync.httpx, "post", lambda *a, **kw: aufgerufen.append(kw) or _FakeAntwort()
    )

    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()

    assert aufgerufen == []


def test_neue_praemie_mit_erwartetem_monat_wird_gemeldet(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100.00"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()

    assert len(aufrufe) == 1
    payload = aufrufe[0]
    assert payload["aktion"] == "upsert"
    assert payload["external_id"] == f"praemientracker:{praemie.id}"
    assert Decimal(payload["betrag"]) == Decimal("100.00")
    assert payload["datum"] == "2026-09-15"


def test_neue_praemie_ohne_erwarteten_monat_wird_nicht_gemeldet(db, deal, aufrufe):
    praemie = Praemie(deal_id=deal.id, quelle="bank", betrag=Decimal("50"), erhalten=False, auszahlung_erwartet=None)
    db.add(praemie)
    db.commit()

    assert aufrufe == []


def test_betragsaenderung_wird_als_upsert_gemeldet(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    praemie.betrag = Decimal("150.00")
    db.commit()

    assert len(aufrufe) == 1
    assert aufrufe[0]["aktion"] == "upsert"
    assert Decimal(aufrufe[0]["betrag"]) == Decimal("150.00")


def test_erhalten_markiert_loest_loeschen_aus(db, deal, aufrufe):
    """Eine bereits erhaltene Auszahlung soll die Forecast-Prognose im
    Budget-Tracker nicht länger belasten."""
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    praemie.erhalten = True
    db.commit()

    assert aufrufe == [{"external_id": f"praemientracker:{praemie.id}", "aktion": "loeschen"}]


def test_geloeschte_praemie_meldet_loeschen(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()
    praemie_id = praemie.id

    db.delete(praemie)
    db.commit()

    assert aufrufe == [{"external_id": f"praemientracker:{praemie_id}", "aktion": "loeschen"}]


def test_unveraenderter_commit_loest_kein_event_aus(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    db.commit()

    assert aufrufe == []
