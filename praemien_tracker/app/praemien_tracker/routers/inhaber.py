from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import iban
from ..database import get_db
from ..helpers import parse_date
from ..ingress import redirect
from ..models import Inhaber
from ..templating import templates

router = APIRouter()

# Absenderangaben für den Kündigungs-Assistenten - Formularname je Inhaber
# ist "<feld>_<id>".
TEXT_FELDER = ("voller_name", "strasse", "plz", "ort", "email")


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
            "iban_formatiert": iban.formatiert,
            "iban_gueltig": iban.gueltig,
        },
    )


@router.post("/inhaber")
async def inhaber_speichern(request: Request, db: Session = Depends(get_db)):
    """Ein Speichern-Button für alle Zeilen zugleich (wie beim Deal bearbeiten,
    siehe 2.26.0) statt eines je Inhaber. Liest bewusst manuell über
    request.form() statt typisierter Form(...)-Parameter, weil die Anzahl der
    Inhaber variabel ist - ein Bool-Feld (Checkbox) wird an seinem Namen
    erkannt und ist True, wenn der Schlüssel überhaupt vorhanden ist.

    Die Absenderangaben werden nur angefasst, wenn ihr Feld mitgeschickt
    wurde - sonst löschte ein Formular ohne diese Felder (oder ein alter
    Browser-Tab) still die gepflegte Anschrift."""
    form = await request.form()
    for inhaber in db.query(Inhaber).all():
        inhaber.ist_minderjaehrig = form.get(f"minderjaehrig_{inhaber.id}") is not None
        for feld in TEXT_FELDER:
            wert = form.get(f"{feld}_{inhaber.id}")
            if wert is not None:
                setattr(inhaber, feld, str(wert).strip() or None)
        if (wert := form.get(f"geburtsdatum_{inhaber.id}")) is not None:
            inhaber.geburtsdatum = parse_date(str(wert).strip())
        if (wert := form.get(f"iban_{inhaber.id}")) is not None:
            inhaber.iban = iban.normalisieren(str(wert))
    db.commit()
    return redirect(request, "inhaber")
