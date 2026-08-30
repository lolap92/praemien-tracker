from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..ingress import redirect
from ..models import Deal, Aufgabe
from ..templating import templates
from .vorschlaege import zaehlen as vorschlaege_zaehlen

router = APIRouter()


@dataclass
class Aktion:
    """Eine Zeile der Startseite: *eine* Sache, die der Nutzer tun kann.

    Bewusst kein reiner Zähler wie früher: ohne Titel-in-Klartext, ohne
    Beispiel-Deal und ohne Ziel-Link musste man jede Zahl erst antippen, um
    zu erfahren, ob sich dahinter Arbeit verbirgt.
    """

    schluessel: str
    titel: str
    anzahl: int
    url: str
    farbe: str
    beispiele: list[str] = field(default_factory=list)
    weitere: int = 0
    ueberfaellig: int = 0
    hinweis: str = ""


# Reihenfolge der Aufgabenzeilen, wenn nichts überfällig ist: erst was eine
# Frist hat und Geld kosten kann (Bedingungen), dann fehlendes Geld
# (Auszahlung), dann laufende Kosten (Kündigen), dann Selbstgesetztes.
# Überfälliges wird davor einsortiert, siehe _sortierung.
AKTION_KATEGORIEN = [
    ("Bedingungen", "Bedingungen erfüllen", "todos?tab=bedingungen", "cond"),
    ("Prämienauszahlung prüfen", "Prämienauszahlung prüfen", "todos?tab=praemie_pruefen", "wait"),
    ("Kündigen", "Konto kündigen", "todos?tab=kuendigen", "cancel"),
    ("Manuelle Aufgaben", "Eigene Aufgaben", "todos?tab=manuell", "accent"),
    ("Zu prüfen", "Auffälligkeiten prüfen", "todos?tab=pruefen", "wait"),
]

_RANG = {kategorie: i for i, (kategorie, _, _, _) in enumerate(AKTION_KATEGORIEN)}
# Überfällige Prämien werden aus "Auf Prämie warten" nach oben gezogen (siehe
# unten) und stehen dort ganz vorne - eine Prämie, die nicht gekommen ist,
# ist das teuerste offene Thema.
_RANG_UEBERFAELLIGE_PRAEMIE = -1
_RANG_VORSCHLAEGE = len(AKTION_KATEGORIEN)


def _kurzname(todo: derived.Todo) -> str:
    """Knappe Bezeichnung für die Beispielzeile. Der volle Todo-Text
    ("Bank · Kontoart · Inhaber: ...") ist für eine Übersichtszeile zu lang."""
    if todo.deal is not None:
        return f"{todo.deal.bank.name} · {todo.deal.kontoart}"
    return todo.text


def _beispiele(todos: list[derived.Todo], max_anzahl: int = 2) -> tuple[list[str], int]:
    """Die ersten paar Betroffenen namentlich, der Rest als Zahl. Überfälliges
    zuerst, damit im Beispiel steht, was drängt."""
    sortiert = sorted(todos, key=lambda t: (not t.ueberfaellig, _kurzname(t)))
    namen: list[str] = []
    for t in sortiert:
        name = _kurzname(t)
        if name not in namen:
            namen.append(name)
        if len(namen) == max_anzahl:
            break
    weitere = max(0, len({_kurzname(t) for t in todos}) - len(namen))
    return namen, weitere


@router.get("/")
def root(request: Request):
    return redirect(request, "overview")


