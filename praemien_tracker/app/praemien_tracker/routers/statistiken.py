from __future__ import annotations

import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..database import get_db
from ..models import Aufgabe, Deal, Inhaber
from ..templating import templates
from .vorschlaege import zaehlen as vorschlaege_zaehlen

router = APIRouter()

# Die Zählungen, die früher als Kachelreihen auf der Startseite standen.
# Sie sind dort weg, weil eine Zahl nicht sagt, ob etwas zu tun ist (siehe
# routers/overview.py) - verloren gehen sollen sie deshalb aber nicht: hier
# ist ihr Platz, wo man Zahlen auch sucht.
# (ToDo-Kategorie, Anzeigename, Ziel). Der Anzeigename steht daneben, weil
# die Startseite "Deals pflegen" schreibt - die Kategorie selbst heißt seit je
# "Deal pflegen" und ist der Schlüssel in derived.alle_todos.
QUERLIEGENDE_KATEGORIEN = [
    ("Manuelle Aufgaben", "Manuelle Aufgaben", "todos?tab=manuell"),
    ("Deal pflegen", "Deals pflegen", "todos?tab=pflegen"),
    ("Zu prüfen", "Zu prüfen", "todos?tab=pruefen"),
]

# Ziel je Pipeline-Status. Was ein Nutzer erledigen kann, führt in die
# ToDo-Liste; reine Wartezustände in die gefilterte Deals-Liste.
STATUS_ZIELE = {
    derived.STATUS_BEDINGUNGEN: "todos?tab=bedingungen",
    derived.STATUS_PRAEMIE_WARTEN: "todos?tab=praemie",
    derived.STATUS_PRAEMIE_PRUEFEN: "todos?tab=praemie_pruefen",
    derived.STATUS_WARTET_AUF_KUENDIGUNG: "deals?status=wartet_auf_kuendigung",
    derived.STATUS_KUENDIGEN: "todos?tab=kuendigen",
    derived.STATUS_BESTAETIGUNG_WARTEN: "todos?tab=bestaetigung",
    derived.STATUS_ABGESCHLOSSEN: "deals?status=abgeschlossen",
}


@router.get("/statistiken")
def statistiken(request: Request, db: Session = Depends(get_db)):
    heute = datetime.date.today()
    deals = (
        db.query(Deal)
        .options(
            joinedload(Deal.inhaber),
            joinedload(Deal.bank),
            joinedload(Deal.praemien),
            joinedload(Deal.bedingungen),
        )
        .all()
    )
    aufgaben = (
        db.query(Aufgabe)
        .options(joinedload(Aufgabe.deal).joinedload(Deal.bank))
        .all()
    )

    jahr_heute = heute.year
    vorjahr = jahr_heute - 1

    def freibetrag_summe(deals_inh, jahr):
        """Alle Deals des Jahres zählen mit, auch gekündigte und
        abgeschlossene: Ein Freistellungsauftrag ist im Jahr seiner Erteilung
        verbraucht, unabhängig davon, ob das Konto inzwischen zu ist."""
        return sum(
            (d.freibetrag for d in deals_inh if d.freibetrag is not None and d.freibetrag_jahr == jahr),
            Decimal("0"),
        )

    pro_inhaber = []
    for inh in db.query(Inhaber).order_by(Inhaber.name).all():
        deals_inh = [d for d in deals if d.inhaber_id == inh.id]
        kz = derived.kennzahlen([p for d in deals_inh for p in d.praemien])
        pro_inhaber.append(
            {
                "inhaber": inh,
                "kennzahlen": kz,
                "anzahl_deals": len(deals_inh),
                "freibetrag_jahr": freibetrag_summe(deals_inh, jahr_heute),
                "freibetrag_vorjahr": freibetrag_summe(deals_inh, vorjahr),
            }
        )

    nach_status: dict[str, list[Deal]] = {s: [] for s in derived.STATUS_ORDER}
    for d in deals:
        nach_status[derived.status(d, heute)].append(d)

    pipeline = []
    for s in derived.STATUS_ORDER:
        stufen_deals = nach_status[s]
        # Beim reinen Wartezustand ist das früheste Kündigungsdatum die
        # eigentliche Information - die Zahl allein sagt nur, dass man wartet.
        daten = [d.kuendbar_ab for d in stufen_deals if d.kuendbar_ab]
        zusatz = ""
        if s == derived.STATUS_WARTET_AUF_KUENDIGUNG and daten:
            zusatz = f"ab {min(daten).strftime('%d.%m.%Y')}"
        pipeline.append(
            {
                "status": s,
                "label": derived.STATUS_LABELS[s],
                "anzahl": len(stufen_deals),
                "url": STATUS_ZIELE[s],
                "zusatz": zusatz,
            }
        )

    alle_todos = derived.alle_todos(deals, aufgaben, heute)
    querliegend = [
        {
            "label": label,
            "anzahl": sum(1 for t in alle_todos if t.kategorie == kategorie),
            "url": url,
        }
        for kategorie, label, url in QUERLIEGENDE_KATEGORIEN
    ]

    zaehler = vorschlaege_zaehlen(db)
    vorschlaege = [
        {"label": "Vorgeschlagen", "anzahl": zaehler.vorgeschlagen, "chip": "vorgeschlagen", "url": "vorschlaege?status=vorgeschlagen"},
        {"label": "Zu prüfen", "anzahl": zaehler.zu_pruefen, "chip": "zu_pruefen", "url": "vorschlaege?status=zu_pruefen"},
        {"label": "Abgelehnt", "anzahl": zaehler.abgelehnt, "chip": "automatisch_abgelehnt", "url": "vorschlaege?status=automatisch_abgelehnt"},
        {"label": "Verworfen", "anzahl": zaehler.verworfen, "chip": "verworfen", "url": "vorschlaege?status=verworfen"},
    ]

    return templates.TemplateResponse(
        "statistiken.html",
        {
            "request": request,
            "pro_inhaber": pro_inhaber,
            "jahr_heute": jahr_heute,
            "vorjahr": vorjahr,
            "kennzahlen": derived.kennzahlen([p for d in deals for p in d.praemien]),
            "anzahl_deals": len(deals),
            "pipeline": pipeline,
            "querliegend": querliegend,
            "vorschlaege": vorschlaege,
        },
    )
