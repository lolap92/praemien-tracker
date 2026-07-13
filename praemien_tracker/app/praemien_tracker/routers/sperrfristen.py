from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..models import Deal
from ..templating import templates

router = APIRouter()


@router.get("/sperrfristen")
def sperrfristen_view(request: Request, db: Session = Depends(get_db)):
    deals = (
        db.query(Deal)
        .options(joinedload(Deal.bank), joinedload(Deal.inhaber))
        .filter(Deal.gekuendigt.is_(True))
        .all()
    )

    heute = datetime.date.today()
    zeilen = []
    ohne_datum = []
    for d in deals:
        kuendigungsdatum = derived.parse_gekuendigt_monat(d.gekuendigt_im_monat)
        if kuendigungsdatum is None:
            ohne_datum.append(d)
            continue
        monate = derived.monate_seit_kuendigung(kuendigungsdatum, heute)
        zeilen.append(
            {
                "deal": d,
                "kuendigungsdatum": kuendigungsdatum,
                "monate": monate,
                "stufe": derived.sperrfrist_stufe(monate),
            }
        )

    zeilen.sort(key=lambda z: z["kuendigungsdatum"])
    ohne_datum.sort(key=lambda d: (d.bank.name, d.kontoart, d.inhaber.name))

    return templates.TemplateResponse(
        "sperrfristen.html",
        {
            "request": request,
            "zeilen": zeilen,
            "ohne_datum": ohne_datum,
        },
    )
