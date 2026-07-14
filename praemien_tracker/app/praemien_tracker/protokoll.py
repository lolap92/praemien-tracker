"""Automatisches Änderungsprotokoll über SQLAlchemy-Session-Events.

Erfasst jede Änderung an den fachlichen Tabellen (Deal, Bank, Inhaber,
Praemie, Bedingung, Aufgabe, DealUrl) - unabhängig davon, über welche Route
sie ausgelöst wurde. Kein manuelles Loggen in den Routen nötig.

Ablauf pro Flush:
- before_flush: neue Objekte werden vorgemerkt (ihre id ist erst nach dem
  INSERT bekannt), geänderte Felder (vorher/nachher) und gelöschte Objekte
  (komplettes JSON vor dem Löschen) werden sofort erfasst.
- after_flush: die vorgemerkten neuen Objekte haben jetzt eine id, ihr
  komplettes JSON wird ergänzt.
- after_commit: alle gesammelten Einträge werden in einer eigenen, kurzen
  Session geschrieben - erst nachdem die eigentliche Änderung sicher
  committet ist.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, attributes

from .database import SessionLocal
from .models import Aufgabe, Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie, ProtokollEintrag

GETRACKTE_MODELLE = (Deal, Bank, Inhaber, Praemie, Bedingung, Aufgabe, DealUrl)
IGNORIERTE_FELDER = {"id", "erstellt_am", "geaendert_am"}


def _serialisiere(wert):
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, (datetime.date, datetime.datetime)):
        return wert.isoformat()
    return wert


def _spalten_snapshot(obj) -> dict:
    mapper = inspect(obj).mapper
    return {col.key: _serialisiere(getattr(obj, col.key)) for col in mapper.columns}


def _deal_snapshot(deal: Deal) -> dict:
    daten = _spalten_snapshot(deal)
    daten["bank"] = deal.bank.name if deal.bank else None
    daten["inhaber"] = deal.inhaber.name if deal.inhaber else None
    daten["praemien"] = [_spalten_snapshot(p) for p in deal.praemien]
    daten["bedingungen"] = [_spalten_snapshot(b) for b in deal.bedingungen]
    daten["aufgaben"] = [_spalten_snapshot(a) for a in deal.aufgaben]
    daten["urls"] = [_spalten_snapshot(u) for u in deal.urls]
    return daten


def _voller_snapshot(obj) -> dict:
    if isinstance(obj, Deal):
        return _deal_snapshot(obj)
    return _spalten_snapshot(obj)


def _deal_id_von(obj) -> int | None:
    if isinstance(obj, Deal):
        return obj.id
    return getattr(obj, "deal_id", None)


def _dirty_feld_aenderungen(obj):
    mapper = inspect(obj).mapper
    for col in mapper.columns:
        if col.key in IGNORIERTE_FELDER:
            continue
        hist = attributes.get_history(obj, col.key)
        if not hist.has_changes():
            continue
        alt = hist.deleted[0] if hist.deleted else None
        neu = hist.added[0] if hist.added else getattr(obj, col.key)
        yield col.key, _serialisiere(alt), _serialisiere(neu)


@event.listens_for(Session, "before_flush")
def _before_flush(session, flush_context, instances):
    eintraege = session.info.setdefault("protokoll_eintraege", [])
    neu_pending = session.info.setdefault("protokoll_neu_pending", [])

    for obj in session.new:
        if isinstance(obj, GETRACKTE_MODELLE):
            neu_pending.append(obj)

    for obj in session.dirty:
        if not isinstance(obj, GETRACKTE_MODELLE):
            continue
        for feld, alt, neu in _dirty_feld_aenderungen(obj):
            eintraege.append(
                {
                    "tabelle": type(obj).__name__,
                    "objekt_id": obj.id,
                    "deal_id": _deal_id_von(obj),
                    "aktion": "geaendert",
                    "feld": feld,
                    "alter_wert": None if alt is None else str(alt),
                    "neuer_wert": None if neu is None else str(neu),
                }
            )

    for obj in session.deleted:
        if not isinstance(obj, GETRACKTE_MODELLE):
            continue
        eintraege.append(
            {
                "tabelle": type(obj).__name__,
                "objekt_id": obj.id,
                "deal_id": _deal_id_von(obj),
                "aktion": "geloescht",
                "feld": None,
                "alter_wert": json.dumps(_voller_snapshot(obj), ensure_ascii=False),
                "neuer_wert": None,
            }
        )


@event.listens_for(Session, "after_flush")
def _after_flush(session, flush_context):
    eintraege = session.info.setdefault("protokoll_eintraege", [])
    neu_pending = session.info.pop("protokoll_neu_pending", [])
    for obj in neu_pending:
        eintraege.append(
            {
                "tabelle": type(obj).__name__,
                "objekt_id": obj.id,
                "deal_id": _deal_id_von(obj),
                "aktion": "erstellt",
                "feld": None,
                "alter_wert": None,
                "neuer_wert": json.dumps(_voller_snapshot(obj), ensure_ascii=False),
            }
        )


@event.listens_for(Session, "after_commit")
def _after_commit(session):
    eintraege = session.info.pop("protokoll_eintraege", [])
    session.info.pop("protokoll_neu_pending", None)
    if not eintraege:
        return
    with SessionLocal() as log_session:
        for e in eintraege:
            log_session.add(ProtokollEintrag(**e))
        log_session.commit()


@event.listens_for(Session, "after_rollback")
def _after_rollback(session):
    session.info.pop("protokoll_eintraege", None)
    session.info.pop("protokoll_neu_pending", None)
