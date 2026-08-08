from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived
from ..config import DEMO_MODUS
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
# Zusätzlich zu den drei offenen Status lässt sich auch nach "verworfen"
# filtern (eigene Sektion, siehe vorschlaege_view) - fachlich kein "offener"
# Status mehr, aber über dieselbe Status-Filterleiste erreichbar.
STATUS_FILTERBAR = STATUS_OFFEN + (matching.STATUS_VERWORFEN,)

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
    sperrfrist_monate: object
    gefunden_am: object
    bedingungen: list
    praemien: list
    status: str
    verwerfen_gruende: object
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
                sperrfrist_monate=fuehrend.sperrfrist_monate,
                gefunden_am=max(m.gefunden_am for m in mitglieder),
                bedingungen=fuehrend.bedingungen,
                praemien=fuehrend.praemien,
                status=status,
                verwerfen_gruende=fuehrend.verwerfen_gruende,
                mitglieder=mitglieder,
            )
        )
    gruppen.sort(key=lambda g: max(m.gefunden_am for m in g.mitglieder), reverse=True)
    return gruppen


@dataclass
class DuplikatGruppe:
    """Mehrere VorschlagGruppen (=Funde) mit gleicher Bank+Kontoart, egal aus
    welcher/welchen Quelle(n) - vermutlich derselbe Deal, nur unabhängig
    voneinander gefunden (z.B. einmal auf mydealz, einmal auf spartanien,
    ggf. mit abweichender Prämienhöhe je nach Quelle). Anders als bei
    VorschlagGruppe bleibt jeder Fund ein eigener Datensatz mit eigenem
    roh_json - die Bündelung ist reine Anzeige- und Aktions-Hilfe, damit sich
    beim Übernehmen gezielt eine Version wählen und die übrigen als Duplikat
    verwerfen lassen (Konzept: Nutzerfrage "gleicher Deal von mydealz und
    spartanien - wie vergleichen und einen übernehmen?")."""

    bank_name: str
    kontoart: str
    status: str
    gefunden_am: object
    funde: list[VorschlagGruppe]


def _quellenuebergreifend_gruppieren(gruppen: list[VorschlagGruppe]) -> list[VorschlagGruppe | DuplikatGruppe]:
    """Bündelt VorschlagGruppen mit identischer Bank+Kontoart (normalisiert
    wie beim Bank-Abgleich) zu einer DuplikatGruppe. Die Prämienhöhe fließt
    bewusst nicht ins Kriterium ein, da sie sich je Quelle unterscheiden
    kann. Funktioniert unabhängig von der Anzahl beteiligter Quellen - ob 2
    oder 5 Fundstellen denselben Deal melden, macht keinen Unterschied.
    Einzelne, nicht betroffene Funde bleiben unverändert in der Liste."""
    nach_schluessel: dict[tuple[str, str], list[VorschlagGruppe]] = {}
    for g in gruppen:
        schluessel = (derived.bank_name_normalisieren(g.bank_name), g.kontoart.strip().lower())
        nach_schluessel.setdefault(schluessel, []).append(g)

    ergebnis: list[VorschlagGruppe | DuplikatGruppe] = []
    for mitglieder in nach_schluessel.values():
        if len(mitglieder) == 1:
            ergebnis.append(mitglieder[0])
            continue
        # Höchste Prämie zuerst (Vorauswahl) - bei Gleichstand der zuletzt gefundene Fund.
        mitglieder = sorted(mitglieder, key=lambda g: (g.praemie_betrag, g.gefunden_am), reverse=True)
        status = min((g.status for g in mitglieder), key=lambda s: _STATUS_PRIORITAET.get(s, 99))
        ergebnis.append(
            DuplikatGruppe(
                bank_name=mitglieder[0].bank_name,
                kontoart=mitglieder[0].kontoart,
                status=status,
                gefunden_am=max(g.gefunden_am for g in mitglieder),
                funde=mitglieder,
            )
        )
    ergebnis.sort(key=lambda item: item.gefunden_am, reverse=True)
    return ergebnis


def _nach_quelle_typ_filtern(
    vorschlaege: list[DealVorschlag], filter_quelle: list[str], filter_typ: list[str]
) -> list[DealVorschlag]:
    if filter_quelle:
        vorschlaege = [v for v in vorschlaege if v.quelle in filter_quelle]
    if filter_typ:
        will_kind = "kind" in filter_typ
        will_erwachsen = "erwachsen" in filter_typ
        vorschlaege = [
            v
            for v in vorschlaege
            if (v.inhaber.ist_minderjaehrig and will_kind) or (not v.inhaber.ist_minderjaehrig and will_erwachsen)
        ]
    return vorschlaege


@dataclass
class VorschlagZaehler:
    vorgeschlagen: int
    zu_pruefen: int
    abgelehnt: int
    verworfen: int


