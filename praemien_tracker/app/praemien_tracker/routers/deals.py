from __future__ import annotations

import datetime
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..export import build_workbook
from ..helpers import (
    build_deal_from_import,
    get_or_create_bank,
    get_or_create_inhaber,
    kuendigung_vorschlag,
    kwk_vorschlag,
    monat_aus_formular,
    parse_date,
    parse_decimal,
)
from ..ingress import redirect
from ..models import Aufgabe, Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie
from ..schemas import DealImport
from ..templating import templates

router = APIRouter()


def _hole_deal(db: Session, deal_id: int) -> Deal:
    """Deal oder 404 - statt eines Stacktrace, wenn eine ID nicht (mehr)
    existiert, etwa aus einem alten Lesezeichen oder einem zweiten Tab."""
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} existiert nicht.")
    return deal


def _quelle_oder_400(wert: str) -> str:
    """Nur die zwei fachlich existierenden Quellen zulassen. Ohne diese
    Prüfung landet ein abweichender Wert in der Datenbank, das <select> im
    Formular kennt ihn nicht - und beim nächsten Speichern wird daraus
    stillschweigend "spartanien"."""
    normalisiert = derived.normalisiere_quelle(wert)
    if normalisiert is None:
        raise HTTPException(status_code=400, detail=f"Unbekannte Prämien-Quelle: {wert!r}")
    return normalisiert


def _freibetrag_jahr(eingabe: str, betrag) -> int | None:
    try:
        jahr = int(eingabe.strip())
    except (ValueError, AttributeError):
        jahr = None
    if betrag is None:
        return jahr
    return jahr or datetime.date.today().year


def _als_int(werte: list[str]) -> list[int]:
    """Nicht-numerische Filterwerte werden übergangen, statt die Seite mit
    einem Fehler abzubrechen - erreichbar über alte Links oder von Hand
    getippte URLs."""
    ergebnis = []
    for wert in werte:
        try:
            ergebnis.append(int(wert.strip()))
        except (ValueError, AttributeError):
            continue
    return ergebnis


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
    inhaber_id: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    q: str | None = None,
    db: Session = Depends(get_db),
):
    inhaber_ids = _als_int(inhaber_id)
    status_werte = [s for s in status if s.strip() in derived.STATUS_INDEX]

    deals = _deal_query(db).join(Bank).order_by(Bank.name, Deal.kontoart).all()

    if inhaber_ids:
        deals = [d for d in deals if d.inhaber_id in inhaber_ids]
    if status_werte:
        deals = [d for d in deals if derived.status(d) in status_werte]
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
            "filter_inhaber_id": inhaber_ids,
            "filter_status": status_werte,
            "filter_q": q or "",
            "filter_aktiv": bool(inhaber_ids or status_werte or q),
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


def _neu_formular(
    request: Request,
    db: Session,
    *,
    form_fehler: str | None = None,
    json_fehler: list[str] | None = None,
    json_text: str = "",
    eingaben: dict | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "deal_form.html",
        {
            "request": request,
            "deal": None,
            "banken": db.query(Bank).order_by(Bank.name).all(),
            "inhaber_liste": db.query(Inhaber).order_by(Inhaber.name).all(),
            "status": None,
            "offene_felder": [],
            "form_fehler": form_fehler,
            "json_fehler": json_fehler,
            "json_text": json_text,
            "eingaben": eingaben or {},
        },
        status_code=status_code,
    )


@router.get("/deals/new")
def deal_new_form(request: Request, db: Session = Depends(get_db)):
    return _neu_formular(request, db)


@router.post("/deals/new")
def deal_new_create(
    request: Request,
    bank: str = Form(...),
    inhaber: str = Form(...),
    kontoart: str = Form(...),
    kontonummer: str = Form(""),
    zugangsdaten_gespeichert: str = Form(""),
    db: Session = Depends(get_db),
):
    eingaben = {
        "bank": bank.strip(),
        "inhaber": inhaber.strip(),
        "kontoart": kontoart.strip(),
        "kontonummer": kontonummer.strip(),
    }
    # required im HTML lässt reine Leerzeichen durch - ohne diese Prüfung
    # entstünde eine Bank mit leerem Namen, die wegen unique anschließend
    # jede weitere Leereingabe einsammelt.
    fehlend = [
        label
        for feld, label in (("bank", "Bank"), ("inhaber", "Inhaber"), ("kontoart", "Kontoart"))
        if not eingaben[feld]
    ]
    if fehlend:
        return _neu_formular(
            request,
            db,
            form_fehler="Bitte ausfüllen: " + ", ".join(fehlend) + ".",
            eingaben=eingaben,
            status_code=400,
        )

    deal = Deal(
        bank=get_or_create_bank(db, eingaben["bank"]),
        inhaber=get_or_create_inhaber(db, eingaben["inhaber"]),
        kontoart=eingaben["kontoart"],
        kontonummer=eingaben["kontonummer"] or None,
        zugangsdaten_gespeichert=zugangsdaten_gespeichert == "on",
    )
    kuendigung_vorschlag(db, deal)
    kwk_vorschlag(db, deal)
    db.add(deal)
    db.commit()
    return redirect(request, f"deals/{deal.id}/edit")


