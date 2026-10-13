"""Kündigungs-Assistent (kuendigung_assistent.py): eine Seite je Deal, die
den Kündigungsweg zeigt, nach fehlenden Angaben fragt und daraus E-Mail und
Brief (Druckansicht, PDF, Word) erzeugt. Jedes erzeugte Schreiben wird als
Momentaufnahme gespeichert und lässt sich als versendet markieren."""

from __future__ import annotations

import datetime
import json
import logging
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session, joinedload

from .. import config, iban
from .. import kuendigung_assistent as ka
from .. import kuendigung_dokumente as kd
from .. import kuendigung_formular as kf
from ..anthropic_client import anthropic_client
from ..database import get_db
from ..helpers import als_gekuendigt_markieren, parse_date
from ..ingress import redirect
from ..models import Deal, Kuendigungsschreiben
from ..templating import templates

router = APIRouter()
logger = logging.getLogger("praemien_tracker")

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
            "formular": kf.formular_fuer(db, deal),
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
    if schreiben.kanal == "formular":
        inhalt = schreiben.datei or b""
    else:
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
    if format_ == "pdf" and schreiben.kanal == "formular" and schreiben.datei:
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


# ------------------------------------------------- Formular der Bank ----


def _formular_redirect(request: Request, deal_id: int, meldung: str = "") -> Response:
    ziel = f"deals/{deal_id}/kuendigung/formular"
    if meldung:
        ziel += "?" + urlencode({"meldung": meldung})
    return redirect(request, ziel)


def _ki_client():
    return None if config.DEMO_MODUS else anthropic_client()


@router.get("/deals/{deal_id}/kuendigung/formular")
def formular_view(request: Request, deal_id: int, meldung: str = "", db: Session = Depends(get_db)):
    deal = _hole_deal(db, deal_id)
    formular = kf.formular_fuer(db, deal)
    anforderung = ka.anforderung_fuer(db, deal)
    werte = ka.werte_fuer(deal)
    zusatzfelder = kf.zusatzfelder_von(formular) if formular else []
    feldwerte = kf.feldwerte(formular, deal) if formular else []
    zusatz_labels = {z["schluessel"]: z["label"] for z in zusatzfelder}
    fehlend = dict.fromkeys(
        zusatz_labels.get(p) or ka.label_fuer(anforderung, p) for fw in feldwerte for p in fw.fehlt
    )

    # Ausfüllhilfe für nicht ausfüllbare Formulare: alles, was bekannt ist.
    hilfe_schluessel = [k for k in ka.STANDARD_FELDER if k not in ("bank", "kontoart", "termin")]
    hilfe = [(ka.label_fuer(anforderung, k), werte.get(k)) for k in hilfe_schluessel if werte.get(k)] + [
        (z["label"], werte.get(z["schluessel"])) for z in zusatzfelder if werte.get(z["schluessel"])
    ]

    return templates.TemplateResponse(
        "kuendigung_formular.html",
        {
            "request": request,
            "deal": deal,
            "formular": formular,
            "formular_url": anforderung.formular_url,
            "feldwerte": feldwerte,
            "zusatzfelder": [dict(z, wert=werte.get(z["schluessel"], "")) for z in zusatzfelder],
            "fehlend": list(fehlend),
            "hilfe": hilfe,
            "meldung": meldung,
            "ki_verfuegbar": bool(config.ANTHROPIC_API_KEY) and not config.DEMO_MODUS,
            "laden_moeglich": not config.DEMO_MODUS,
            "an": kf.AN,
            "aus": kf.AUS,
        },
    )