def zaehlen(db: Session) -> VorschlagZaehler:
    """Anzahl Vorschläge je Status, dedupliziert wie in der Ansicht (ein Fund
    für mehrere Inhaber zählt nur einmal, mehrere Quellen desselben Deals
    dank Duplikat-Bündelung ebenfalls) - unabhängig von Quelle-/Typ-Filtern,
    für die Kacheln auf der Übersicht."""
    lade_optionen = (joinedload(DealVorschlag.inhaber), joinedload(DealVorschlag.bedingungen), joinedload(DealVorschlag.praemien))

    offene = db.query(DealVorschlag).options(*lade_optionen).filter(DealVorschlag.status.in_(STATUS_OFFEN)).all()
    offene_anzeige = _quellenuebergreifend_gruppieren(_gruppieren(offene))

    verworfene = db.query(DealVorschlag).options(*lade_optionen).filter(DealVorschlag.status == matching.STATUS_VERWORFEN).all()
    verworfene_gruppen = _gruppieren(verworfene)

    return VorschlagZaehler(
        vorgeschlagen=sum(1 for g in offene_anzeige if g.status == matching.STATUS_VORGESCHLAGEN),
        zu_pruefen=sum(1 for g in offene_anzeige if g.status == matching.STATUS_ZU_PRUEFEN),
        abgelehnt=sum(1 for g in offene_anzeige if g.status == matching.STATUS_ABGELEHNT),
        verworfen=len(verworfene_gruppen),
    )


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
    filter_status = [s for s in status if s in STATUS_FILTERBAR]

    lade_optionen = (
        joinedload(DealVorschlag.inhaber),
        joinedload(DealVorschlag.bedingungen),
        joinedload(DealVorschlag.praemien),
    )

    alle = (
        db.query(DealVorschlag)
        .options(*lade_optionen)
        .filter(DealVorschlag.status.in_(STATUS_OFFEN))
        .order_by(DealVorschlag.gefunden_am.desc())
        .all()
    )
    alle = _nach_quelle_typ_filtern(alle, filter_quelle, filter_typ)
    alle_gruppen = _gruppieren(alle)

    # Manuell verworfene Vorschläge separat abgefragt: eigene Sektion am
    # Seitenende, mit den vom Nutzer ausgewählten Verwerfen-Gründen. Bleiben
    # bewusst eine eigene Gruppierung statt mit STATUS_OFFEN vermischt zu
    # werden - sonst würde ein für eine Person verworfener, für eine andere
    # noch offener Fund nicht mehr getrennt sichtbar.
    verworfene_rows = (
        db.query(DealVorschlag)
        .options(*lade_optionen)
        .filter(DealVorschlag.status == matching.STATUS_VERWORFEN)
        .order_by(DealVorschlag.gefunden_am.desc())
        .all()
    )
    verworfene_rows = _nach_quelle_typ_filtern(verworfene_rows, filter_quelle, filter_typ)
    verworfen_gruppen = _gruppieren(verworfene_rows)

    # Zähler je Status - berücksichtigen Quelle/Typ, aber bewusst nicht den
    # Status-Filter selbst: sonst würden sich die Chips beim Anklicken auf
    # 0 zurücksetzen, weil die anderen Status dann herausgefiltert sind.
    alle_anzeige = _quellenuebergreifend_gruppieren(alle_gruppen)
    anzahl_vorgeschlagen = sum(1 for g in alle_anzeige if g.status == matching.STATUS_VORGESCHLAGEN)
    anzahl_zu_pruefen = sum(1 for g in alle_anzeige if g.status == matching.STATUS_ZU_PRUEFEN)
    anzahl_abgelehnt = sum(1 for g in alle_anzeige if g.status == matching.STATUS_ABGELEHNT)
    anzahl_verworfen = len(verworfen_gruppen)

    gruppen = alle_gruppen
    if filter_status:
        gruppen = [g for g in gruppen if g.status in filter_status]
    verworfen = verworfen_gruppen
    if filter_status and matching.STATUS_VERWORFEN not in filter_status:
        verworfen = []

    eingeteilt: dict[str, list[VorschlagGruppe | DuplikatGruppe]] = {s: [] for s in STATUS_OFFEN}
    for g in _quellenuebergreifend_gruppieren(gruppen):
        eingeteilt[g.status].append(g)

    letzter_lauf = db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()

    return templates.TemplateResponse(
        "vorschlaege.html",
        {
            "request": request,
            "vorgeschlagen": eingeteilt[matching.STATUS_VORGESCHLAGEN],
            "zu_pruefen": eingeteilt[matching.STATUS_ZU_PRUEFEN],
            "automatisch_abgelehnt": eingeteilt[matching.STATUS_ABGELEHNT],
            "verworfen": verworfen,
            "anzahl_vorgeschlagen": anzahl_vorgeschlagen,
            "anzahl_zu_pruefen": anzahl_zu_pruefen,
            "anzahl_abgelehnt": anzahl_abgelehnt,
            "anzahl_verworfen": anzahl_verworfen,
            "verwerfen_gruende_optionen": matching.VERWERFEN_GRUENDE_LABELS,
            "letzter_lauf": letzter_lauf,
            "filter_quelle": filter_quelle,
            "filter_typ": filter_typ,
            "filter_status": filter_status,
            "filter_aktiv": bool(filter_quelle or filter_typ or filter_status),
        },
    )


