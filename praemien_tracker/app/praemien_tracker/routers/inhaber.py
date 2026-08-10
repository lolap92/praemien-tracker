from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingress import redirect
from ..models import Inhaber
from ..templating import templates

router = APIRouter()


@router.get("/inhaber")
def inhaber_view(request: Request, db: Session = Depends(get_db)):
    """Verwaltung der Haushaltsmitglieder: einzige Stelle, an der sich
    `ist_minderjaehrig` setzen lässt - entscheidet in finder/lauf.py und
    routers/vorschlaege.py, ob ein Angebot für diese Person überhaupt als
    Vorschlag infrage kommt bzw. im "Übernehmen"-Dialog vorausgewählt ist.
    Neue Inhaber entstehen weiterhin automatisch beim Anlegen eines Deals
    (helpers.get_or_create_inhaber, immer erwachsen per Default) - hier lässt
    sich das nachträglich korrigieren, ohne direkten Datenbankzugriff."""
    inhaber_liste = db.query(Inhaber).order_by(Inhaber.name).all()
    return templates.TemplateResponse(
        "inhaber.html",
        {
            "request": request,
            "inhaber_liste": inhaber_liste,
        },
    )


@router.post("/inhaber")
async def inhaber_speichern(request: Request, db: Session = Depends(get_db)):
    """Ein Speichern-Button für alle Zeilen zugleich (wie beim Deal bearbeiten,
    siehe 2.26.0) statt eines je Inhaber. Liest bewusst manuell über
    request.form() statt typisierter Form(...)-Parameter, weil die Anzahl der
    Inhaber variabel ist - ein Bool-Feld (Checkbox) wird an seinem Namen
    erkannt und ist True, wenn der Schlüssel überhaupt vorhanden ist."""
    form = await request.form()
    for inhaber in db.query(Inhaber).all():
        inhaber.ist_minderjaehrig = form.get(f"minderjaehrig_{inhaber.id}") is not None
    db.commit()
    return redirect(request, "inhaber")
