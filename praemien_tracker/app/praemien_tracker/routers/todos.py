from __future__ import annotations

import datetime
import re

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..helpers import parse_date
from ..ingress import redirect
from ..models import Aufgabe, Bedingung, Deal, Praemie
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

KATEGORIE_REIHENFOLGE = [
    "Manuelle Aufgaben",
    "Bedingungen",
    "Auf Prämie warten",
    "Kündigen",
    "Bestätigung warten",
    "Zugangsdaten",
]

# Format "<kategorie-slug>-<deal-id>", z.B. "bedingungen-6" - wird für die
# id des <dialog>-Elements verwendet und daher vor der Wiederverwendung im
# <script>-Block validiert.
DIALOG_PARAM = re.compile(r"^[a-z]+-\d+$")


def _todos_redirect(request: Request, tab: str = "", dialog: str = ""):
    ziel = "todos"
    teile = []
    if tab:
        teile.append(f"tab={tab}")
    if dialog:
        teile.append(f"dialog={dialog}")
    if teile:
        ziel += "?" + "&".join(teile)
    return redirect(request, ziel)


@router.get("/todos")
def todos_view(request: Request, tab: str = "", dialog: str = "", db: Session = Depends(get_db)):
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

    aktiver_tab = tab if tab in KATEGORIE_SLUGS.values() and any(
        KATEGORIE_SLUGS[k] == tab and gruppen.get(k) for k in KATEGORIE_REIHENFOLGE
    ) else ""
    offener_dialog = dialog if DIALOG_PARAM.match(dialog or "") else ""

    offene_aufgaben = [a for a in aufgaben if not a.erledigt]
    erledigte_aufgaben = [a for a in aufgaben if a.erledigt]

    return templates.TemplateResponse(
        "todos.html",
        {
            "request": request,
            "gruppen": gruppen,
            "kategorie_slugs": KATEGORIE_SLUGS,
            "kategorie_reihenfolge": KATEGORIE_REIHENFOLGE,
            "deals": sorted(deals, key=lambda d: (d.bank.name, d.inhaber.name)),
            "offene_aufgaben": offene_aufgaben,
            "erledigte_aufgaben": erledigte_aufgaben,
            "aktiver_tab": aktiver_tab,
            "offener_dialog": offener_dialog,
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
    return _todos_redirect(request, tab=KATEGORIE_SLUGS["Manuelle Aufgaben"])


@router.post("/todos/aufgaben/{aufgabe_id}/toggle")
def toggle_aufgabe(request: Request, aufgabe_id: int, tab: str = Form(""), db: Session = Depends(get_db)):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        aufgabe.erledigt = not aufgabe.erledigt
        db.commit()
    return _todos_redirect(request, tab)


@router.post("/todos/aufgaben/{aufgabe_id}/delete")
def delete_aufgabe(request: Request, aufgabe_id: int, db: Session = Depends(get_db)):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        db.delete(aufgabe)
        db.commit()
    return redirect(request, "todos")


@router.post("/todos/bedingungen/{bedingung_id}/toggle")
def toggle_bedingung(
    request: Request, bedingung_id: int, tab: str = Form(""), dialog: str = Form(""), db: Session = Depends(get_db)
):
    b = db.get(Bedingung, bedingung_id)
    if b:
        b.erfuellt = not b.erfuellt
        db.commit()
    return _todos_redirect(request, tab, dialog)


@router.post("/todos/praemien/{praemie_id}/toggle")
def toggle_praemie(
    request: Request, praemie_id: int, tab: str = Form(""), dialog: str = Form(""), db: Session = Depends(get_db)
):
    p = db.get(Praemie, praemie_id)
    if p:
        p.erhalten = not p.erhalten
        db.commit()
    return _todos_redirect(request, tab, dialog)


@router.post("/todos/deals/{deal_id}/kuendigen-toggle")
def toggle_kuendigen(request: Request, deal_id: int, tab: str = Form(""), db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if deal:
        deal.gekuendigt = not deal.gekuendigt
        if deal.gekuendigt:
            deal.gekuendigt_im_monat = datetime.date.today().strftime("%m.%y")
        db.commit()
    return _todos_redirect(request, tab)


@router.post("/todos/deals/{deal_id}/bestaetigen-toggle")
def toggle_bestaetigen(request: Request, deal_id: int, tab: str = Form(""), db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if deal:
        deal.kuendigung_bestaetigt = not deal.kuendigung_bestaetigt
        db.commit()
    return _todos_redirect(request, tab)


@router.post("/todos/deals/{deal_id}/zugangsdaten-toggle")
def toggle_zugangsdaten(request: Request, deal_id: int, tab: str = Form(""), db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if deal:
        deal.zugangsdaten_gespeichert = not deal.zugangsdaten_gespeichert
        db.commit()
    return _todos_redirect(request, tab)