@router.post("/vorschlaege/uebernehmen")
def uebernehmen(
    request: Request,
    vorschlag_ids: list[int] = Form(default=[]),
    verwerfen_duplikat_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    """Legt für jede ausgewählte Inhaber-Zeile einen eigenen Deal aus
    roh_json an - über denselben Mechanismus wie der händische JSON-Import
    (Konzept Abschnitt 7). Die Auswahl kommt aus den Checkboxen je Person in
    der Gruppen-Karte: ein Fund kann für mehrere Namen gleichzeitig
    übernommen werden. Auch aus "automatisch_abgelehnt" möglich, als
    bewusstes Überstimmen. Unbekannte oder bereits entschiedene IDs werden
    übergangen statt die ganze Anfrage abzubrechen.

    verwerfen_duplikat_ids kommt aus der Duplikat-Gruppe (siehe
    DuplikatGruppe/dup_gruppe_karte): wählt der Nutzer dort eine Quelle zum
    Übernehmen aus, werden die übrigen Quellen desselben Deals hier
    automatisch mit Grund "Duplikat" verworfen - kein zusätzlicher
    Bestätigungsschritt nötig."""
    for vorschlag_id in vorschlag_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is None or vorschlag.status not in STATUS_OFFEN:
            continue
        daten = DealImport.model_validate_json(vorschlag.roh_json)
        build_deal_from_import(db, daten)
        vorschlag.status = matching.STATUS_UEBERNOMMEN
    for vorschlag_id in verwerfen_duplikat_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is not None and vorschlag.status in STATUS_OFFEN:
            vorschlag.status = matching.STATUS_VERWORFEN
            vorschlag.verwerfen_gruende = matching.VERWERFEN_GRUND_DUPLIKAT
    db.commit()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/verwerfen")
def verwerfen(
    request: Request,
    vorschlag_ids: list[int] = Form(default=[]),
    gruende: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    """Setzt nur den Status der ausgewählten Zeilen, keine Löschung - taucht
    dank Dedup gegen den Inhalts-Hash nicht erneut auf, solange sich am Fund
    nichts ändert. Nicht ausgewählte Personen in derselben Gruppe bleiben
    offen.

    Ein manuelles Verwerfen braucht immer mindestens einen Grund aus dem
    festen Enum (Dialog erzwingt das clientseitig per Checkbox-Auswahl) -
    ohne gültigen Grund passiert serverseitig nichts, damit nie ein Vorschlag
    ohne Begründung verworfen werden kann."""
    gueltige_gruende = [g for g in gruende if g in matching.VERWERFEN_GRUENDE]
    if not gueltige_gruende:
        return redirect(request, "vorschlaege")
    gruende_text = ",".join(gueltige_gruende)

    for vorschlag_id in vorschlag_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is not None and vorschlag.status in STATUS_OFFEN:
            vorschlag.status = matching.STATUS_VERWORFEN
            vorschlag.verwerfen_gruende = gruende_text
    db.commit()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/jetzt-suchen")
def jetzt_suchen(request: Request, db: Session = Depends(get_db)):
    """Manueller Anstoß des täglichen Laufs - nicht Teil des Konzepts, aber
    nötig, um Einrichtung und API-Key zu testen, ohne bis 06:00 Uhr zu warten.
    Fehler werden geloggt statt die Seite abstürzen zu lassen (z.B. fehlender
    oder ungültiger API-Key, Quelle nicht erreichbar). Im Demo-Modus komplett
    gesperrt (auch serverseitig, nicht nur der ausgeblendete Button) - sonst
    könnte ein echter API-Key echte, kostenpflichtige Anfragen auslösen und
    echte Funde in die Demo-Daten mischen."""
    if not DEMO_MODUS:
        try:
            taeglicher_lauf(db)
        except Exception:
            logger.exception("Manueller KI-Deal-Finder-Lauf fehlgeschlagen.")
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/alle-neu-analysieren")
def alle_neu_analysieren(request: Request, db: Session = Depends(get_db)):
    """Erzwingt für jeden aktuell gelisteten Fund einen frischen API-Aufruf
    (Cache übersprungen) und aktualisiert bestehende, noch offene Vorschläge
    mit dem neuen Ergebnis - z.B. damit ältere Karten nachträglich eine
    Prämien-Aufschlüsselung bekommen, die es bei ihrer ersten Prüfung noch
    nicht gab. Der Bestätigungsdialog im Frontend macht auf die höheren
    API-Kosten aufmerksam, bevor diese Route überhaupt aufgerufen wird. Im
    Demo-Modus gesperrt, siehe jetzt_suchen()."""
    if not DEMO_MODUS:
        try:
            taeglicher_lauf(db, ignoriere_cache=True)
        except Exception:
            logger.exception("Erzwungene Neuanalyse (KI-Deal-Finder) fehlgeschlagen.")
    return redirect(request, "vorschlaege")
