from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProtokollEintrag
from ..templating import templates

router = APIRouter()

PRO_SEITE = 200


@router.get("/protokoll")
def protokoll_view(request: Request, seite: str = "1", db: Session = Depends(get_db)):
    gesamt = db.query(ProtokollEintrag).count()
    seiten = max(1, -(-gesamt // PRO_SEITE))
    # Unbrauchbare Seitenangaben (Text, 0, negativ, jenseits des Endes) landen
    # auf der ersten bzw. letzten Seite, statt die Seite mit einem Fehler
    # abzubrechen.
    try:
        nummer = int(seite)
    except (TypeError, ValueError):
        nummer = 1
    seite = min(max(nummer, 1), seiten)

    eintraege = (
        db.query(ProtokollEintrag)
        .order_by(ProtokollEintrag.zeitpunkt.desc(), ProtokollEintrag.id.desc())
        .offset((seite - 1) * PRO_SEITE)
        .limit(PRO_SEITE)
        .all()
    )

    return templates.TemplateResponse(
        "protokoll.html",
        {
            "request": request,
            "eintraege": eintraege,
            "gesamt": gesamt,
            "seite": seite,
            "seiten": seiten,
            "pro_seite": PRO_SEITE,
        },
    )
