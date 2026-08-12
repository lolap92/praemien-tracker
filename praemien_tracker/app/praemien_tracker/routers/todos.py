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
    "Deal pflegen": "pflegen",
    "Bedingungen": "bedingungen",
    "Auf Prämie warten": "praemie",
    "Prämienauszahlung prüfen": "praemie_pruefen",
    "Kündigen": "kuendigen",
    "Bestätigung warten": "bestaetigung",
    "Zu prüfen": "pruefen",
}

# "Deal pflegen" steht direkt hinter "Manuelle Aufgaben" und vor den echten
# Pipeline-Status: fehlende Stammdaten sollen zuerst auffallen. "Zu prüfen"
# steht am Ende: das sind Dinge, die man sich ansieht, keine, die jetzt zu
# tun sind.
KATEGORIE_REIHENFOLGE = [
    "Manuelle Aufgaben",
    "Deal pflegen",
    "Bedingungen",
    "Auf Prämie warten",
    "Prämienauszahlung prüfen",
    "Kündigen",
    "Bestätigung warten",
    "Zu prüfen",
]

# Format "<kategorie-slug>-<deal-id>", z.B. "bedingungen-6" - wird für die
# id des <dialog>-Elements verwendet und daher vor der Wiederverwendung im
# <script>-Block validiert.
DIALOG_PARAM = re.compile(r"^[a-z]+-\d+$")


def _ziel(wert: str, aktuell: bool) -> bool:
    """Zielzustand aus dem Formular. Bisher wurde invertiert - damit hing das
    Ergebnis davon ab, wie oft die Anfrage ankam, nicht davon, was gewollt
    war. Ohne Angabe bleibt es beim Umschalten, damit alte Lesezeichen und
    offene Seiten weiter funktionieren."""
    if wert == "on":
        return True
    if wert == "off":
        return False
    return not aktuell


def _todos_redirect(request: Request, tab: str = "", dialog: str = "", quelle: str = ""):
    ziel = "todos"
    teile = []
    if tab:
        teile.append(f"tab={tab}")
    if dialog:
        teile.append(f"dialog={dialog}")
    if quelle:
        teile.append(f"quelle={quelle}")
    if teile:
        ziel += "?" + "&".join(teile)
    return redirect(request, ziel)


