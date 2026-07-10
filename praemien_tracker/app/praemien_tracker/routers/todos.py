from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..helpers import parse_date
from ..ingress import redirect
from ..models import Aufgabe, Deal
from ..templating import templates

router = APIRouter()

KATEGORIE_SLUGS = {
    "Manuelle Aufgaben": "manuell",
    "Bedingungen": "bedingungen",
    "Auf Prämie warten": "praemie",
    "Kündigen": "kuendigen",
    "Bestätigung warten": "bestaetigung",
    "Zugangsdaten": "zugangsdaten",
}


@router.get("/todos")
def todos_view(request: Request, db: Session = Depends(get_db)):
    deals = (
        db.query(Deal)
        .options(
            joinedload(Deal.bank),
            joinedload(Deal.inhaber),
            joinedload(Deal.bedingungen),
            joinedload(Deal.praemien),
        )
        .all()
    )
    aufgaben = (
        db.query(Aufgabe)
        .options(joinedload(Aufgabe.deal).joinedload(Deal.bank), joinedload(Aufgabe.deal).joinedload(Deal.inhaber))
        .all()
    )

    alle = derived.alle_todos(deals, aufgaben)
    gruppen: dict[str, list[derived.Todo]] = {}
    for t in alle:
        gruppen.setdefault(t.kategorie, []).append(t)

    offene_aufgaben = [a for a in aufgaben if not a.erledigt]
    erledigte_aufgaben = [a for a in aufgaben if a.erledigt]

    return templates.TemplateResponse(
        "todos.html",
        {
            "request": request,
            "gruppen": gruppen,
            "kategorie_slugs": KATEGORIE_SLUGS,
            "kategorie_reihenfolge": [
                "Manuelle Aufgaben",
                "Bedingungen",
                "Auf Prämie warten",
                "Kündigen",
                "Bestätigung warten",
                "Zugangsdaten",
            ],
            "deals": sorted(deals, key=lambda d: (d.bank.name, d.inhaber.name)),
            "offene_aufgaben": offene_aufgaben,
            "erledigte_aufgaben": erledigte_aufgaben,
        },
    )


@router.post("/todos/aufgaben")
def create_aufgabe(
    request: Request,
    beschreibung: str = Form(...),
    deal_id: str = Form(""),
    faellig_bis: str = Form(""),
    db: Session = Depends(get_db),
):
    aufgabe = Aufgabe(
        beschreibung=beschreibung.strip(),
        deal_id=int(deal_id) if deal_id else None,
        faellig_bis=parse_date(faellig_bis),
    )
    db.add(aufgabe)
    db.commit()
    return redirect(request, "todos")


@router.post("/todos/aufgaben/{aufgabe_id}/toggle")
def toggle_aufgabe(request: Request, aufgabe_id: int, db: Session = Depends(get_db)):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        aufgabe.erledigt = not aufgabe.erledigt
        db.commit()
    return redirect(request, "todos")


@router.post("/todos/aufgaben/{aufgabe_id}/delete")
def delete_aufgabe(request: Request, aufgabe_id: int, db: Session = Depends(get_db)):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        db.delete(aufgabe)
        db.commit()
    return redirect(request, "todos")
