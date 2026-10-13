"""Kündigungs-Assistent (kuendigung_assistent.py): eine Seite je Deal, die
den Kündigungsweg zeigt, nach fehlenden Angaben fragt und daraus E-Mail und
druckfertigen Brief erzeugt."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from .. import config, iban
from .. import kuendigung_assistent as ka
from ..database import get_db
from ..helpers import parse_date
from ..ingress import redirect
from ..models import Deal
from ..templating import templates

router = APIRouter()

RECHERCHE_MELDUNGEN = {
    "ok": "Die Anforderungen der Bank wurden neu recherchiert. Bitte Empfänger und Text kurz prüfen.",
    "nichts": "Die KI hat keine verlässlichen Angaben zu dieser Bank gefunden - es gilt weiter die bisherige Vorlage.",
    "ohne_key": "Ohne Anthropic-API-Key in der Add-on-Konfiguration ist keine Recherche möglich - es gilt die Standardvorlage für eine formlose schriftliche Kündigung.",
    "demo": "Im Demo-Modus wird nichts recherchiert.",
}

# Felder, die nie abgefragt werden: die App kennt sie immer.
_IMMER_BEKANNT = {"bank", "kontoart", "termin"}

_INHABER_SPALTE = {
    "name": "voller_name",
    "strasse": "strasse",
    "plz": "plz",
    "ort": "ort",
    "email": "email",
}


def _hole_deal(db: Session, deal_id: int) -> Deal:
    deal = (
        db.query(Deal)
        .options(joinedload(Deal.bank), joinedload(Deal.inhaber))
        .filter(Deal.id == deal_id)
        .one_or_none()
    )
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} existiert nicht.")
    return deal


def _eingabefelder(deal: Deal, anforderung: ka.Anforderung, werte: dict[str, str]) -> list[dict]:
    """Die Rückfragen: immer der Absender, dazu jeder Platzhalter der
    Vorlage. Was schon bekannt ist, steht vorausgefüllt drin - so lässt sich
    auch ein gespeicherter Wert hier korrigieren."""
    schluessel = list(ka.ABSENDER_FELDER) + [
        p for p in anforderung.platzhalter if p not in ka.ABSENDER_FELDER and p not in _IMMER_BEKANNT
    ]
    hinweise = {z.get("schluessel"): z.get("hinweis", "") for z in anforderung.zusatzfelder}
    felder = []
    for k in schluessel:
        wert = werte.get(k, "")
        vorschlag = ""
        if k == "name" and not wert:
            # Der Anzeigename ist oft schon der volle Name - als Startwert
            # spart er Tipparbeit, zählt aber erst nach dem Speichern.
            vorschlag = deal.inhaber.name
        if k == "geburtsdatum":
            wert = deal.inhaber.geburtsdatum.isoformat() if deal.inhaber.geburtsdatum else ""
        felder.append(
            {
                "schluessel": k,
                "label": ka.label_fuer(anforderung, k),
                "wert": wert or vorschlag,
                "fehlt": not werte.get(k),
                "hinweis": hinweise.get(k, ""),
                "typ": "date" if k == "geburtsdatum" else "text",
            }
        )
    return felder


@router.get("/deals/{deal_id}/kuendigung")
def kuendigung_view(request: Request, deal_id: int, recherche: str = "", db: Session = Depends(get_db)):
    deal = _hole_deal(db, deal_id)
    anforderung = ka.anforderung_fuer(db, deal)
    werte = ka.werte_fuer(deal)
    fehlend = ka.fehlende(anforderung, werte)
    absender_fehlend = ka.absender_fehlend(werte)

    anschrift = deal.bank.anschrift or anforderung.empfaenger_anschrift
    email = deal.bank.kuendigung_email or anforderung.empfaenger_email
    vollstaendig = not fehlend and not absender_fehlend

    return templates.TemplateResponse(
        "kuendigung.html",
        {
            "request": request,
            "deal": deal,
            "anforderung": anforderung,
            "felder": _eingabefelder(deal, anforderung, werte),
            "fehlend": [ka.label_fuer(anforderung, k) for k in dict.fromkeys(absender_fehlend + fehlend)],
            "termin": werte["termin"],
            "standard_termin": ka.STANDARD_TERMIN,
            "anschrift": anschrift or "",
            "anschrift_aus_recherche": not deal.bank.anschrift and bool(anforderung.empfaenger_anschrift),
            "email": email or "",
            "email_aus_recherche": not deal.bank.kuendigung_email and bool(anforderung.empfaenger_email),
            "iban_warnung": bool(deal.inhaber.iban) and not iban.gueltig(deal.inhaber.iban),
            "schreiben": ka.schreiben(anforderung, werte) if vollstaendig else None,
            "signatur": ka.mail_signatur(werte),
            "meldung": RECHERCHE_MELDUNGEN.get(recherche),
            "ki_verfuegbar": bool(config.ANTHROPIC_API_KEY) and not config.DEMO_MODUS,
        },
    )


@router.post("/deals/{deal_id}/kuendigung/recherche")
def kuendigung_recherche(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Bewusst nur auf Knopfdruck: eine Websuche dauert spürbar, und die
    Seite selbst soll nie darauf warten."""
    deal = _hole_deal(db, deal_id)
    if config.DEMO_MODUS:
        ergebnis = "demo"
    elif not config.ANTHROPIC_API_KEY:
        ergebnis = "ohne_key"
    else:
        ergebnis = "ok" if ka.recherchieren(db, deal) is not None else "nichts"
    return redirect(request, f"deals/{deal_id}/kuendigung?recherche={ergebnis}")


