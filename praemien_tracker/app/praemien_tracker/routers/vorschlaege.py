from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..finder import matching
from ..finder.lauf import taeglicher_lauf
from ..helpers import build_deal_from_import
from ..ingress import redirect
from ..models import DealVorschlag, FinderLauf
from ..schemas import DealImport
from ..templating import templates

router = APIRouter()
logger = logging.getLogger("praemien_tracker.finder")

# Reihenfolge der Statusgruppen wie im Konzept-Mockup: erst eindeutig
# vorgeschlagene, dann zu prüfende, ganz unten (eingeklappt) die
# automatisch abgelehnten.
STATUS_OFFEN = matching.STATUS_OFFEN


@router.get("/vorschlaege")
def vorschlaege_view(request: Request, db: Session = Depends(get_db)):
    alle = (
        db.query(DealVorschlag)
        .options(joinedload(DealVorschlag.inhaber), joinedload(DealVorschlag.bedingungen))
        .filter(DealVorschlag.status.in_(STATUS_OFFEN))
        .order_by(DealVorschlag.gefunden_am.desc())
        .all()
    )
    gruppen: dict[str, list[DealVorschlag]] = {s: [] for s in STATUS_OFFEN}
    for v in alle:
        gruppen[v.status].append(v)

    letzter_lauf = db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()

    return templates.TemplateResponse(
        "vorschlaege.html",
        {
            "request": request,
            "vorgeschlagen": gruppen[matching.STATUS_VORGESCHLAGEN],
            "zu_pruefen": gruppen[matching.STATUS_ZU_PRUEFEN],
            "automatisch_abgelehnt": gruppen[matching.STATUS_ABGELEHNT],
            "letzter_lauf": letzter_lauf,
        },
    )


@router.post("/vorschlaege/{vorschlag_id}/uebernehmen")
def uebernehmen(request: Request, vorschlag_id: int, db: Session = Depends(get_db)):
    """Legt Deal + Prämien/Bedingungen/URL aus roh_json an - über denselben
    Mechanismus wie der händische JSON-Import (Konzept Abschnitt 7). Auch aus
    "automatisch_abgelehnt" möglich, als bewusstes Überstimmen."""
    vorschlag = db.get(DealVorschlag, vorschlag_id)
    if vorschlag is None:
        raise HTTPException(status_code=404, detail=f"Vorschlag {vorschlag_id} nicht gefunden.")
    if vorschlag.status not in STATUS_OFFEN:
        return redirect(request, "vorschlaege")

    daten = DealImport.model_validate_json(vorschlag.roh_json)
    build_deal_from_import(db, daten)
    vorschlag.status = matching.STATUS_UEBERNOMMEN
    db.commit()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/{vorschlag_id}/verwerfen")
def verwerfen(request: Request, vorschlag_id: int, db: Session = Depends(get_db)):
    """Setzt nur den Status, keine Löschung - taucht dank Dedup gegen den
    Inhalts-Hash nicht erneut auf, solange sich am Fund nichts ändert."""
    vorschlag = db.get(DealVorschlag, vorschlag_id)
    if vorschlag is not None and vorschlag.status in STATUS_OFFEN:
        vorschlag.status = matching.STATUS_VERWORFEN
        db.commit()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/jetzt-suchen")
def jetzt_suchen(request: Request, db: Session = Depends(get_db)):
    """Manueller Anstoß des täglichen Laufs - nicht Teil des Konzepts, aber
    nötig, um Einrichtung und API-Key zu testen, ohne bis 06:00 Uhr zu warten.
    Fehler werden geloggt statt die Seite abstürzen zu lassen (z.B. fehlender
    oder ungültiger API-Key, Quelle nicht erreichbar)."""
    try:
        taeglicher_lauf(db)
    except Exception:
        logger.exception("Manueller KI-Deal-Finder-Lauf fehlgeschlagen.")
    return redirect(request, "vorschlaege")
