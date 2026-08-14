from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..ingress import redirect
from ..models import Deal, Aufgabe
from ..templating import templates
from .vorschlaege import zaehlen as vorschlaege_zaehlen

router = APIRouter()


@router.get("/")
def root(request: Request):
    return redirect(request, "overview")


@router.get("/overview")
def overview(request: Request, db: Session = Depends(get_db)):
    deals = (
        db.query(Deal)
        .options(
            joinedload(Deal.bank),
            joinedload(Deal.inhaber),
            joinedload(Deal.praemien),
            joinedload(Deal.bedingungen),
        )
        .all()
    )
    aufgaben = (
        db.query(Aufgabe)
        .options(
            joinedload(Aufgabe.deal).joinedload(Deal.bank),
            joinedload(Aufgabe.deal).joinedload(Deal.inhaber),
        )
        .all()
    )

    gesamt_kennzahlen = derived.kennzahlen([p for d in deals for p in d.praemien])

    nach_status: dict[str, list[Deal]] = {s: [] for s in derived.STATUS_ORDER}
    for d in deals:
        nach_status[derived.status(d)].append(d)

    # "Deal pflegen" ist bewusst kein siebter Pipeline-Status (siehe
    # derived.deal_todos): ein Deal kann gleichzeitig in einem der sechs
    # echten Status UND hier auftauchen, deshalb läuft die Zählung getrennt
    # von nach_status statt sie zu ersetzen. Abgeschlossene Deals zählen
    # nicht mehr mit, ihre Daten ändern sich nicht mehr.
    alle_todos = derived.alle_todos(deals, aufgaben)
    anzahl_manuelle_aufgaben = sum(1 for t in alle_todos if t.kategorie == "Manuelle Aufgaben")
    anzahl_deal_pflegen = sum(1 for t in alle_todos if t.kategorie == "Deal pflegen")
    anzahl_zu_pruefen = sum(1 for t in alle_todos if t.kategorie == "Zu prüfen")

    vorschlag_zaehler = vorschlaege_zaehlen(db)

    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "kennzahlen": gesamt_kennzahlen,
            "nach_status": nach_status,
            "status_labels": derived.STATUS_LABELS,
            "status_order": derived.STATUS_ORDER,
            "anzahl_deals": len(deals),
            "anzahl_manuelle_aufgaben": anzahl_manuelle_aufgaben,
            "anzahl_deal_pflegen": anzahl_deal_pflegen,
            "anzahl_zu_pruefen": anzahl_zu_pruefen,
            "vorschlag_zaehler": vorschlag_zaehler,
        },
    )
