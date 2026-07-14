from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProtokollEintrag
from ..templating import templates

router = APIRouter()

ANZEIGE_LIMIT = 1000


@router.get("/protokoll")
def protokoll_view(request: Request, db: Session = Depends(get_db)):
    eintraege = (
        db.query(ProtokollEintrag)
        .order_by(ProtokollEintrag.zeitpunkt.desc(), ProtokollEintrag.id.desc())
        .limit(ANZEIGE_LIMIT)
        .all()
    )
    gesamt = db.query(ProtokollEintrag).count()

    return templates.TemplateResponse(
        "protokoll.html",
        {
            "request": request,
            "eintraege": eintraege,
            "gesamt": gesamt,
            "limit": ANZEIGE_LIMIT,
        },
    )