@router.get("/todos")
def todos_view(request: Request, tab: str = "", dialog: str = "", quelle: str | None = None, db: Session = Depends(get_db)):
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

    alle_ungefiltert = derived.alle_todos(deals, aufgaben)
    norm_quelle = derived.normalisiere_quelle(quelle) if quelle else None
    if norm_quelle:
        alle = []
        for t in alle_ungefiltert:
            if t.kategorie in ("Auf Prämie warten", "Prämienauszahlung prüfen"):
                if any(p.quelle == norm_quelle for p in t.elemente):
                    alle.append(t)
            else:
                if t.deal and any(p.quelle == norm_quelle for p in t.deal.praemien):
                    alle.append(t)
    else:
        alle = alle_ungefiltert

    gruppen: dict[str, list[derived.Todo]] = {}
    for t in alle:
        gruppen.setdefault(t.kategorie, []).append(t)

    # Jede Kachel bleibt immer wählbar, auch ganz ohne Inhalt - sonst
    # verschwindet sie entweder dauerhaft (wenn es die Kategorie gerade nie
    # gibt) oder sobald der Quelle-Filter gerade alle ihre Einträge ausblendet
    # (z.B. "Prämienauszahlung prüfen" bei quelle=bank, wenn dort nur
    # Spartanien-Prämien fällig sind) - in beiden Fällen kommt man von dort
    # dann nicht mehr an den Filter, um ihn zurückzusetzen (Bug), bzw. eine
    # Kategorie taucht nie wieder auf, sobald sie einmal leer war.
    # kategorien_mit_inhalt_ungefiltert unterscheidet für die Anzeige die
    # beiden Leer-Fälle: "nur durch den Filter leer" (Kachel normal, siehe
    # "Nichts für diese Quelle." unten) vs. "wirklich komplett leer,
    # unabhängig vom Filter" (Kachel ausgegraut, siehe todos.html).
    kategorien_mit_inhalt_ungefiltert = {t.kategorie for t in alle_ungefiltert}
    for kategorie in KATEGORIE_REIHENFOLGE:
        gruppen.setdefault(kategorie, [])

    # Sort "Auf Prämie warten" and "Prämienauszahlung prüfen" by faellig_bis ascending
    if "Auf Prämie warten" in gruppen:
        # Since faellig_bis is set to praemie_naechste_pruefung, which returns a date, we can sort by it.
        # Fallback to datetime.date.max if None (though praemie_naechste_pruefung always returns a date)
        gruppen["Auf Prämie warten"].sort(key=lambda x: x.faellig_bis or datetime.date.max)
    if "Prämienauszahlung prüfen" in gruppen:
        gruppen["Prämienauszahlung prüfen"].sort(key=lambda x: x.faellig_bis or datetime.date.max)

    # Sichtbare Kategorien: jede, die (ggf. leer) in gruppen steht - siehe die
    # setdefault-Aufrufe oben. Dieselbe Regel steht in todos.html noch einmal
    # (dort für die Radios/Kacheln/Panels als "kategorie in gruppen"), da die
    # Anzeige rein clientseitig per CSS umschaltet und deshalb pro Kategorie
    # selbst entscheiden muss.
    sichtbare_slugs = {KATEGORIE_SLUGS[k] for k in KATEGORIE_REIHENFOLGE if k in gruppen}
    if tab in sichtbare_slugs:
        aktiver_tab = tab
    else:
        # Default: die erste Kategorie mit tatsächlichem (gefiltertem)
        # Inhalt - sonst "Manuelle Aufgaben" (immer erreichbar, um die erste
        # Aufgabe anzulegen, wenn sonst nichts ansteht).
        mit_inhalt = [k for k in KATEGORIE_REIHENFOLGE if gruppen.get(k)]
        default_kategorie = mit_inhalt[0] if mit_inhalt else "Manuelle Aufgaben"
        aktiver_tab = KATEGORIE_SLUGS[default_kategorie]
    offener_dialog = dialog if DIALOG_PARAM.match(dialog or "") else ""

    offene_aufgaben = [a for a in aufgaben if not a.erledigt]
    erledigte_aufgaben = [a for a in aufgaben if a.erledigt]

    # Kategorien, deren Kachel zwar (jetzt immer) sichtbar ist, aber komplett
    # leer bleibt, unabhängig vom Quelle-Filter - dort gibt es also wirklich
    # nichts, im Unterschied zu "nur durch den Filter leer". Das Template
    # graut diese Kachel aus, statt sie normal (aktionsfähig) anzuzeigen. Gilt
    # auch für "Manuelle Aufgaben" - bleibt dabei weiterhin normal anklickbar
    # (der "+ Neue Aufgabe"-Button steckt ohnehin dahinter, nicht in der
    # Kachel selbst).
    leere_kategorien = {k for k in KATEGORIE_REIHENFOLGE if k not in kategorien_mit_inhalt_ungefiltert}

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
            "filter_quelle": norm_quelle or "",
            "leere_kategorien": leere_kategorien,
        },
    )


@router.post("/todos/aufgaben")
def create_aufgabe(
    request: Request,
    beschreibung: str = Form(...),
    deal_id: str = Form(""),
    faellig_bis: str = Form(""),
    quelle: str = Form(""),
    db: Session = Depends(get_db),
):
    aufgabe = Aufgabe(
        beschreibung=beschreibung.strip(),
        deal_id=int(deal_id) if deal_id else None,
        faellig_bis=parse_date(faellig_bis),
    )
    db.add(aufgabe)
    db.commit()
    return _todos_redirect(request, tab=KATEGORIE_SLUGS["Manuelle Aufgaben"], quelle=quelle)


@router.post("/todos/aufgaben/{aufgabe_id}/toggle")
def toggle_aufgabe(
    request: Request, aufgabe_id: int, tab: str = Form(""), quelle: str = Form(""), wert: str = Form(""), db: Session = Depends(get_db)
):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        aufgabe.erledigt = _ziel(wert, aufgabe.erledigt)
        db.commit()
    return _todos_redirect(request, tab, quelle=quelle)


