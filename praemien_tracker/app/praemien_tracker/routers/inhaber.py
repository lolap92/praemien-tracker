from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from sqlalchemy.orm import Session

from .. import iban, unterschrift
from ..database import get_db
from ..helpers import parse_date
from ..ingress import redirect
from ..models import Inhaber
from ..templating import templates

router = APIRouter()

# Absenderangaben für den Kündigungs-Assistenten - Formularname je Inhaber
# ist "<feld>_<id>".
TEXT_FELDER = ("voller_name", "strasse", "plz", "ort", "email")


def _seite(request: Request, db: Session, fehler: list[str] | None = None, status_code: int = 200):
    inhaber_liste = db.query(Inhaber).order_by(Inhaber.name).all()
    return templates.TemplateResponse(
        "inhaber.html",
        {
            "request": request,
            "inhaber_liste": inhaber_liste,
            "iban_formatiert": iban.formatiert,
            "iban_gueltig": iban.gueltig,
            "unterschrift_lesen": unterschrift.lesen,
            "fehler": fehler or [],
        },
        status_code=status_code,
    )


@router.get("/inhaber")
def inhaber_view(request: Request, db: Session = Depends(get_db)):
    """Verwaltung der Haushaltsmitglieder: einzige Stelle, an der sich
    `ist_minderjaehrig` setzen lässt - entscheidet in finder/lauf.py und
    routers/vorschlaege.py, ob ein Angebot für diese Person überhaupt als
    Vorschlag infrage kommt bzw. im "Übernehmen"-Dialog vorausgewählt ist.
    Neue Inhaber entstehen weiterhin automatisch beim Anlegen eines Deals
    (helpers.get_or_create_inhaber, immer erwachsen per Default) - hier lässt
    sich das nachträglich korrigieren, ohne direkten Datenbankzugriff."""
    return _seite(request, db)


@router.post("/inhaber")
async def inhaber_speichern(request: Request, db: Session = Depends(get_db)):
    """Ein Speichern-Button für alle Zeilen zugleich (wie beim Deal bearbeiten,
    siehe 2.26.0) statt eines je Inhaber. Liest bewusst manuell über
    request.form() statt typisierter Form(...)-Parameter, weil die Anzahl der
    Inhaber variabel ist - ein Bool-Feld (Checkbox) wird an seinem Namen
    erkannt und ist True, wenn der Schlüssel überhaupt vorhanden ist.

    Die Absenderangaben werden nur angefasst, wenn ihr Feld mitgeschickt
    wurde - sonst löschte ein Formular ohne diese Felder (oder ein alter
    Browser-Tab) still die gepflegte Anschrift.

    Die Unterschrift ist ein Datei-Feld: ohne gewählte Datei bleibt die
    gespeicherte unverändert, "Unterschrift entfernen" löscht sie. Ein
    unbrauchbares Bild verwirft nur dieses Bild - die übrigen Angaben werden
    gespeichert und die Seite zeigt den Grund an."""
    form = await request.form()
    fehler: list[str] = []
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
        if form.get(f"unterschrift_loeschen_{inhaber.id}") is not None:
            inhaber.unterschrift = None
        datei = form.get(f"unterschrift_{inhaber.id}")
        if isinstance(datei, UploadFile) and datei.filename:
            try:
                inhaber.unterschrift = unterschrift.normalisieren(await datei.read())
            except unterschrift.UngueltigesBild as exc:
                fehler.append(f"Unterschrift für {inhaber.name}: {exc}")
    db.commit()
    if fehler:
        return _seite(request, db, fehler=fehler, status_code=400)
    return redirect(request, "inhaber")


@router.post("/inhaber/{inhaber_id}/unterschrift")
def unterschrift_setzen(inhaber_id: int, bild_base64: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Setzt nur die Unterschrift eines Inhabers, das Bild als Base64 in JSON
    ({"bild_base64": "..."}). Für Werkzeuge, die keine Datei hochladen
    können (z. B. der App-Proxy des Home-Assistant-MCP-Servers) - und
    anders als POST /inhaber, das immer alle Inhaber samt "minderjährig"
    aus dem Formular übernimmt, lässt es alles andere unberührt. Ein leerer
    String entfernt die Unterschrift."""
    inhaber = db.get(Inhaber, inhaber_id)
    if inhaber is None:
        raise HTTPException(status_code=404, detail="Inhaber nicht gefunden.")
    if not bild_base64.strip():
        inhaber.unterschrift = None
    else:
        try:
            roh = base64.b64decode(bild_base64.split(",", 1)[-1], validate=True)
            inhaber.unterschrift = unterschrift.normalisieren(roh)
        except binascii.Error as exc:
            raise HTTPException(status_code=400, detail="Kein gültiges Base64.") from exc
        except unterschrift.UngueltigesBild as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    bild = unterschrift.lesen(inhaber.unterschrift)
    return {
        "inhaber": inhaber.name,
        "unterschrift_hinterlegt": bild is not None,
        "breite": bild.breite if bild else None,
        "hoehe": bild.hoehe if bild else None,
    }
