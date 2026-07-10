from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..models import Bank, Deal
from ..templating import templates

router = APIRouter()


@router.get("/completeness")
def completeness_view(request: Request, db: Session = Depends(get_db)):
    deals = (
        db.query(Deal)
        .join(Bank)
        .options(joinedload(Deal.bank), joinedload(Deal.inhaber), joinedload(Deal.praemien))
        .order_by(Bank.name)
        .all()
    )

    zeilen = []
    for d in deals:
        offen = derived.offene_felder(d)
        if offen:
            zeilen.append({"deal": d, "offene_felder": offen})

    return templates.TemplateResponse(
        "completeness.html",
        {
            "request": request,
            "zeilen": zeilen,
            "anzahl_gesamt": len(deals),
            "anzahl_vollstaendig": len(deals) - len(zeilen),
        },
    )