@router.post("/todos/aufgaben/{aufgabe_id}/delete")
def delete_aufgabe(request: Request, aufgabe_id: int, quelle: str = Form(""), db: Session = Depends(get_db)):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        db.delete(aufgabe)
        db.commit()
    return _todos_redirect(request, quelle=quelle)


@router.post("/todos/bedingungen/{bedingung_id}/toggle")
def toggle_bedingung(
    request: Request,
    bedingung_id: int,
    tab: str = Form(""),
    dialog: str = Form(""),
    quelle: str = Form(""),
    wert: str = Form(""),
    db: Session = Depends(get_db),
):
    b = db.get(Bedingung, bedingung_id)
    if b:
        b.erfuellt = _ziel(wert, b.erfuellt)
        # Zeitpunkt der Erfüllung ist der Bezugspunkt für die Überfälligkeit
        # einer Prämie ohne Auszahlungsdatum - und wird beim Zurücknehmen
        # wieder geleert, damit kein Datum ohne passenden Zustand stehenbleibt.
        b.erfuellt_am = datetime.date.today() if b.erfuellt else None
        db.commit()
    return _todos_redirect(request, tab, dialog, quelle=quelle)


@router.post("/todos/praemien/{praemie_id}/toggle")
def toggle_praemie(
    request: Request,
    praemie_id: int,
    tab: str = Form(""),
    dialog: str = Form(""),
    quelle: str = Form(""),
    wert: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.get(Praemie, praemie_id)
    if p:
        p.erhalten = _ziel(wert, p.erhalten)
        db.commit()
    return _todos_redirect(request, tab, dialog, quelle=quelle)


@router.post("/todos/praemien/{praemie_id}/pruefung-verschieben")
def praemie_pruefung_verschieben(
    request: Request,
    praemie_id: int,
    tab: str = Form(""),
    dialog: str = Form(""),
    quelle: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.get(Praemie, praemie_id)
    if p:
        derived.praemie_pruefung_verschieben(p)
        db.commit()
    return _todos_redirect(request, tab, dialog, quelle=quelle)


@router.post("/todos/deals/{deal_id}/kuendigen-toggle")
def toggle_kuendigen(
    request: Request, deal_id: int, tab: str = Form(""), quelle: str = Form(""), wert: str = Form(""), db: Session = Depends(get_db)
):
    deal = db.get(Deal, deal_id)
    if deal:
        deal.gekuendigt = _ziel(wert, deal.gekuendigt)
        if deal.gekuendigt:
            # Einen gepflegten Monat nicht überschreiben: sonst ersetzt ein
            # versehentliches Ent- und Wiederankreuzen das echte
            # Kündigungsdatum durch heute - und verfälscht damit die
            # Sperrfristen-Auswertung.
            if not deal.gekuendigt_im_monat:
                deal.gekuendigt_im_monat = derived.format_monat(datetime.date.today())
        else:
            deal.gekuendigt_im_monat = None
        db.commit()
    return _todos_redirect(request, tab, quelle=quelle)


@router.post("/todos/deals/{deal_id}/bestaetigen-toggle")
def toggle_bestaetigen(
    request: Request, deal_id: int, tab: str = Form(""), quelle: str = Form(""), wert: str = Form(""), db: Session = Depends(get_db)
):
    deal = db.get(Deal, deal_id)
    if deal:
        deal.kuendigung_bestaetigt = _ziel(wert, deal.kuendigung_bestaetigt)
        db.commit()
    return _todos_redirect(request, tab, quelle=quelle)


@router.post("/todos/deals/{deal_id}/pruefung")
def pruefung_abhaken(
    request: Request,
    deal_id: int,
    regel: str = Form(...),
    signatur: str = Form(""),
    tab: str = Form(""),
    quelle: str = Form(""),
    db: Session = Depends(get_db),
):
    """Merkt, dass eine Auffälligkeit angesehen wurde. Setzt idempotent (kein
    Umschalten) und speichert die Signatur des geprüften Zustands - ändern
    sich die Fakten, erscheint der Hinweis erneut."""
    deal = db.get(Deal, deal_id)
    if deal and regel in derived.PRUEF_TEXTE:
        derived.pruefung_abhaken(deal, regel, signatur)
        db.commit()
    return _todos_redirect(request, tab, quelle=quelle)
