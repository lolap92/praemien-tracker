"""Meldet Änderungen an Prämien-Auszahlungen als Home-Assistant-Event, damit
der Budget-Tracker (separates Add-on) daraus automatisch einen Forecast-
Eintrag im Topf "Sonderausgaben" anlegt, aktualisiert oder entfernt.

Eigene, schlanke Session-Event-Listener statt Anhängen an protokoll.py: dort
geht es um die lückenlose Änderungshistorie aller Modelle, hier nur um
Praemie und mit eigener Entscheidungslogik (erhalten/auszahlung_erwartet
bestimmen, ob überhaupt ein Forecast-Eintrag sinnvoll ist). Ablauf wie bei
protokoll.py: before_flush merkt neue/geänderte/gelöschte Praemien vor,
after_flush ergänzt die inzwischen vergebene id neuer Zeilen, after_commit
verschickt die Events - erst, wenn die Änderung sicher committet ist.

Der Budget-Tracker hat kein festes Tages-Datum für eine Auszahlung (nur den
Monat in `auszahlung_erwartet`), erwartet für einen Forecast-Eintrag aber ein
konkretes Datum - der 15. des erwarteten Monats dient als grobe Annäherung.
"""

from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, attributes, joinedload

from .database import SessionLocal
from .models import Bank, Deal, Inhaber, Praemie

logger = logging.getLogger("praemien_tracker.sync")

SUPERVISOR_EVENT_URL_VORLAGE = "http://supervisor/core/api/events/{event_typ}"
EVENT_TYP = "praemien_auszahlung_geaendert"


def _external_id(praemie_id: int) -> str:
    return f"praemientracker:{praemie_id}"


def _ist_geaendert(obj: Praemie) -> bool:
    mapper = inspect(obj).mapper
    for col in mapper.columns:
        if col.key == "id":
            continue
        if attributes.get_history(obj, col.key).has_changes():
            return True
    return False


def _deal_von(praemie: Praemie) -> Deal | None:
    """praemie.deal kann an einer druckfrisch erzeugten Prämie (INSERT gerade
    erst geflusht) leer bleiben, wenn nur deal_id statt der Objektzuweisung
    gesetzt wurde - SQLAlchemy löst eine Beziehung an einem frisch erzeugten
    Objekt innerhalb von after_flush nicht zuverlässig lazy auf (derselbe
    Fall wie protokoll.py::_bank_von). Ein Session.get() auf denselben
    Fremdschlüssel funktioniert davon unabhängig. Die App selbst hängt eine
    neue Prämie immer über deal.praemien.append(...) an (setzt die Beziehung
    direkt), betrifft also nur diesen Randfall."""
    if praemie.deal is not None:
        return praemie.deal
    sitzung = inspect(praemie).session
    return sitzung.get(Deal, praemie.deal_id) if sitzung is not None else None


def _bank_von(deal: Deal) -> Bank | None:
    """Derselbe Randfall wie _deal_von, eine Ebene tiefer: deal.bank kann bei
    einem ebenfalls druckfrischen Deal leer bleiben."""
    if deal.bank is not None:
        return deal.bank
    sitzung = inspect(deal).session
    return sitzung.get(Bank, deal.bank_id) if sitzung is not None else None


def _inhaber_von(deal: Deal) -> Inhaber | None:
    if deal.inhaber is not None:
        return deal.inhaber
    sitzung = inspect(deal).session
    return sitzung.get(Inhaber, deal.inhaber_id) if sitzung is not None else None


def _vorkommen_payload(praemie: Praemie) -> dict | None:
    """None, wenn für diese Prämie aktuell kein Forecast-Eintrag sinnvoll ist
    (schon erhalten oder noch kein erwarteter Monat gepflegt) - der
    Budget-Tracker entfernt in dem Fall einen zuvor angelegten Eintrag."""
    if praemie.erhalten or not praemie.auszahlung_erwartet:
        return None
    deal = _deal_von(praemie)
    bank = _bank_von(deal) if deal else None
    inhaber = _inhaber_von(deal) if deal else None
    # Bank/Kontoart/Inhaber ergänzt, damit mehrere Forecast-Einträge im
    # Budget-Tracker (eigenständige Liste, ohne Bezug zu unseren Deals)
    # auseinanderzuhalten sind - vorher zeigten mehrere Prämien ohne eigenen
    # "zweck" dort alle identisch nur "Prämienauszahlung".
    grunddaten = f"{bank.name} · {deal.kontoart} · {inhaber.name}" if deal and bank and inhaber else None
    zweck_oder_default = praemie.zweck or "Prämienauszahlung"
    bezeichnung = f"{zweck_oder_default} – {grunddaten}" if grunddaten else zweck_oder_default
    return {
        "external_id": _external_id(praemie.id),
        "aktion": "upsert",
        "bezeichnung": bezeichnung,
        "betrag": str(praemie.betrag),
        "datum": f"{praemie.auszahlung_erwartet}-15",
    }


