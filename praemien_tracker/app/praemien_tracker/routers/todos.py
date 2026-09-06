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

# Zeitraum-Filter im Reiter "Manuelle Aufgaben". Voreinstellung ist
# "aktuell": eine Aufgabe, die erst in drei Wochen ansteht, ist nichts, was
# heute zu erledigen wäre - sie würde die Liste (und mit monatlichen Aufgaben
# erst recht) mit Dingen füllen, die noch gar nicht dran sind. Über den Filter
# bleiben die späteren Termine jederzeit einsehbar.
FAELLIG_AKTUELL = "aktuell"
FAELLIG_ZUKUENFTIG = "zukuenftig"
FAELLIG_ALLE = "alle"
FAELLIG_LABELS = {
    FAELLIG_AKTUELL: "Aktuell fällig",
    FAELLIG_ZUKUENFTIG: "Später fällig",
    FAELLIG_ALLE: "Alle",
}
FAELLIG_WERTE = tuple(FAELLIG_LABELS)


def _normalisiere_faellig(wert: str | None) -> str:
    return wert if wert in FAELLIG_LABELS else FAELLIG_AKTUELL


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


def _todos_redirect(
    request: Request, tab: str = "", dialog: str = "", quelle: str = "", feld: str = "", faellig: str = ""
):
    ziel = "todos"
    teile = []
    if tab:
        teile.append(f"tab={tab}")
    if dialog:
        teile.append(f"dialog={dialog}")
    if quelle:
        teile.append(f"quelle={quelle}")
    if feld:
        teile.append(f"feld={feld}")
    # Nur mitschleifen, wenn vom Standard abweichend - sonst stünde nach jedem
    # Abhaken "?faellig=aktuell" in der Adresszeile, ohne etwas zu ändern.
    if faellig and faellig != FAELLIG_AKTUELL:
        teile.append(f"faellig={faellig}")
    if teile:
        ziel += "?" + "&".join(teile)
    return redirect(request, ziel)


@router.get("/todos")
def todos_view(
    request: Request,
    tab: str = "",
    dialog: str = "",
    quelle: str | None = None,
    feld: str | None = None,
    faellig: str | None = None,
    db: Session = Depends(get_db),
):
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

    valid_felder = {"kontonummer", "kontofuehrungsgebuehren", "zugangsdaten_gespeichert", "auszahlung_erwartet"}
    norm_feld = feld.strip().lower() if feld and feld.strip().lower() in valid_felder else None

    norm_faellig = _normalisiere_faellig(faellig.strip().lower() if faellig else None)

    alle = []
    for t in alle_ungefiltert:
        # Quelle filter
        if norm_quelle:
            if t.kategorie in ("Auf Prämie warten", "Prämienauszahlung prüfen"):
                if not any(p.quelle == norm_quelle for p in t.elemente):
                    continue
            else:
                if not (t.deal and any(p.quelle == norm_quelle for p in t.deal.praemien)):
                    continue

        # Zeitraum-Filter, nur für manuelle Aufgaben: alles andere hat kein
        # frei gewähltes Fälligkeitsdatum, das sich sinnvoll in "jetzt" und
        # "später" trennen ließe (siehe Todo.zukuenftig).
        if t.kategorie == "Manuelle Aufgaben":
            if norm_faellig == FAELLIG_AKTUELL and t.zukuenftig:
                continue
            if norm_faellig == FAELLIG_ZUKUENFTIG and not t.zukuenftig:
                continue

        # Feld filter for "Deal pflegen"
        if norm_feld and t.kategorie == "Deal pflegen":
            matching_elements = []
            for f in t.elemente:
                if norm_feld == "kontonummer" and f.feld == "kontonummer":
                    matching_elements.append(f)
                elif norm_feld == "kontofuehrungsgebuehren" and f.feld == "kontofuehrungsgebuehren":
                    matching_elements.append(f)
                elif norm_feld == "zugangsdaten_gespeichert" and f.feld == "zugangsdaten_gespeichert":
                    matching_elements.append(f)
                elif norm_feld == "auszahlung_erwartet" and (f.feld.endswith("_auszahlung_erwartet") or f.feld.startswith("praemie_")):
                    matching_elements.append(f)

            if not matching_elements:
                continue

            bezeichnung = f"{t.deal.bank.name} · {t.deal.kontoart} · {t.deal.inhaber.name}"
            t.elemente = matching_elements
            t.text = f"{bezeichnung}: {len(matching_elements)} Angabe(n) offen"

        alle.append(t)

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

    # Alle Listen alphabetisch nach Bankname (dann Inhaber) sortiert, statt in
    # DB-Reihenfolge - so steht bei mehreren offenen Punkten quer durch die
    # Kategorien immer dieselbe Bank an derselben Stelle. Manuelle Aufgaben
    # ohne Deal haben keinen Banknamen und landen deshalb ans Ende. Bei
    # gleicher Bank/gleichem Inhaber bleibt faellig_bis als Tiebreak
    # entscheidend - dort ist die Dringlichkeit weiterhin wichtig (siehe
    # praemie_naechste_pruefung).
    for kategorie_liste in gruppen.values():
        kategorie_liste.sort(
            key=lambda t: (
                1 if t.deal is None else 0,
                t.deal.bank.name.lower() if t.deal else "",
                t.deal.inhaber.name.lower() if t.deal else "",
                t.faellig_bis or datetime.date.max,
            )
        )

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

    def _aufgabe_sortierschluessel(a: Aufgabe):
        return (1 if a.deal is None else 0, a.deal.bank.name.lower() if a.deal else "", a.deal.inhaber.name.lower() if a.deal else "")

    offene_aufgaben = sorted((a for a in aufgaben if not a.erledigt), key=_aufgabe_sortierschluessel)
    erledigte_aufgaben = sorted((a for a in aufgaben if a.erledigt), key=_aufgabe_sortierschluessel)

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
            "filter_feld": norm_feld or "",
            "filter_faellig": norm_faellig,
            "faellig_labels": FAELLIG_LABELS,
            "wiederholung_labels": derived.WIEDERHOLUNG_LABELS,
            "wiederholung_monatlich": derived.WIEDERHOLUNG_MONATLICH,
            "leere_kategorien": leere_kategorien,
        },
    )


