from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..finder import matching
from ..finder.lauf import taeglicher_lauf
from ..helpers import build_deal_from_import
from ..ingress import redirect
from ..models import DealVorschlag, FinderLauf
from ..schemas import DealImport
from ..templating import templates

router = APIRouter()
logger = logging.getLogger("praemien_tracker.finder")

# Reihenfolge der Statusgruppen wie im Konzept-Mockup: erst eindeutig
# vorgeschlagene, dann zu prüfende, ganz unten (eingeklappt) die
# automatisch abgelehnten.
STATUS_OFFEN = matching.STATUS_OFFEN
_STATUS_PRIORITAET = {matching.STATUS_VORGESCHLAGEN: 0, matching.STATUS_ZU_PRUEFEN: 1, matching.STATUS_ABGELEHNT: 2}

QUELLEN = ("mydealz", "spartanien")
TYPEN = ("erwachsen", "kind")


@dataclass
class VorschlagGruppe:
    """Ein Fund (gleiche quelle_url + inhalt_hash), einmal angezeigt statt
    einmal je Inhaber. `mitglieder` enthält weiterhin eine Zeile je Inhaber,
    denn "Übernehmen" braucht die individuelle roh_json/Status pro Person -
    nur die Anzeige wird zusammengefasst (Konzept: gleicher Fund, mehrere
    mögliche Empfänger)."""

    quelle: str
    quelle_url: str
    bank_name: str
    kontoart: str
    praemie_betrag: object
    bedingungen: list
    status: str
    mitglieder: list[DealVorschlag]


def _gruppieren(vorschlaege: list[DealVorschlag]) -> list[VorschlagGruppe]:
    """Fasst Zeilen mit identischer quelle_url+inhalt_hash zusammen - das ist
    derselbe Fund für unterschiedliche Inhaber (siehe matching.bewerten: der
    Hash hängt nicht vom Inhaber ab). Der Gruppen-Status ist der beste
    Einzelstatus (vorgeschlagen vor zu_pruefen vor automatisch_abgelehnt) -
    ein für irgendjemanden echter Neukunden-Deal soll nicht in der
    abgelehnten Sektion untergehen, nur weil er für eine andere Person schon
    Bestandskunde ist."""
    nach_schluessel: dict[tuple[str, str], list[DealVorschlag]] = {}
    for v in vorschlaege:
        nach_schluessel.setdefault((v.quelle_url, v.inhalt_hash), []).append(v)

    gruppen = []
    for mitglieder in nach_schluessel.values():
        mitglieder = sorted(mitglieder, key=lambda v: v.gefunden_am, reverse=True)
        fuehrend = mitglieder[0]
        status = min((m.status for m in mitglieder), key=lambda s: _STATUS_PRIORITAET.get(s, 99))
        gruppen.append(
            VorschlagGruppe(
                quelle=fuehrend.quelle,
                quelle_url=fuehrend.quelle_url,
                bank_name=fuehrend.bank_name,
                kontoart=fuehrend.kontoart,
                praemie_betrag=fuehrend.praemie_betrag,
                bedingungen=fuehrend.bedingungen,
                status=status,
                mitglieder=mitglieder,
            )
        )
    gruppen.sort(key=lambda g: max(m.gefunden_am for m in g.mitglieder), reverse=True)
    return gruppen


@router.get("/vorschlaege")
def vorschlaege_view(
    request: Request,
    quelle: list[str] = Query(default=[]),
    typ: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    filter_quelle = [q for q in quelle if q in QUELLEN]
    filter_typ = [t for t in typ if t in TYPEN]
    filter_status = [s for s in status if s in STATUS_OFFEN]

    alle = (
        db.query(DealVorschlag)
        .options(joinedload(DealVorschlag.inhaber), joinedload(DealVorschlag.bedingungen))
        .filter(DealVorschlag.status.in_(STATUS_OFFEN))
        .order_by(DealVorschlag.gefunden_am.desc())
        .all()
    )

    if filter_quelle:
        alle = [v for v in alle if v.quelle in filter_quelle]
    if filter_typ:
        will_kind = "kind" in filter_typ
        will_erwachsen = "erwachsen" in filter_typ
        alle = [
            v
            for v in alle
            if (v.inhaber.ist_minderjaehrig and will_kind) or (not v.inhaber.ist_minderjaehrig and will_erwachsen)
        ]

    gruppen = _gruppieren(alle)
    if filter_status:
        gruppen = [g for g in gruppen if g.status in filter_status]

    eingeteilt: dict[str, list[VorschlagGruppe]] = {s: [] for s in STATUS_OFFEN}
    for g in gruppen:
        eingeteilt[g.status].append(g)

    letzter_lauf = db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()

    return templates.TemplateResponse(
        "vorschlaege.html",
        {
            "request": request,
            "vorgeschlagen": eingeteilt[matching.STATUS_VORGESCHLAGEN],
            "zu_pruefen": eingeteilt[matching.STATUS_ZU_PRUEFEN],
            "automatisch_abgelehnt": eingeteilt[matching.STATUS_ABGELEHNT],
            "letzter_lauf": letzter_lauf,
            "filter_quelle": filter_quelle,
            "filter_typ": filter_typ,
            "filter_status": filter_status,
            "filter_aktiv": bool(filter_quelle or filter_typ or filter_status),
        },
    )


@router.post("/vorschlaege/uebernehmen")
def uebernehmen(request: Request, vorschlag_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)):
    """Legt für jede ausgewählte Inhaber-Zeile einen eigenen Deal aus
    roh_json an - über denselben Mechanismus wie der händische JSON-Import
    (Konzept Abschnitt 7). Die Auswahl kommt aus den Checkboxen je Person in
    der Gruppen-Karte: ein Fund kann für mehrere Namen gleichzeitig
    übernommen werden. Auch aus "automatisch_abgelehnt" möglich, als
    bewusstes Überstimmen. Unbekannte oder bereits entschiedene IDs werden
    übergangen statt die ganze Anfrage abzubrechen."""
    for vorschlag_id in vorschlag_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is None or vorschlag.status not in STATUS_OFFEN:
            continue
        daten = DealImport.model_validate_json(vorschlag.roh_json)
        build_deal_from_import(db, daten)
        vorschlag.status = matching.STATUS_UEBERNOMMEN
    db.commit()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/verwerfen")
def verwerfen(request: Request, vorschlag_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)):
    """Setzt nur den Status der ausgewählten Zeilen, keine Löschung - taucht
    dank Dedup gegen den Inhalts-Hash nicht erneut auf, solange sich am Fund
    nichts ändert. Nicht ausgewählte Personen in derselben Gruppe bleiben
    offen."""
    for vorschlag_id in vorschlag_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is not None and vorschlag.status in STATUS_OFFEN:
            vorschlag.status = matching.STATUS_VERWORFEN
    db.commit()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/jetzt-suchen")
def jetzt_suchen(request: Request, db: Session = Depends(get_db)):
    """Manueller Anstoß des täglichen Laufs - nicht Teil des Konzepts, aber
    nötig, um Einrichtung und API-Key zu testen, ohne bis 06:00 Uhr zu warten.
    Fehler werden geloggt statt die Seite abstürzen zu lassen (z.B. fehlender
    oder ungültiger API-Key, Quelle nicht erreichbar)."""
    try:
        taeglicher_lauf(db)
    except Exception:
        logger.exception("Manueller KI-Deal-Finder-Lauf fehlgeschlagen.")
    return redirect(request, "vorschlaege")
