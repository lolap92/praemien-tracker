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
    alle_deals = (
        db.query(Deal)
        .join(Bank)
        .options(joinedload(Deal.bank), joinedload(Deal.inhaber), joinedload(Deal.praemien))
        .order_by(Bank.name)
        .all()
    )
    # Abgeschlossene und gekündigte Deals (storniert oder bestätigt gekündigt,
    # siehe derived.status) sind für die Datenqualität nicht mehr relevant -
    # an ihren Daten ändert sich nichts mehr, sie müssen hier nicht mehr
    # auftauchen und auch nicht mitgezählt werden.
    deals = [d for d in alle_deals if derived.status(d) != derived.STATUS_ABGESCHLOSSEN]

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