@router.post("/todos/aufgaben")
def create_aufgabe(
    request: Request,
    beschreibung: str = Form(...),
    deal_id: str = Form(""),
    faellig_bis: str = Form(""),
    wiederholung: str = Form(""),
    quelle: str = Form(""),
    db: Session = Depends(get_db),
):
    # deal_id kommt aus einem <select> mit gültigen IDs oder leer. Trotzdem
    # robust: eine nicht-numerische oder unbekannte ID darf keinen 500 auslösen
    # (nicht-numerisch: int() wirft; unbekannt: Fremdschlüssel-Fehler beim
    # Commit). Nicht auflösbar -> Aufgabe ohne Deal.
    ziel_deal = db.get(Deal, int(deal_id)) if deal_id.strip().isdigit() else None
    art = derived.normalisiere_wiederholung(wiederholung)
    termin = _termin_mit_anker(art, parse_date(faellig_bis))
    aufgabe = Aufgabe(
        beschreibung=beschreibung.strip(),
        deal_id=ziel_deal.id if ziel_deal else None,
        faellig_bis=termin,
        wiederholung=art,
    )
    db.add(aufgabe)
    db.commit()
    return _todos_redirect(
        request,
        tab=KATEGORIE_SLUGS["Manuelle Aufgaben"],
        quelle=quelle,
        faellig=_sichtbarer_filter(termin, FAELLIG_AKTUELL),
    )


def _sichtbarer_filter(termin: datetime.date | None, aktueller_filter: str) -> str:
    """Nach dem Speichern den Filter so wählen, dass die Aufgabe auch zu sehen
    ist.

    Bekommt eine Aufgabe ein Datum in der Zukunft, fällt sie aus der
    Voreinstellung "aktuell fällig" heraus - sie wäre nach dem Speichern
    schlicht verschwunden, als wäre sie gelöscht worden. In dem Fall wird auf
    "alle" umgeschaltet: die Liste zeigt dann weiterhin alles und die eben
    bearbeitete Aufgabe steht sichtbar darin. Ein bereits bewusst gesetzter
    Filter bleibt unangetastet."""
    if aktueller_filter != FAELLIG_AKTUELL:
        return aktueller_filter
    if termin and termin > datetime.date.today():
        return FAELLIG_ALLE
    return aktueller_filter


def _termin_mit_anker(art: str, termin: datetime.date | None) -> datetime.date | None:
    """Eine monatliche Aufgabe braucht einen Anker, an dem die Kette hängt -
    ohne Datum gäbe es keinen nächsten Termin. Ohne Angabe ist das der
    heutige Tag: die Aufgabe steht damit sofort an und wiederholt sich von da
    an taggenau. Für einmalige Aufgaben bleibt ein leeres Datum leer."""
    if art == derived.WIEDERHOLUNG_MONATLICH and termin is None:
        return datetime.date.today()
    return termin


@router.post("/todos/aufgaben/{aufgabe_id}/bearbeiten")
def edit_aufgabe(
    request: Request,
    aufgabe_id: int,
    beschreibung: str = Form(...),
    deal_id: str = Form(""),
    faellig_bis: str = Form(""),
    wiederholung: str = Form(""),
    tab: str = Form(""),
    quelle: str = Form(""),
    faellig: str = Form(""),
    db: Session = Depends(get_db),
):
    """Beschreibung, Deal, Frist und Wiederholungsart einer Aufgabe ändern.

    Ändert ausschließlich diese eine Zeile: ein bereits angelegter
    Folgetermin bleibt, wie er ist. Er ist aus dem damaligen Stand
    hervorgegangen und würde sonst rückwirkend umgeschrieben - die nächste
    Wiederholung rechnet ohnehin mit den neuen Angaben.
    """
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        # Leere Beschreibung wäre eine Aufgabe ohne Text: das Formular
        # verlangt sie ohnehin (required), hier bleibt der bisherige Text
        # stehen, statt ihn zu löschen.
        neuer_text = beschreibung.strip()
        if neuer_text:
            aufgabe.beschreibung = neuer_text
        ziel_deal = db.get(Deal, int(deal_id)) if deal_id.strip().isdigit() else None
        aufgabe.deal_id = ziel_deal.id if ziel_deal else None
        aufgabe.wiederholung = derived.normalisiere_wiederholung(wiederholung)
        aufgabe.faellig_bis = _termin_mit_anker(aufgabe.wiederholung, parse_date(faellig_bis))
        db.commit()
        faellig = _sichtbarer_filter(aufgabe.faellig_bis, _normalisiere_faellig(faellig))
    return _todos_redirect(request, tab, quelle=quelle, faellig=faellig)