@router.get("/overview")
def overview(request: Request, db: Session = Depends(get_db)):
    heute = datetime.date.today()
    deals = (
        db.query(Deal)
        .options(
            joinedload(Deal.bank),
            joinedload(Deal.inhaber),
            joinedload(Deal.praemien),
            joinedload(Deal.bedingungen),
        )
        .all()
    )
    aufgaben = (
        db.query(Aufgabe)
        .options(
            joinedload(Aufgabe.deal).joinedload(Deal.bank),
            joinedload(Aufgabe.deal).joinedload(Deal.inhaber),
        )
        .all()
    )

    gesamt_kennzahlen = derived.kennzahlen([p for d in deals for p in d.praemien])

    alle_todos = derived.alle_todos(deals, aufgaben, heute)
    nach_kategorie: dict[str, list[derived.Todo]] = {}
    for t in alle_todos:
        nach_kategorie.setdefault(t.kategorie, []).append(t)

    # --- Jetzt dran: was der Nutzer heute anfassen muss ---
    aktionen: list[tuple[int, Aktion]] = []

    # Eine Prämie kann überfällig sein, ohne dass heute schon der nächste
    # Prüftermin ansteht - sie liegt dann in "Auf Prämie warten", ist aber
    # trotzdem eine Aufgabe (bei der Bank nachhaken). Genau diese Fälle
    # werden hier herausgezogen; der ruhige Rest bleibt unten unter "Läuft".
    wartende = nach_kategorie.get("Auf Prämie warten", [])
    ueberfaellige_praemien = [t for t in wartende if t.ueberfaellig]
    if ueberfaellige_praemien:
        beispiele, weitere = _beispiele(ueberfaellige_praemien)
        aktionen.append(
            (
                _RANG_UEBERFAELLIGE_PRAEMIE,
                Aktion(
                    schluessel="praemie_ueberfaellig",
                    titel="Prämie nicht gekommen",
                    anzahl=len(ueberfaellige_praemien),
                    url="todos?tab=praemie",
                    farbe="danger",
                    beispiele=beispiele,
                    weitere=weitere,
                    ueberfaellig=len(ueberfaellige_praemien),
                    hinweis="bei der Bank nachhaken",
                ),
            )
        )

    for kategorie, titel, url, farbe in AKTION_KATEGORIEN:
        todos = nach_kategorie.get(kategorie, [])
        if not todos:
            continue
        beispiele, weitere = _beispiele(todos)
        aktionen.append(
            (
                _RANG[kategorie],
                Aktion(
                    schluessel=kategorie,
                    titel=titel,
                    anzahl=len(todos),
                    url=url,
                    farbe=farbe,
                    beispiele=beispiele,
                    weitere=weitere,
                    ueberfaellig=sum(1 for t in todos if t.ueberfaellig),
                ),
            )
        )

    vorschlag_zaehler = vorschlaege_zaehlen(db)
    offene_vorschlaege = vorschlag_zaehler.vorgeschlagen + vorschlag_zaehler.zu_pruefen
    if offene_vorschlaege:
        teile = []
        if vorschlag_zaehler.vorgeschlagen:
            teile.append(f"{vorschlag_zaehler.vorgeschlagen} vorgeschlagen")
        if vorschlag_zaehler.zu_pruefen:
            teile.append(f"{vorschlag_zaehler.zu_pruefen} zu prüfen")
        aktionen.append(
            (
                _RANG_VORSCHLAEGE,
                Aktion(
                    schluessel="vorschlaege",
                    titel="Deal-Vorschläge entscheiden",
                    anzahl=offene_vorschlaege,
                    url="vorschlaege",
                    farbe="done",
                    beispiele=[" · ".join(teile)],
                ),
            )
        )

    # Überfälliges zuerst, danach die feste Reihenfolge oben. Innerhalb von
    # "überfällig" entscheidet die Menge.
    aktionen.sort(key=lambda paar: (0 if paar[1].ueberfaellig else 1, -paar[1].ueberfaellig, paar[0]))
    aktionsliste = [a for _, a in aktionen]

    aufgaben_gesamt = sum(a.anzahl for a in aktionsliste)
    ueberfaellig_gesamt = sum(a.ueberfaellig for a in aktionsliste)

    # --- Nebenbei: nützlich, aber nichts, was heute drängt ---
    pflege_todos = nach_kategorie.get("Deal pflegen", [])
    pflege_beispiele, pflege_weitere = _beispiele(pflege_todos)

    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "kennzahlen": gesamt_kennzahlen,
            "anzahl_deals": len(deals),
            "aktionen": aktionsliste,
            "aufgaben_gesamt": aufgaben_gesamt,
            "ueberfaellig_gesamt": ueberfaellig_gesamt,
            "anzahl_deal_pflegen": len(pflege_todos),
            "pflege_beispiele": pflege_beispiele,
            "pflege_weitere": pflege_weitere,
        },
    )