@router.post("/deals/{deal_id}/kuendigung/formular/laden")
def formular_laden(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Holt das Formular unter der recherchierten formular_url. Im
    Demo-Modus nie - dort geht keine Anfrage nach draußen."""
    deal = _hole_deal(db, deal_id)
    url = ka.anforderung_fuer(db, deal).formular_url
    if config.DEMO_MODUS or not url:
        return _formular_redirect(request, deal_id, "Kein Formular-Link vorhanden." if not url else "Im Demo-Modus wird nichts heruntergeladen.")
    try:
        pdf = kf.von_url_laden(url)
        kf.speichern(db, deal, pdf, url, _ki_client())
    except kf.FormularFehler as exc:
        return _formular_redirect(request, deal_id, str(exc))
    db.commit()
    return _formular_redirect(request, deal_id)


@router.post("/deals/{deal_id}/kuendigung/formular/hochladen")
async def formular_hochladen(request: Request, deal_id: int, db: Session = Depends(get_db)):
    deal = _hole_deal(db, deal_id)
    form = await request.form()
    datei = form.get("datei")
    if datei is None or not hasattr(datei, "read"):
        return _formular_redirect(request, deal_id, "Bitte eine PDF-Datei auswählen.")
    pdf = await datei.read(kf.MAX_GROESSE + 1)
    if len(pdf) > kf.MAX_GROESSE:
        return _formular_redirect(request, deal_id, "Die Datei ist größer als 10 MB.")
    try:
        kf.speichern(db, deal, pdf, f"hochgeladen: {datei.filename or 'formular.pdf'}", _ki_client())
    except kf.FormularFehler as exc:
        return _formular_redirect(request, deal_id, str(exc))
    db.commit()
    return _formular_redirect(request, deal_id)


@router.post("/deals/{deal_id}/kuendigung/formular/zuordnen")
def formular_zuordnen(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Zuordnung neu ermitteln - etwa nachdem ein API-Key eingetragen wurde.
    Eigene Werte bleiben erhalten."""
    deal = _hole_deal(db, deal_id)
    formular = kf.formular_fuer(db, deal)
    if formular is None:
        raise HTTPException(status_code=404, detail="Für diese Bank ist kein Formular hinterlegt.")
    kf.zuordnen(formular, deal, _ki_client())
    db.commit()
    return _formular_redirect(request, deal_id, "Zuordnung neu ermittelt." if formular.zuordnung_ki else "Zuordnung per Stichwörter neu ermittelt.")


def _formular_werte_uebernehmen(form, deal: Deal, formular) -> None:
    """Ein Feldwert, der genau dem Vorschlag entspricht, wird nicht als
    eigener gespeichert - sonst folgte er einer späteren Adressänderung
    nicht mehr.

    Verglichen wird mit dem Vorschlag, wie er beim Anzeigen galt, also vor
    dem Übernehmen der Zusatzangaben: Wer gleichzeitig eine Kundennummer
    einträgt, schickt das zugehörige Feld noch leer mit - das ist kein
    bewusst geleertes Feld, sondern der alte Vorschlag."""
    angezeigt = {fw.feld.name: fw.vorschlag for fw in kf.feldwerte(formular, deal)}
    angaben = ka.angaben_laden(deal)
    for name in form.keys():
        if name.startswith("zusatz_"):
            angaben[name.removeprefix("zusatz_")] = str(form.get(name) or "").strip()
    ka.angaben_speichern(deal, angaben)

    eigen = kf.eigene_werte(deal)
    for fw in kf.feldwerte(formular, deal):
        eingabe = form.get(f"feld_{fw.feld.name}")
        if eingabe is None:
            continue
        eingabe = str(eingabe).strip()
        if eingabe in (fw.vorschlag, angezeigt.get(fw.feld.name)):
            eigen.pop(fw.feld.name, None)
        else:
            eigen[fw.feld.name] = eingabe
    deal.kuendigung_formular_werte = json.dumps(eigen, ensure_ascii=False, sort_keys=True) if eigen else None


@router.post("/deals/{deal_id}/kuendigung/formular/angaben")
async def formular_angaben(request: Request, deal_id: int, db: Session = Depends(get_db)):
    """Speichern oder - mit aktion=ausfuellen - speichern und das
    ausgefüllte Formular herunterladen. Das Ergebnis landet wie Brief und
    E-Mail unter "Gespeicherte Schreiben"."""
    deal = _hole_deal(db, deal_id)
    formular = kf.formular_fuer(db, deal)
    if formular is None:
        raise HTTPException(status_code=404, detail="Für diese Bank ist kein Formular hinterlegt.")
    form = await request.form()
    _formular_werte_uebernehmen(form, deal, formular)
    if form.get("aktion") != "ausfuellen":
        db.commit()
        return _formular_redirect(request, deal_id, "Gespeichert.")

    werte = kf.feldwerte(formular, deal)
    try:
        pdf = kf.ausfuellen(formular.pdf, werte)
    except Exception:
        db.commit()
        logger.exception("Formular für Deal %s ließ sich nicht ausfüllen.", deal_id)
        return _formular_redirect(request, deal_id, "Das Formular ließ sich nicht ausfüllen - bitte die Ausfüllhilfe nutzen.")
    liste = "\n".join(
        f"{fw.feld.label}: {fw.wert}" for fw in werte if fw.wert and fw.wert != kf.AUS
    )
    schreiben = ka.schreiben_speichern(deal, "formular", f"Kündigungsformular {deal.bank.name}", liste, datei=pdf)
    db.commit()
    return _datei(deal, schreiben, "pdf")


@router.get("/deals/{deal_id}/kuendigung/formular/original")
def formular_original(deal_id: int, db: Session = Depends(get_db)):
    deal = _hole_deal(db, deal_id)
    formular = kf.formular_fuer(db, deal)
    if formular is None:
        raise HTTPException(status_code=404, detail="Für diese Bank ist kein Formular hinterlegt.")
    return Response(
        content=formular.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="Kuendigungsformular-leer.pdf"'},
    )


@router.post("/deals/{deal_id}/kuendigung/formular/entfernen")
def formular_entfernen(request: Request, deal_id: int, db: Session = Depends(get_db)):
    deal = _hole_deal(db, deal_id)
    formular = kf.formular_fuer(db, deal)
    if formular is not None:
        db.delete(formular)
    deal.kuendigung_formular_werte = None
    db.commit()
    return redirect(request, f"deals/{deal_id}/kuendigung")