def _lesbare_fehler(exc: ValidationError, mit_index: bool) -> list[str]:
    """Aus dem Pydantic-Fehlerobjekt kurze deutsche Zeilen bauen - der rohe
    str(exc) ist ein technischer Dump mit englischen Feldnamen und einem Link
    auf errors.pydantic.dev."""
    texte = {
        "missing": "fehlt",
        "string_type": "muss Text sein",
        "int_parsing": "muss eine Zahl sein",
        "bool_parsing": "muss true oder false sein",
        "decimal_parsing": "muss eine Zahl sein",
        "date_from_datetime_parsing": "ist kein gültiges Datum (erwartet JJJJ-MM-TT)",
        "date_parsing": "ist kein gültiges Datum (erwartet JJJJ-MM-TT)",
    }
    zeilen = []
    for fehler in exc.errors():
        pfad = [str(teil) for teil in fehler["loc"]]
        if mit_index and pfad and pfad[0].isdigit():
            vorsatz = f"Deal {int(pfad[0]) + 1}: "
            pfad = pfad[1:]
        else:
            vorsatz = ""
        feld = " → ".join(pfad) or "Eingabe"
        zeilen.append(f"{vorsatz}{feld} {texte.get(fehler['type'], fehler['msg'])}")
    return zeilen


@router.post("/deals/json-import")
def deal_json_import(request: Request, json_text: str = Form(...), db: Session = Depends(get_db)):
    try:
        rohdaten = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return _neu_formular(
            request,
            db,
            json_fehler=[f"Kein gültiges JSON (Zeile {exc.lineno}, Spalte {exc.colno}): {exc.msg}"],
            json_text=json_text,
            status_code=400,
        )

    # Eine Liste ist ebenso zulässig wie ein einzelnes Objekt, damit sich
    # mehrere Deals in einem Durchgang anlegen lassen.
    ist_liste = isinstance(rohdaten, list)
    try:
        if ist_liste:
            # Über den TypeAdapter validiert, damit der Fehlerpfad die Position
            # in der Liste enthält und die Meldung sagen kann, welcher Deal.
            deals = TypeAdapter(list[DealImport]).validate_python(rohdaten)
        else:
            deals = [DealImport.model_validate(rohdaten)]
    except ValidationError as exc:
        return _neu_formular(
            request, db, json_fehler=_lesbare_fehler(exc, ist_liste), json_text=json_text, status_code=400
        )

    if not deals:
        return _neu_formular(
            request, db, json_fehler=["Die Liste enthält keinen Deal."], json_text=json_text, status_code=400
        )

    angelegt = [build_deal_from_import(db, daten) for daten in deals]
    db.commit()
    if len(angelegt) == 1:
        return redirect(request, f"deals/{angelegt[0].id}/edit")
    return redirect(request, "deals")


def _geschwister(db: Session, deal: Deal) -> list[dict]:
    """Andere Deals mit derselben Kombination Bank/Kontoart/Inhaber.

    Die Kombination ist fachlich *nicht* eindeutig: Nach Ablauf der Sperrfrist
    zählt man bei derselben Bank wieder als Neukunde - eine zweite Runde ist
    der Normalfall. Deshalb wird nur hingewiesen, nicht blockiert. Der Ton
    richtet sich danach, wie der Vorgänger dasteht: ein noch laufender Deal
    ist meist ein Versehen, ein lange gekündigter eine reguläre Wiederholung.
    """
    andere = (
        db.query(Deal)
        .filter(
            Deal.id != deal.id,
            Deal.bank_id == deal.bank_id,
            Deal.inhaber_id == deal.inhaber_id,
            Deal.kontoart == deal.kontoart,
        )
        .all()
    )
    heute = datetime.date.today()
    zeilen = []
    for anderer in andere:
        kuendigungsdatum = derived.parse_monat(anderer.gekuendigt_im_monat)
        if not anderer.gekuendigt or kuendigungsdatum is None:
            stufe, hinweis = "warnung", "läuft noch – wahrscheinlich ein Versehen"
        else:
            monate = derived.monate_seit_kuendigung(kuendigungsdatum, heute)
            sperrstufe = derived.sperrfrist_stufe(monate)
            if sperrstufe == derived.SPERRFRIST_GRUEN:
                stufe, hinweis = "info", f"gekündigt vor {monate} Monaten – Sperrfrist abgelaufen"
            else:
                stufe, hinweis = "warnung", f"erst vor {monate} Monaten gekündigt – Sperrfrist evtl. noch offen"
        zeilen.append({"deal": anderer, "stufe": stufe, "hinweis": hinweis})
    return zeilen


