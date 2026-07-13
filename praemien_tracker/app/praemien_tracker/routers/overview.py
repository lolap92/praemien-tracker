from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..ingress import redirect
from ..models import Deal, Inhaber
from ..templating import templates

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

    gesamt_kennzahlen = derived.kennzahlen([p for d in deals for p in d.praemien])

    nach_status: dict[str, list[Deal]] = {s: [] for s in derived.STATUS_ORDER}
    for d in deals:
        nach_status[derived.status(d)].append(d)

    pro_inhaber = []
    for inh in db.query(Inhaber).order_by(Inhaber.name).all():
        deals_inh = [d for d in deals if d.inhaber_id == inh.id]
        kz = derived.kennzahlen([p for d in deals_inh for p in d.praemien])
        freibetrag_genutzt = sum((d.freibetrag for d in deals_inh if d.freibetrag is not None), Decimal("0"))
        pro_inhaber.append(
            {
                "inhaber": inh,
                "kennzahlen": kz,
                "anzahl_deals": len(deals_inh),
                "freibetrag_genutzt": freibetrag_genutzt,
            }
        )

    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "kennzahlen": gesamt_kennzahlen,
            "nach_status": nach_status,
            "status_labels": derived.STATUS_LABELS,
            "status_order": derived.STATUS_ORDER,
            "pro_inhaber": pro_inhaber,
            "anzahl_deals": len(deals),
        },
    )
