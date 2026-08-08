"""main._scheduler_starten: täglicher Lauf per Option abschaltbar."""

from __future__ import annotations

from praemien_tracker import main


def test_scheduler_startet_job_wenn_aktiv(monkeypatch):
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", True)
    scheduler = main._scheduler_starten()
    try:
        assert scheduler.get_job("ki_deal_finder") is not None
    finally:
        scheduler.shutdown(wait=False)


def test_scheduler_startet_keinen_job_wenn_deaktiviert(monkeypatch):
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", False)
    scheduler = main._scheduler_starten()
    try:
        assert scheduler.get_job("ki_deal_finder") is None
    finally:
        scheduler.shutdown(wait=False)