@router.get("/deals/{deal_id}/edit")
def deal_edit_form(request: Request, deal_id: int, db: Session = Depends(get_db)):
    deal = _deal_query(db).filter(Deal.id == deal_id).one_or_none()
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} existiert nicht.")
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
            "geschwister": _geschwister(db, deal),
            "jahr_heute": datetime.date.today().year,
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
    freibetrag_jahr: str = Form(""),
    praemien_auf_sparkonto: str = Form(""),
    kommentar: str = Form(""),
    zugangsdaten_gespeichert: str = Form(""),
    db: Session = Depends(get_db),
):
    deal = _hole_deal(db, deal_id)
    deal.bank = get_or_create_bank(db, bank)
    deal.inhaber = get_or_create_inhaber(db, inhaber)
    deal.kontoart = kontoart.strip()
    deal.kontonummer = kontonummer.strip() or None
    deal.kuendbar_ab = parse_date(kuendbar_ab)
    deal.gekuendigt = gekuendigt == "on"
    deal.gekuendigt_im_monat = monat_aus_formular(gekuendigt_im_monat)
    deal.kuendigung_bestaetigt = kuendigung_bestaetigt == "on"
    deal.kuendigung_hinweis = kuendigung_hinweis.strip() or None
    deal.kuendigung_hinweis_url = kuendigung_hinweis_url.strip() or None
    deal.kuendigung_hinweis_ki = False
    deal.freibetrag = parse_decimal(freibetrag)
    # Ohne Jahresangabe faellt der Betrag auf das laufende Jahr - sonst
    # erscheint er in keiner der beiden Jahresspalten und ist unsichtbar.
    deal.freibetrag_jahr = _freibetrag_jahr(freibetrag_jahr, deal.freibetrag)
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
        deal.kuendigung_hinweis_ki = False
        db.commit()
    return redirect(request, f"deals/{deal_id}/edit")


@router.post("/deals/{deal_id}/stornieren")
def deal_stornieren(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Storniert einen Deal: der Vorgang ist nicht zustande gekommen.

    Alle Bedingungen gelten als erfüllt und noch nicht erhaltene Prämien
    werden auf 0 gesetzt - der zutreffende Betrag, denn es kam keine Prämie.
    Der Deal wird über ein eigenes Feld als storniert markiert und *nicht*
    mehr als gekündigt: sonst erschien er dauerhaft in der
    Sperrfristen-Auswertung, obwohl es nichts zu sperren gibt.

    Anders als bei einem echt gekündigten Konto werden offene Bedingungen
    hier bewusst abgehakt - ein stornierter Deal ist erledigt und soll nicht
    erneut unter "Zu prüfen" auftauchen.
    """
    deal = _hole_deal(db, deal_id)
    for b in deal.bedingungen:
        b.erfuellt = True
    for p in deal.praemien:
        if not p.erhalten:
            p.betrag = Decimal("0")
            p.erhalten = True
    deal.storniert = True
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
    _hole_deal(db, deal_id)
    db.add(
        Praemie(
            deal_id=deal_id,
            quelle=_quelle_oder_400(quelle),
            betrag=parse_decimal(betrag) or 0,
            erhalten=erhalten == "on",
            auszahlung_erwartet=monat_aus_formular(auszahlung_erwartet),
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
        p.quelle = _quelle_oder_400(quelle)
        p.betrag = parse_decimal(betrag) or 0
        p.erhalten = erhalten == "on"
        p.auszahlung_erwartet = monat_aus_formular(auszahlung_erwartet)
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
    _hole_deal(db, deal_id)
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
    _hole_deal(db, deal_id)
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
    _hole_deal(db, deal_id)
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
