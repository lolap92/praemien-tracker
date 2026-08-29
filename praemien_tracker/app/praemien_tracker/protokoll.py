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
import logging
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, attributes

from . import derived
from .database import SessionLocal
from .models import Aufgabe, Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie, ProtokollEintrag
from .templating import templates

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


def _kontext_von(obj) -> tuple[str | None, str | None, str | None]:
    """(bank_name, inhaber_name, kontoart) - für Deals direkt, für
    Deal-Kinder über die Beziehung, für Bank/Inhaber nur der eigene Name.
    Wird zum Zeitpunkt des Eintrags aufgelöst und denormalisiert
    gespeichert, damit der Kontext auch nach dem Löschen des Deals noch
    im Protokoll lesbar bleibt."""
    deal = _deal_von(obj)
    if deal is not None:
        bank = _bank_von(deal)
        inhaber = _inhaber_von(deal)
        return (bank.name if bank else None), (inhaber.name if inhaber else None), deal.kontoart
    if isinstance(obj, Bank):
        return obj.name, None, None
    if isinstance(obj, Inhaber):
        return None, obj.name, None
    return None, None, None


def _deal_von(obj) -> Deal | None:
    """Der Deal, zu dem dieses Objekt gehört - das Objekt selbst, falls es
    schon ein Deal ist, sonst über die deal-Beziehung (Praemie, Bedingung,
    Aufgabe, DealUrl haben alle eine). Bank/Inhaber haben keinen einzelnen
    zugehörigen Deal - eine Namensänderung dort betrifft potenziell mehrere
    Deals, für die deshalb bewusst kein Snapshot entsteht."""
    if isinstance(obj, Deal):
        return obj
    return getattr(obj, "deal", None)


def _per_id_nachgeladen(deal: Deal, relationship_wert, modell, fremdschluessel_id):
    """Fallback für deal.bank/deal.inhaber, falls die Beziehung selbst noch
    nicht geladen ist. Betrifft nur ganz frisch angelegte Deals, deren
    bank_id/inhaber_id per rohem Fremdschlüssel statt per Objektzuweisung
    gesetzt wurden: SQLAlchemy liefert lazy-geladene Beziehungen an frisch
    erzeugten Objekten innerhalb von after_flush zuverlässig als None, ein
    direkter Session.get() auf denselben Fremdschlüssel funktioniert dort
    aber (siehe _html_snapshot_von-Testfall). Die App selbst weist beim
    Anlegen immer das Objekt direkt zu (deal.bank = ...), betrifft also nur
    diesen Randfall."""
    if relationship_wert is not None or fremdschluessel_id is None:
        return relationship_wert
    sitzung = inspect(deal).session
    return sitzung.get(modell, fremdschluessel_id) if sitzung is not None else None


def _bank_von(deal: Deal) -> Bank | None:
    return _per_id_nachgeladen(deal, deal.bank, Bank, deal.bank_id)


def _inhaber_von(deal: Deal) -> Inhaber | None:
    return _per_id_nachgeladen(deal, deal.inhaber, Inhaber, deal.inhaber_id)


def _html_snapshot_von(obj) -> str | None:
    """Rendert deal_snapshot.html für den zu diesem Objekt gehörenden Deal -
    eine eigenständige, von base.html/request unabhängige Momentaufnahme der
    Dealseite (siehe deal_snapshot.html), damit sie auch nach dem Löschen des
    Deals noch einsehbar bleibt. Ein Renderfehler darf die eigentliche
    Änderung nicht verhindern, deshalb wird er nur geloggt."""
    deal = _deal_von(obj)
    if deal is None:
        return None
    try:
        return templates.get_template("deal_snapshot.html").render(
            deal=deal,
            bank=_bank_von(deal),
            inhaber=_inhaber_von(deal),
            status=derived.status(deal),
            status_labels=derived.STATUS_LABELS,
            zeitpunkt=datetime.datetime.now(datetime.timezone.utc),
        )
    except Exception:
        logging.getLogger("praemien_tracker").exception(
            "Konnte Dealseiten-Snapshot für Deal %s nicht rendern.", deal.id
        )
        return None


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
        aenderungen = list(_dirty_feld_aenderungen(obj))
        if not aenderungen:
            continue
        snapshot_json = json.dumps(_voller_snapshot(obj), ensure_ascii=False)
        bank_name, inhaber_name, kontoart = _kontext_von(obj)
        html_snapshot = _html_snapshot_von(obj)
        for feld, alt, neu in aenderungen:
            eintraege.append(
                {
                    "tabelle": type(obj).__name__,
                    "objekt_id": obj.id,
                    "deal_id": _deal_id_von(obj),
                    "aktion": "geaendert",
                    "feld": feld,
                    "alter_wert": None if alt is None else str(alt),
                    "neuer_wert": None if neu is None else str(neu),
                    "json_snapshot": snapshot_json,
                    "bank_name": bank_name,
                    "inhaber_name": inhaber_name,
                    "kontoart": kontoart,
                    "html_snapshot": html_snapshot,
                }
            )

    for obj in session.deleted:
        if not isinstance(obj, GETRACKTE_MODELLE):
            continue
        snapshot_json = json.dumps(_voller_snapshot(obj), ensure_ascii=False)
        bank_name, inhaber_name, kontoart = _kontext_von(obj)
        eintraege.append(
            {
                "tabelle": type(obj).__name__,
                "objekt_id": obj.id,
                "deal_id": _deal_id_von(obj),
                "aktion": "geloescht",
                "feld": None,
                "alter_wert": snapshot_json,
                "neuer_wert": None,
                "json_snapshot": snapshot_json,
                "bank_name": bank_name,
                "inhaber_name": inhaber_name,
                "kontoart": kontoart,
                # Der wichtigste Fall für den Snapshot: nach dem Löschen ist
                # dies die letzte Gelegenheit, den Deal noch zu rendern.
                "html_snapshot": _html_snapshot_von(obj),
            }
        )


@event.listens_for(Session, "after_flush")
def _after_flush(session, flush_context):
    eintraege = session.info.setdefault("protokoll_eintraege", [])
    neu_pending = session.info.pop("protokoll_neu_pending", [])
    for obj in neu_pending:
        snapshot_json = json.dumps(_voller_snapshot(obj), ensure_ascii=False)
        bank_name, inhaber_name, kontoart = _kontext_von(obj)
        eintraege.append(
            {
                "tabelle": type(obj).__name__,
                "objekt_id": obj.id,
                "deal_id": _deal_id_von(obj),
                "aktion": "erstellt",
                "feld": None,
                "alter_wert": None,
                "neuer_wert": snapshot_json,
                "json_snapshot": snapshot_json,
                "bank_name": bank_name,
                "inhaber_name": inhaber_name,
                "kontoart": kontoart,
                "html_snapshot": _html_snapshot_von(obj),
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
