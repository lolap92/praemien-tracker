from __future__ import annotations

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..export import build_workbook
from ..helpers import build_deal_from_import, get_or_create_bank, get_or_create_inhaber, parse_date, parse_decimal
from ..ingress import redirect
from ..models import Aufgabe, Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie
from ..schemas import DealImport
from ..templating import templates

router = APIRouter()


def _deal_query(db: Session):
    return db.query(Deal).options(
        joinedload(Deal.bank),
        joinedload(Deal.inhaber),
        joinedload(Deal.praemien),
        joinedload(Deal.bedingungen),
        joinedload(Deal.aufgaben),
        joinedload(Deal.urls),
    )


@router.get("/deals")
def deals_list(
    request: Request,
    inhaber_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    deals = _deal_query(db).join(Bank).order_by(Bank.name, Deal.kontoart).all()

    if inhaber_id:
        deals = [d for d in deals if d.inhaber_id == inhaber_id]
    if status:
        deals = [d for d in deals if derived.status(d) == status]
    if q:
        q_lower = q.strip().lower()
        deals = [d for d in deals if q_lower in d.bank.name.lower()]

    zeilen = [
        {
            "deal": d,
            "status": derived.status(d),
            "status_index": derived.STATUS_INDEX[derived.status(d)],
            "kennzahlen": derived.kennzahlen(d.praemien),
        }
        for d in deals
    ]

    return templates.TemplateResponse(
        "deals_list.html",
        {
            "request": request,
            "zeilen": zeilen,
            "inhaber_liste": db.query(Inhaber).order_by(Inhaber.name).all(),
            "status_labels": derived.STATUS_LABELS,
            "status_order": derived.STATUS_ORDER,
            "filter_inhaber_id": inhaber_id,
            "filter_status": status,
            "filter_q": q or "",
        },
    )


@router.get("/deals/export.xlsx")
def deals_export(db: Session = Depends(get_db)):
    deals = _deal_query(db).join(Bank).order_by(Bank.name, Deal.kontoart).all()
    buffer = build_workbook(deals)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=praemien-tracker-export.xlsx"},
    )


@router.get("/deals/new")
def deal_new_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "deal_form.html",
        {
            "request": request,
            "deal": None,
            "banken": db.query(Bank).order_by(Bank.name).all(),
            "inhaber_liste": db.query(Inhaber).order_by(Inhaber.name).all(),
            "status": None,
            "offene_felder": [],
            "json_fehler": None,
            "json_text": "",
        },
    )


@router.post("/deals/new")
def deal_new_create(
    request: Request,
    bank: str = Form(...),
    inhaber: str = Form(...),
    kontoart: str = Form(...),
    kontonummer: str = Form(""),
    kuendbar_ab: str = Form(""),
    freibetrag: str = Form(""),
    kommentar: str = Form(""),
    zugangsdaten_gespeichert: str = Form(""),
    praemien_auf_sparkonto: str = Form(""),
    db: Session = Depends(get_db),
):
    deal = Deal(
        bank=get_or_create_bank(db, bank),
        inhaber=get_or_create_inhaber(db, inhaber),
        kontoart=kontoart.strip(),
        kontonummer=kontonummer.strip() or None,
        kuendbar_ab=parse_date(kuendbar_ab),
        freibetrag=parse_decimal(freibetrag),
        kommentar=kommentar.strip() or None,
        zugangsdaten_gespeichert=zugangsdaten_gespeichert == "on",
        praemien_auf_sparkonto=(praemien_auf_sparkonto == "on") if praemien_auf_sparkonto else None,
    )
    db.add(deal)
    db.commit()
    return redirect(request, f"deals/{deal.id}/edit")


@router.post("/deals/json-import")
def deal_json_import(request: Request, json_text: str = Form(...), db: Session = Depends(get_db)):
    banken = db.query(Bank).order_by(Bank.name).all()
    inhaber_liste = db.query(Inhaber).order_by(Inhaber.name).all()

    try:
        rohdaten = json.loads(json_text)
        daten = DealImport.model_validate(rohdaten)
    except (json.JSONDecodeError, ValidationError) as exc:
        return templates.TemplateResponse(
            "deal_form.html",
            {
                "request": request,
                "deal": None,
                "banken": banken,
                "inhaber_liste": inhaber_liste,
                "status": None,
                "offene_felder": [],
                "json_fehler": str(exc),
                "json_text": json_text,
            },
            status_code=400,
        )

    deal = build_deal_from_import(db, daten)
    db.commit()
    return redirect(request, f"deals/{deal.id}/edit")