def _nachfolger_anlegen(db: Session, aufgabe: Aufgabe) -> None:
    """Beim Abhaken einer monatlichen Aufgabe den Termin des nächsten Monats
    anlegen. Bewusst eine neue Zeile statt eines verschobenen Datums: die
    erledigte Aufgabe bleibt als Fakt bestehen und taucht wie jede andere
    unter "Erledigte Aufgaben" auf.

    Hängt an derselben Aufgabe schon ein Nachfolger (z.B. weil sie schon
    einmal abgehakt und wieder geöffnet wurde), entsteht kein zweiter."""
    if derived.normalisiere_wiederholung(aufgabe.wiederholung) != derived.WIEDERHOLUNG_MONATLICH:
        return
    if db.query(Aufgabe.id).filter(Aufgabe.vorgaenger_id == aufgabe.id).first() is not None:
        return
    db.add(
        Aufgabe(
            beschreibung=aufgabe.beschreibung,
            deal_id=aufgabe.deal_id,
            faellig_bis=derived.naechster_monatstermin(aufgabe.faellig_bis),
            wiederholung=derived.WIEDERHOLUNG_MONATLICH,
            vorgaenger_id=aufgabe.id,
        )
    )


def _nachfolger_zuruecknehmen(db: Session, aufgabe: Aufgabe) -> None:
    """Wird eine erledigte Aufgabe wieder geöffnet, war das Abhaken ein
    Versehen - dann muss auch der dabei erzeugte Nachfolger wieder weg, sonst
    stünde dieselbe Aufgabe zweimal offen in der Liste.

    Nur noch offene Nachfolger werden entfernt: ist der Folgetermin
    inzwischen selbst abgehakt (und hat womöglich schon einen eigenen
    Nachfolger), gehört er zur Historie und bleibt stehen."""
    for nachfolger in db.query(Aufgabe).filter(
        Aufgabe.vorgaenger_id == aufgabe.id, Aufgabe.erledigt.is_(False)
    ):
        db.delete(nachfolger)


@router.post("/todos/aufgaben/{aufgabe_id}/toggle")
def toggle_aufgabe(
    request: Request,
    aufgabe_id: int,
    tab: str = Form(""),
    quelle: str = Form(""),
    faellig: str = Form(""),
    wert: str = Form(""),
    db: Session = Depends(get_db),
):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        vorher = aufgabe.erledigt
        aufgabe.erledigt = _ziel(wert, aufgabe.erledigt)
        if aufgabe.erledigt and not vorher:
            _nachfolger_anlegen(db, aufgabe)
        elif vorher and not aufgabe.erledigt:
            _nachfolger_zuruecknehmen(db, aufgabe)
        db.commit()
    return _todos_redirect(request, tab, quelle=quelle, faellig=faellig)


@router.post("/todos/aufgaben/{aufgabe_id}/delete")
def delete_aufgabe(
    request: Request,
    aufgabe_id: int,
    tab: str = Form(""),
    quelle: str = Form(""),
    faellig: str = Form(""),
    db: Session = Depends(get_db),
):
    aufgabe = db.get(Aufgabe, aufgabe_id)
    if aufgabe:
        # Ein noch offener Nachfolger würde sonst als verwaiste Zeile
        # weiterleben - wer die Aufgabe löscht, will die Reihe beenden.
        # Bereits erledigte Nachfolger bleiben als Historie bestehen; ihr
        # Verweis auf die gelöschte Zeile wird dabei geleert.
        for nachfolger in db.query(Aufgabe).filter(Aufgabe.vorgaenger_id == aufgabe.id):
            if nachfolger.erledigt:
                nachfolger.vorgaenger_id = None
            else:
                db.delete(nachfolger)
        # Erst die Nachfolger wegschreiben, dann die Aufgabe selbst: ohne
        # ORM-Beziehung kennt SQLAlchemy die Abhängigkeit nicht und würde
        # beide Löschungen in einem Rutsch schicken - der Fremdschlüssel auf
        # die noch verwiesene Zeile schlüge dann fehl.
        db.flush()
        db.delete(aufgabe)
        db.commit()
    return _todos_redirect(request, tab, quelle=quelle, faellig=faellig)


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