def _sende_event(payload: dict, *, timeout: float = 10.0) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        logger.info("Kein SUPERVISOR_TOKEN gesetzt - Auszahlungs-Sync-Event übersprungen: %s", payload)
        return
    try:
        antwort = httpx.post(
            SUPERVISOR_EVENT_URL_VORLAGE.format(event_typ=EVENT_TYP),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        antwort.raise_for_status()
    except Exception:
        logger.exception("Auszahlungs-Sync-Event fehlgeschlagen: %s", payload)
    else:
        # Bestätigt nur, dass Home Assistant das Event entgegengenommen hat -
        # nicht, dass der Budget-Tracker gerade zuhört (HA-Events werden nicht
        # nachgeliefert). Ohne diese Zeile liesse sich im Log nicht
        # unterscheiden, ob ein Event nie gesendet oder nur nie empfangen wurde.
        logger.info("Auszahlungs-Sync-Event gesendet: %s", payload)


def sende_alle_aktuellen() -> int:
    """Meldet den aktuellen Stand jeder vorhandenen Prämie, unabhängig von
    einer Änderung - für den Nachtrag beim Start (siehe main.py).

    Die Ereignis-Listener unten melden nur, was sich *ab jetzt* ändert. Ohne
    diesen Nachtrag bliebe jede Prämie, die schon vor der Einführung dieses
    Sync-Mechanismus einen erwarteten Auszahlungsmonat hatte, im
    Budget-Tracker unsichtbar, bis sie zufällig einmal bearbeitet wird. Läuft
    bei jedem Start erneut - kostet nur ein paar HTTP-Aufrufe und ist über die
    external_id beim Budget-Tracker ohnehin idempotent."""
    with SessionLocal() as db:
        # Bank/Inhaber gleich mitladen (_vorkommen_payload braucht sie für
        # die bezeichnung) - die Schleife läuft erst nach dem "with"-Block,
        # wenn die Session schon geschlossen ist, ein Lazy Load dann würde
        # mit DetachedInstanceError abbrechen.
        praemien = (
            db.query(Praemie)
            .options(joinedload(Praemie.deal).joinedload(Deal.bank), joinedload(Praemie.deal).joinedload(Deal.inhaber))
            .all()
        )
    for praemie in praemien:
        payload = _vorkommen_payload(praemie)
        if payload is not None:
            _sende_event(payload)
        else:
            _sende_event({"external_id": _external_id(praemie.id), "aktion": "loeschen"})
    return len(praemien)


@event.listens_for(Session, "before_flush")
def _before_flush(session, flush_context, instances):
    """Payload wird bewusst schon hier (bzw. in after_flush) fertig gebaut
    statt erst in after_commit: _vorkommen_payload() liest jetzt auch
    praemie.deal.bank/.kontoart/.inhaber, und ein lazy load davon schlägt in
    after_commit fehl ("session is in 'committed' state") - die Transaktion
    ist zu dem Zeitpunkt bereits abgeschlossen. Vor/während des Flushs ist
    die Session dagegen ganz normal abfragbar."""
    aktionen = session.info.setdefault("auszahlungs_sync_aktionen", [])
    neu_pending = session.info.setdefault("auszahlungs_sync_neu_pending", [])

    for obj in session.new:
        if isinstance(obj, Praemie):
            neu_pending.append(obj)

    for obj in session.dirty:
        if isinstance(obj, Praemie) and _ist_geaendert(obj):
            aktionen.append(("geaendert", obj.id, _vorkommen_payload(obj)))

    for obj in session.deleted:
        if isinstance(obj, Praemie):
            aktionen.append(("geloescht", obj.id, None))


@event.listens_for(Session, "after_flush")
def _after_flush(session, flush_context):
    aktionen = session.info.setdefault("auszahlungs_sync_aktionen", [])
    neu_pending = session.info.pop("auszahlungs_sync_neu_pending", [])
    for obj in neu_pending:
        aktionen.append(("erstellt", obj.id, _vorkommen_payload(obj)))


@event.listens_for(Session, "after_commit")
def _after_commit(session):
    aktionen = session.info.pop("auszahlungs_sync_aktionen", [])
    session.info.pop("auszahlungs_sync_neu_pending", None)

    for art, praemie_id, payload in aktionen:
        if art == "geloescht":
            _sende_event({"external_id": _external_id(praemie_id), "aktion": "loeschen"})
            continue
        if payload is not None:
            _sende_event(payload)
        elif art == "geaendert":
            # Nur bei einer Änderung kann vorher ein Forecast-Eintrag
            # existiert haben, der jetzt zurückgezogen werden muss - eine
            # neu angelegte Prämie ohne erwarteten Monat wurde nie gemeldet.
            _sende_event({"external_id": _external_id(praemie_id), "aktion": "loeschen"})


@event.listens_for(Session, "after_rollback")
def _after_rollback(session):
    session.info.pop("auszahlungs_sync_aktionen", None)
    session.info.pop("auszahlungs_sync_neu_pending", None)
