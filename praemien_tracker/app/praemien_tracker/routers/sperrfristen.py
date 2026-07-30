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
        # Stornierte Deals sind nie zustande gekommen - sie gehören nicht in eine
        # Auswertung darüber, wann eine Bank wieder Neukunden-Ziel ist.
        .filter(Deal.gekuendigt.is_(True), Deal.storniert.is_(False))
        .all()
    )

    heute = datetime.date.today()
    zeilen = []
    for d in deals:
        # Ohne auswertbaren Monat erscheint der Deal unter "Zu prüfen" statt
        # hier in einer zweiten Liste - derselbe Hinweis lebte sonst an zwei
        # Stellen.
        kuendigungsdatum = derived.parse_monat(d.gekuendigt_im_monat)
        if kuendigungsdatum is None:
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

    return templates.TemplateResponse(
        "sperrfristen.html",
        {
            "request": request,
            "zeilen": zeilen,
        },
    )