@router.get("/deals/{deal_id}/edit")
def deal_edit_form(request: Request, deal_id: int, db: Session = Depends(get_db)):
    deal = _deal_query(db).filter(Deal.id == deal_id).one()
    return templates.TemplateResponse(
        "deal_form.html",
        {
            "request": request,
            "deal": deal,
            "banken": db.query(Bank).order_by(Bank.name).all(),
            "inhaber_liste": db.query(Inhaber).order_by(Inhaber.name).all(),
            "status": derived.status(deal),
            "status_labels": derived.STATUS_LABELS,
            "offene_felder": {f.feld for f in derived.offene_felder(deal)},
            "json_fehler": None,
            "json_text": "",
        },
    )


@router.post("/deals/{deal_id}")
def deal_update(
    request: Request,
    deal_id: int,
    bank: str = Form(...),
    inhaber: str = Form(...),
    kontoart: str = Form(...),
    kontonummer: str = Form(""),
    kuendbar_ab: str = Form(""),
    gekuendigt: str = Form(""),
    gekuendigt_im_monat: str = Form(""),
    kuendigung_bestaetigt: str = Form(""),
    kuendigung_hinweis: str = Form(""),
    kuendigung_hinweis_url: str = Form(""),
    freibetrag: str = Form(""),
    praemien_auf_sparkonto: str = Form(""),
    kommentar: str = Form(""),
    zugangsdaten_gespeichert: str = Form(""),
    db: Session = Depends(get_db),
):
    deal = db.get(Deal, deal_id)
    deal.bank = get_or_create_bank(db, bank)
    deal.inhaber = get_or_create_inhaber(db, inhaber)
    deal.kontoart = kontoart.strip()
    deal.kontonummer = kontonummer.strip() or None
    deal.kuendbar_ab = parse_date(kuendbar_ab)
    deal.gekuendigt = gekuendigt == "on"
    deal.gekuendigt_im_monat = gekuendigt_im_monat.strip() or None
    deal.kuendigung_bestaetigt = kuendigung_bestaetigt == "on"
    deal.kuendigung_hinweis = kuendigung_hinweis.strip() or None
    deal.kuendigung_hinweis_url = kuendigung_hinweis_url.strip() or None
    deal.freibetrag = parse_decimal(freibetrag)
    deal.praemien_auf_sparkonto = (praemien_auf_sparkonto == "on") if praemien_auf_sparkonto else None
    deal.kommentar = kommentar.strip() or None
    deal.zugangsdaten_gespeichert = zugangsdaten_gespeichert == "on"
    db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/kuendigung-hinweis")