@router.post("/deals/{deal_id}/kuendigung/angaben")
async def kuendigung_angaben(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Speichert die Rückfragen dorthin, wo sie hingehören: Absender am
    Inhaber (gilt damit für alle seine Deals), Empfänger an der Bank,
    Kontonummer am Deal, Termin und bankspezifische Zusatzfelder in
    deal.kuendigung_angaben. Nur Felder, die das Formular tatsächlich
    mitschickt, werden angefasst - ein nicht angezeigtes Feld bleibt, wie es
    ist."""
    deal = _hole_deal(db, deal_id)
    form = await request.form()
    inhaber = deal.inhaber

    def feld(name: str) -> str | None:
        wert = form.get(name)
        return None if wert is None else str(wert).strip()

    for schluessel, spalte in _INHABER_SPALTE.items():
        wert = feld(schluessel)
        if wert is not None:
            setattr(inhaber, spalte, wert or None)
    if (wert := feld("geburtsdatum")) is not None:
        inhaber.geburtsdatum = parse_date(wert)
    if (wert := feld("iban")) is not None:
        inhaber.iban = iban.normalisieren(wert)
    if (wert := feld("kontonummer")) is not None:
        deal.kontonummer = wert or None
    if (wert := feld("bank_anschrift")) is not None:
        deal.bank.anschrift = "\n".join(z.strip() for z in wert.splitlines() if z.strip()) or None
    if (wert := feld("bank_email")) is not None:
        deal.bank.kuendigung_email = wert or None

    angaben = ka.angaben_laden(deal)
    if (wert := feld("termin")) is not None:
        angaben["termin"] = "" if wert == ka.STANDARD_TERMIN else wert
    for name in form.keys():
        if name.startswith("zusatz_"):
            angaben[name.removeprefix("zusatz_")] = feld(name) or ""
    ka.angaben_speichern(deal, angaben)

    db.commit()
    return redirect(request, f"deals/{deal_id}/kuendigung#schreiben")


def _brief(request: Request, deal: Deal, db: Session, betreff: str | None, text: str | None):
    anforderung = ka.anforderung_fuer(db, deal)
    werte = ka.werte_fuer(deal)
    fehlend = ka.absender_fehlend(werte)
    if betreff is None or text is None:
        fehlend += ka.fehlende(anforderung, werte)
        entwurf = ka.schreiben(anforderung, werte)
        betreff, text = entwurf["betreff"], entwurf["text"]
    anschrift = deal.bank.anschrift or ""
    return templates.TemplateResponse(
        "kuendigung_brief.html",
        {
            "request": request,
            "deal": deal,
            "fehlend": [ka.label_fuer(anforderung, k) for k in dict.fromkeys(fehlend)],
            "ohne_anschrift": not anschrift,
            "absender": [werte["name"], werte["strasse"], f"{werte['plz']} {werte['ort']}".strip()],
            "empfaenger": anschrift.splitlines(),
            "ort_datum": ", ".join(t for t in (werte["ort"], datetime.date.today().strftime("%d.%m.%Y")) if t),
            "betreff": betreff,
            "absaetze": [a.strip() for a in text.replace("\r\n", "\n").split("\n\n") if a.strip()],
            "name": werte["name"],
        },
    )


@router.get("/deals/{deal_id}/kuendigung/brief")
def kuendigung_brief(request: Request, deal_id: int, db: Session = Depends(get_db)):
    return _brief(request, _hole_deal(db, deal_id), db, None, None)


@router.post("/deals/{deal_id}/kuendigung/brief")
def kuendigung_brief_bearbeitet(
    request: Request,
    deal_id: int,
    betreff: str = Form(""),
    text: str = Form(""),
    db: Session = Depends(get_db),
):
    """Druckansicht mit dem im Assistenten nachbearbeiteten Text - der wird
    nicht gespeichert, sondern direkt gesetzt."""
    # Ein leer abgeschickter Text fällt auf den Entwurf zurück, statt ein
    # leeres Blatt zu setzen.
    if not text.strip():
        return _brief(request, _hole_deal(db, deal_id), db, None, None)
    return _brief(request, _hole_deal(db, deal_id), db, betreff.strip(), text.strip())
