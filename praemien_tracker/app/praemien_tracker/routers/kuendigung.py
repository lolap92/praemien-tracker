"""Kündigungs-Assistent (kuendigung_assistent.py): eine Seite je Deal, die
den Kündigungsweg zeigt, nach fehlenden Angaben fragt und daraus E-Mail und
Brief (Druckansicht, PDF, Word) erzeugt. Jedes erzeugte Schreiben wird als
Momentaufnahme gespeichert und lässt sich als versendet markieren."""

from __future__ import annotations

import datetime
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session, joinedload

from .. import config, iban
from .. import kuendigung_assistent as ka
from .. import kuendigung_dokumente as kd
from ..database import get_db
from ..helpers import als_gekuendigt_markieren, parse_date
from ..ingress import redirect
from ..models import Deal, Kuendigungsschreiben
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
        .options(joinedload(Deal.bank), joinedload(Deal.inhaber), joinedload(Deal.kuendigungsschreiben))
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
            "gespeichert": list(reversed(deal.kuendigungsschreiben)),
            "heute": datetime.date.today(),
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


AUSGABEN = {"pdf": "brief", "docx": "brief", "druck": "brief", "mail": "email"}

_MEDIENTYPEN = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _hole_schreiben(deal: Deal, schreiben_id: int) -> Kuendigungsschreiben:
    """Nur Schreiben dieses Deals - eine fremde ID in der URL führt zu 404
    statt zum Schreiben eines anderen Deals."""
    for s in deal.kuendigungsschreiben:
        if s.id == schreiben_id:
            return s
    raise HTTPException(status_code=404, detail=f"Schreiben {schreiben_id} gehört nicht zu Deal {deal.id}.")


def _dateiname(deal: Deal, schreiben: Kuendigungsschreiben, endung: str) -> str:
    teile = ["Kuendigung", deal.bank.name, deal.kontoart, deal.inhaber.name, schreiben.datum.isoformat()]
    roh = "_".join(teile)
    ersetzt = roh.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}))
    sicher = re.sub(r"[^A-Za-z0-9._-]+", "-", ersetzt).strip("-")
    return f"{sicher}.{endung}"


def _datei(deal: Deal, schreiben: Kuendigungsschreiben, format_: str) -> Response:
    brief = kd.brief_aus(schreiben)
    inhalt = kd.als_pdf(brief) if format_ == "pdf" else kd.als_docx(brief)
    name = _dateiname(deal, schreiben, format_)
    return Response(
        content=inhalt,
        media_type=_MEDIENTYPEN[format_],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _druckansicht(request: Request, deal: Deal, schreiben: Kuendigungsschreiben):
    return templates.TemplateResponse(
        "kuendigung_brief.html",
        {"request": request, "deal": deal, "schreiben": schreiben, "brief": kd.brief_aus(schreiben)},
    )


@router.post("/deals/{deal_id}/kuendigung/schreiben")
def kuendigung_schreiben(
    request: Request,
    deal_id: int,
    ausgabe: str = Form(...),
    betreff: str = Form(""),
    text: str = Form(""),
    db: Session = Depends(get_db),
):
    """Speichert das (ggf. nachbearbeitete) Schreiben als Entwurf und gibt
    es gleich im gewünschten Format aus - PDF, Word, Druckansicht oder, für
    die E-Mail, nur die ID (das Mailprogramm öffnet das Skript der Seite).

    Ein Brief braucht Absender und Empfängeranschrift; fehlt eines, wird
    gar nicht erst gespeichert. Die Seite bietet die Knöpfe dann zwar nicht
    an, ein alter Tab könnte sie aber noch abschicken."""
    deal = _hole_deal(db, deal_id)
    kanal = AUSGABEN.get(ausgabe)
    if kanal is None:
        raise HTTPException(status_code=400, detail=f"Unbekannte Ausgabe: {ausgabe!r}")
    betreff, text = betreff.strip(), text.strip()
    if not betreff or not text:
        raise HTTPException(status_code=400, detail="Betreff und Text dürfen nicht leer sein.")
    if kanal == "brief":
        fehlend = ka.absender_fehlend(ka.werte_fuer(deal))
        if fehlend or not deal.bank.anschrift:
            labels = [ka.STANDARD_FELDER[f] for f in fehlend] + ([] if deal.bank.anschrift else ["Postanschrift der Bank"])
            raise HTTPException(status_code=400, detail="Für den Brief fehlt noch: " + ", ".join(labels) + ".")

    schreiben = ka.schreiben_speichern(deal, kanal, betreff, text)
    db.commit()

    if ausgabe == "mail":
        return JSONResponse({"id": schreiben.id})
    if ausgabe == "druck":
        return _druckansicht(request, deal, schreiben)
    return _datei(deal, schreiben, ausgabe)


@router.get("/deals/{deal_id}/kuendigung/schreiben/{schreiben_id}/{format_}")
def kuendigung_schreiben_abrufen(request: Request, deal_id: int, schreiben_id: int, format_: str, db: Session = Depends(get_db)):
    """Ein gespeichertes Schreiben erneut ausgeben - aus der Momentaufnahme,
    also genau so, wie es damals erzeugt wurde."""
    deal = _hole_deal(db, deal_id)
    schreiben = _hole_schreiben(deal, schreiben_id)
    if format_ == "druck" and schreiben.kanal == "brief":
        return _druckansicht(request, deal, schreiben)
    if format_ in _MEDIENTYPEN and schreiben.kanal == "brief":
        return _datei(deal, schreiben, format_)
    raise HTTPException(status_code=404, detail=f"Format {format_!r} gibt es für dieses Schreiben nicht.")


@router.post("/deals/{deal_id}/kuendigung/schreiben/{schreiben_id}/versendet")
def kuendigung_schreiben_versendet(
    request: Request, deal_id: int, schreiben_id: int, datum: str = Form(""), db: Session = Depends(get_db)
):
    """Hält fest, dass das Schreiben raus ist, und hakt den Deal als
    gekündigt ab - derselbe Weg wie das Häkchen im Kündigen-Reiter, ein
    schon gepflegter Kündigungsmonat bleibt also stehen."""
    deal = _hole_deal(db, deal_id)
    schreiben = _hole_schreiben(deal, schreiben_id)
    versendet = parse_date(datum.strip()) or datetime.date.today()
    schreiben.versendet_am = versendet
    als_gekuendigt_markieren(deal, versendet)
    db.commit()
    return redirect(request, f"deals/{deal_id}/kuendigung#gespeichert")


@router.post("/deals/{deal_id}/kuendigung/schreiben/{schreiben_id}/loeschen")
def kuendigung_schreiben_loeschen(request: Request, deal_id: int, schreiben_id: int, db: Session = Depends(get_db)):
    """Löscht nur das Schreiben - ein dadurch gesetztes "gekündigt" bleibt,
    denn ob tatsächlich gekündigt wurde, ist ein eigener Fakt."""
    deal = _hole_deal(db, deal_id)
    deal.kuendigungsschreiben.remove(_hole_schreiben(deal, schreiben_id))
    db.commit()
    return redirect(request, f"deals/{deal_id}/kuendigung#gespeichert")