async def deal_kuendigung_hinweis_update(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Setzt nur dieses eine Feld. Nimmt sowohl normale Formulardaten als auch
    einen JSON-Body entgegen (z. B. für programmatisches Befüllen)."""
    if request.headers.get("content-type", "").startswith("application/json"):
        daten = await request.json()
    else:
        daten = await request.form()
    deal = db.get(Deal, deal_id)
    if deal:
        deal.kuendigung_hinweis = (daten.get("kuendigung_hinweis") or "").strip() or None
        deal.kuendigung_hinweis_url = (daten.get("kuendigung_hinweis_url") or "").strip() or None
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/stornieren")
def deal_stornieren(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Storniert einen Deal: alle Bedingungen gelten als erfüllt, noch nicht
    erhaltene Prämien werden auf 0 gesetzt und als erhalten markiert, der
    Deal gilt als gekündigt und bestätigt - der Status springt damit
    unabhängig vom bisherigen Stand auf 'Abgeschlossen'."""
    deal = db.get(Deal, deal_id)
    if deal:
        for b in deal.bedingungen:
            b.erfuellt = True
        for p in deal.praemien:
            if not p.erhalten:
                p.betrag = Decimal("0")
                p.erhalten = True
        deal.gekuendigt = True
        deal.kuendigung_bestaetigt = True
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/delete")
def deal_delete(request: Request, deal_id: int, db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if deal:
        db.delete(deal)
        db.commit()
    return redirect(request, "deals")


# --- Prämien ---


@router.post("/deals/{deal_id}/praemien")
def praemie_add(
    request: Request,
    deal_id: int,
    quelle: str = Form(...),
    betrag: str = Form(...),
    erhalten: str = Form(""),
    auszahlung_erwartet: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(
        Praemie(
            deal_id=deal_id,
            quelle=quelle,
            betrag=parse_decimal(betrag) or 0,
            erhalten=erhalten == "on",
            auszahlung_erwartet=auszahlung_erwartet.strip() or None,
        )
    )
    db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/praemien/{praemie_id}")
def praemie_update(
    request: Request,
    deal_id: int,
    praemie_id: int,
    quelle: str = Form(...),
    betrag: str = Form(...),
    erhalten: str = Form(""),
    auszahlung_erwartet: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.get(Praemie, praemie_id)
    if p:
        p.quelle = quelle
        p.betrag = parse_decimal(betrag) or 0
        p.erhalten = erhalten == "on"
        p.auszahlung_erwartet = auszahlung_erwartet.strip() or None
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/praemien/{praemie_id}/delete")
def praemie_delete(request: Request, deal_id: int, praemie_id: int, db: Session = Depends(get_db)):
    p = db.get(Praemie, praemie_id)
    if p:
        db.delete(p)
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


# --- Bedingungen ---


@router.post("/deals/{deal_id}/bedingungen")
def bedingung_add(
    request: Request,
    deal_id: int,
    beschreibung: str = Form(...),
    faellig_bis: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Bedingung(deal_id=deal_id, beschreibung=beschreibung.strip(), faellig_bis=parse_date(faellig_bis)))
    db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/bedingungen/{bedingung_id}")
def bedingung_update(
    request: Request,
    deal_id: int,
    bedingung_id: int,
    beschreibung: str = Form(...),
    erfuellt: str = Form(""),
    faellig_bis: str = Form(""),
    db: Session = Depends(get_db),
):
    b = db.get(Bedingung, bedingung_id)
    if b:
        b.beschreibung = beschreibung.strip()
        b.erfuellt = erfuellt == "on"
        b.faellig_bis = parse_date(faellig_bis)
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/bedingungen/{bedingung_id}/delete")
def bedingung_delete(request: Request, deal_id: int, bedingung_id: int, db: Session = Depends(get_db)):
    b = db.get(Bedingung, bedingung_id)
    if b:
        db.delete(b)
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


# --- Aufgaben (deal-gebunden) ---


@router.post("/deals/{deal_id}/aufgaben")
def deal_aufgabe_add(
    request: Request,
    deal_id: int,
    beschreibung: str = Form(...),
    faellig_bis: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Aufgabe(deal_id=deal_id, beschreibung=beschreibung.strip(), faellig_bis=parse_date(faellig_bis)))
    db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/aufgaben/{aufgabe_id}")
def deal_aufgabe_update(
    request: Request,
    deal_id: int,
    aufgabe_id: int,
    beschreibung: str = Form(...),
    erledigt: str = Form(""),
    faellig_bis: str = Form(""),
    db: Session = Depends(get_db),
):
    a = db.get(Aufgabe, aufgabe_id)
    if a:
        a.beschreibung = beschreibung.strip()
        a.erledigt = erledigt == "on"
        a.faellig_bis = parse_date(faellig_bis)
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/aufgaben/{aufgabe_id}/delete")
def deal_aufgabe_delete(request: Request, deal_id: int, aufgabe_id: int, db: Session = Depends(get_db)):
    a = db.get(Aufgabe, aufgabe_id)
    if a:
        db.delete(a)
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


# --- Links ---


@router.post("/deals/{deal_id}/urls")
def url_add(request: Request, deal_id: int, url: str = Form(...), bezeichnung: str = Form(""), db: Session = Depends(get_db)):
    db.add(DealUrl(deal_id=deal_id, url=url.strip(), bezeichnung=bezeichnung.strip() or None))
    db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/urls/{url_id}/delete")
def url_delete(request: Request, deal_id: int, url_id: int, db: Session = Depends(get_db)):
    u = db.get(DealUrl, url_id)
    if u:
        db.delete(u)
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


# --- Vollständigkeit: Felder abhaken / wieder aufnehmen ---


@router.post("/deals/{deal_id}/skip-field")
def skip_field(request: Request, deal_id: int, feld: str = Form(...), db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if deal:
        felder = set(derived.uebersprungene_felder_liste(deal))
        felder.add(feld)
        derived.uebersprungene_felder_speichern(deal, sorted(felder))
        db.commit()
    return redirect(request, "completeness")


@router.post("/deals/{deal_id}/unskip-field")
def unskip_field(request: Request, deal_id: int, feld: str = Form(...), db: Session = Depends(get_db)):
    deal = db.get(Deal, deal_id)
    if deal:
        felder = set(derived.uebersprungene_felder_liste(deal))
        felder.discard(feld)
        derived.uebersprungene_felder_speichern(deal, sorted(felder))
        db.commit()
    return redirect(request, "completeness")
