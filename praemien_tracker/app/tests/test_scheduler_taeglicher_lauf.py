"""main._scheduler_starten: KI-Deal-Finder und Kündigungshinweis-Batch sind
über je eigene, unabhängige Optionen abschaltbar."""

from __future__ import annotations

from praemien_tracker import main


def test_scheduler_startet_job_wenn_aktiv(monkeypatch):
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", True)
    monkeypatch.setattr(main, "KUENDIGUNG_HINWEISE_BATCH_AKTIV", False)
    scheduler = main._scheduler_starten()
    try:
        assert scheduler.get_job("ki_deal_finder") is not None
    finally:
        scheduler.shutdown(wait=False)


def test_scheduler_startet_keinen_job_wenn_deaktiviert(monkeypatch):
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", False)
    monkeypatch.setattr(main, "KUENDIGUNG_HINWEISE_BATCH_AKTIV", False)
    scheduler = main._scheduler_starten()
    try:
        assert scheduler.get_job("ki_deal_finder") is None
    finally:
        scheduler.shutdown(wait=False)


def test_scheduler_startet_kuendigungshinweis_batch_wenn_aktiv(monkeypatch):
    """Läuft um 02:00 Uhr, deutlich vor dem KI-Deal-Finder um 06:00, damit
    beide nicht gleichzeitig gegen dieselbe SQLite-Datenbank schreiben."""
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", False)
    monkeypatch.setattr(main, "KUENDIGUNG_HINWEISE_BATCH_AKTIV", True)
    scheduler = main._scheduler_starten()
    try:
        job = scheduler.get_job("kuendigung_hinweise")
        assert job is not None
        assert (job.trigger.fields[5].expressions[0].first, job.trigger.fields[6].expressions[0].first) == (2, 0)
    finally:
        scheduler.shutdown(wait=False)


def test_scheduler_startet_keinen_kuendigungshinweis_batch_wenn_deaktiviert(monkeypatch):
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", True)
    monkeypatch.setattr(main, "KUENDIGUNG_HINWEISE_BATCH_AKTIV", False)
    scheduler = main._scheduler_starten()
    try:
        assert scheduler.get_job("kuendigung_hinweise") is None
    finally:
        scheduler.shutdown(wait=False)


def test_beide_optionen_sind_unabhaengig_voneinander(monkeypatch):
    """Kernanliegen: die beiden Jobs lassen sich getrennt voneinander
    an-/abschalten, keine der beiden Optionen steuert den jeweils anderen
    Job mit."""
    monkeypatch.setattr(main, "TAEGLICHER_LAUF_AKTIV", True)
    monkeypatch.setattr(main, "KUENDIGUNG_HINWEISE_BATCH_AKTIV", True)
    scheduler = main._scheduler_starten()
    try:
        assert scheduler.get_job("ki_deal_finder") is not None
        assert scheduler.get_job("kuendigung_hinweise") is not None
    finally:
        scheduler.shutdown(wait=False)
