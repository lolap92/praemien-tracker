from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session, joinedload

from .. import derived, helpers
from ..config import DEMO_MODUS, NOTIFY_GERAETE
from ..database import get_db
from ..finder import matching, notify
from ..finder.lauf import lauf_im_hintergrund_starten, lauf_status
from ..helpers import build_deal_from_import, parse_date, parse_decimal
from ..ingress import redirect
from ..models import DealVorschlag, FinderFund, FinderLauf
from ..schemas import AufgabeIn, BedingungIn, DealImport, PraemieIn, UrlIn
from ..templating import templates

router = APIRouter()

# Zusätzliche leere Zeilen, die uebernehmen_vorschau über die vorhandenen
# Einträge aus roh_json hinaus anbietet, um in der Vorschau noch etwas Neues
# hinzuzufügen (z.B. einen zweiten Link oder eine frei formulierte Aufgabe) -
# ohne eine dynamische "+ Zeile"-Schaltfläche zu brauchen. Leer gebliebene
# Zeilen werden von uebernehmen_bestaetigen beim Auswerten übersprungen.
_LEERZEILEN_PRAEMIEN = 2
_LEERZEILEN_BEDINGUNGEN = 2
_LEERZEILEN_URLS = 1
_LEERZEILEN_AUFGABEN = 3

# Reihenfolge der Statusgruppen wie im Konzept-Mockup: erst eindeutig
# vorgeschlagene, dann zu prüfende, ganz unten (eingeklappt) die
# automatisch abgelehnten.
STATUS_OFFEN = matching.STATUS_OFFEN
_STATUS_PRIORITAET = {matching.STATUS_VORGESCHLAGEN: 0, matching.STATUS_ZU_PRUEFEN: 1, matching.STATUS_ABGELEHNT: 2}
# Zusätzlich zu den drei offenen Status lässt sich auch nach "verworfen"
# filtern (eigene Sektion, siehe vorschlaege_view) - fachlich kein "offener"
# Status mehr, aber über dieselbe Status-Filterleiste erreichbar.
STATUS_FILTERBAR = STATUS_OFFEN + (matching.STATUS_VERWORFEN,)

QUELLEN = ("mydealz", "spartanien", "dealdoktor")
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
    ablehnungsgruende: object
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
        # Über alle Mitglieder vereinigt statt nur fuehrend.ablehnungsgruende:
        # die Sperrfrist-/Neukunden-Prüfung ist inhaberabhängig, zwei
        # Mitglieder derselben Gruppe können deshalb unterschiedliche Gründe
        # haben (z.B. für eine Person schon Sperrfrist, für die andere nicht).
        alle_gruende: list[str] = []
        for m in mitglieder:
            for grund in (m.ablehnungsgruende or "").split("; "):
                if grund and grund not in alle_gruende:
                    alle_gruende.append(grund)
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
                ablehnungsgruende=alle_gruende,
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


def _filter_ziel(quelle: list[str], typ: list[str], status: list[str]) -> str:
    """Baut das Redirect-Ziel "vorschlaege" mit den übergebenen Filtern als
    Query-Parametern - damit ein Verwerfen/Übernehmen aus einer gefilterten
    Ansicht heraus wieder in dieselbe gefilterte Ansicht zurückführt, statt
    die Filterleiste unbemerkt zurückzusetzen."""
    teile = [("quelle", q) for q in quelle if q in QUELLEN]
    teile += [("typ", t) for t in typ if t in TYPEN]
    teile += [("status", s) for s in status if s in STATUS_FILTERBAR]
    if not teile:
        return "vorschlaege"
    return "vorschlaege?" + "&".join(f"{k}={v}" for k, v in teile)


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

    # Bündelung passiert genau einmal, auf den ungefilterten Gruppen - ihr
    # Status ("bester" Status je Bündel, siehe _quellenuebergreifend_gruppieren)
    # muss für Badge-Zähler und Anzeige identisch sein. Vorher wurde bei
    # aktivem Status-Filter ein zweites Mal gebündelt, aber nur aus den schon
    # nach Status vorgefilterten Einzel-Funden - ein Deal, dessen Bündel-
    # Status dank einer besseren Fundstelle z.B. "vorgeschlagen" ist, konnte
    # dadurch beim Filtern auf "zu prüfen" als eigenständige Karte aus den
    # übrigen (schlechteren) Fundstellen wieder auftauchen, obwohl er laut
    # Zähler gar nicht als "zu prüfen" mitgezählt wurde (Bug: Chip zeigte 0,
    # Karte war trotzdem da).
    alle_anzeige = _quellenuebergreifend_gruppieren(alle_gruppen)
    anzahl_vorgeschlagen = sum(1 for g in alle_anzeige if g.status == matching.STATUS_VORGESCHLAGEN)
    anzahl_zu_pruefen = sum(1 for g in alle_anzeige if g.status == matching.STATUS_ZU_PRUEFEN)
    anzahl_abgelehnt = sum(1 for g in alle_anzeige if g.status == matching.STATUS_ABGELEHNT)
    anzahl_verworfen = len(verworfen_gruppen)

    anzeige = alle_anzeige
    if filter_status:
        anzeige = [g for g in anzeige if g.status in filter_status]
    verworfen = verworfen_gruppen
    if filter_status and matching.STATUS_VERWORFEN not in filter_status:
        verworfen = []

    eingeteilt: dict[str, list[VorschlagGruppe | DuplikatGruppe]] = {s: [] for s in STATUS_OFFEN}
    for g in anzeige:
        eingeteilt[g.status].append(g)

    letzter_lauf = db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()
    lauf_laeuft, lauf_gestartet_am = lauf_status()

    return templates.TemplateResponse(
        "vorschlaege.html",
        {
            "request": request,
            "lauf_laeuft": lauf_laeuft,
            "lauf_gestartet_am": lauf_gestartet_am,
            "test_benachrichtigung": request.query_params.get("test_benachrichtigung"),
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


def _zeilen_mit_leerzeilen(vorhandene: list[dict], leerzeile: dict, anzahl_leer: int) -> list[dict]:
    """Vorhandene Zeilen (aus roh_json) plus `anzahl_leer` leere Zeilen zum
    Ergänzen, ohne eine dynamische "+ Zeile"-Schaltfläche zu brauchen - siehe
    uebernehmen_vorschau. Jede Leerzeile ist ein eigenes dict, damit die
    Vorlage sie unabhängig voneinander befüllen kann."""
    return vorhandene + [dict(leerzeile) for _ in range(anzahl_leer)]


@router.post("/vorschlaege/uebernehmen")
def uebernehmen_vorschau(
    request: Request,
    vorschlag_ids: list[int] = Form(default=[]),
    verwerfen_duplikat_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    """Erster Schritt des Übernehmens: zeigt statt sofort einen Deal je
    ausgewähltem Inhaber anzulegen zunächst ein Bearbeitungsformular für die
    Felder, die für alle ausgewählten Inhaber identisch sind (derselbe Fund,
    siehe VorschlagGruppe/_gruppieren) - Kündbar ab, Kommentar sowie Prämien,
    Bedingungen, freie Aufgaben und Links als editierbare Zeilen (plus ein
    paar leere Zeilen zum Ergänzen, siehe _zeilen_mit_leerzeilen). Bank und
    Kontoart werden nur noch zur Orientierung angezeigt, nicht mehr bearbeitet
    - sie bestimmen u.a., ob ein Inhaber als Neukunde gilt, und sollen daher
    unverändert aus der KI-Extraktion stammen. Erst das Absenden dieses
    Formulars (uebernehmen_bestaetigen) legt die Deals wirklich an.

    Die Auswahl kommt aus den Checkboxen je Person in der Gruppen-Karte, auch
    aus "automatisch_abgelehnt" möglich (bewusstes Überstimmen). Unbekannte
    oder bereits entschiedene IDs werden hier wie beim späteren Anlegen
    übergangen; bleibt dadurch keine gültige Auswahl übrig, geht es ohne
    Vorschau direkt zurück zur Übersicht.

    Stößt die Kunden-wirbt-Kunden- und die Kündigungsweg-Recherche für
    Bank+Kontoart schon jetzt im Hintergrund an (helpers.
    kwk_recherche_vorab_starten/kuendigung_hinweis_vorab_starten) - die Zeit,
    die der Nutzer mit der Vorschau verbringt, überbrückt beide KI-Websuchen,
    ohne "Übernehmen" wie früher spürbar zu blockieren (siehe
    uebernehmen_bestaetigen)."""
    gueltig = [v for v in (db.get(DealVorschlag, vid) for vid in vorschlag_ids) if v is not None and v.status in STATUS_OFFEN]
    if not gueltig:
        return redirect(request, "vorschlaege")

    fuehrend = gueltig[0]
    daten = DealImport.model_validate_json(fuehrend.roh_json)
    kwk_schluessel = helpers.kwk_recherche_vorab_starten(daten.bank, daten.kontoart)
    kuendigung_schluessel = helpers.kuendigung_hinweis_vorab_starten(daten.bank, daten.kontoart)

    praemien_zeilen = _zeilen_mit_leerzeilen(
        [
            {"quelle": p.quelle, "betrag": str(p.betrag), "auszahlung_erwartet": p.auszahlung_erwartet or "", "erhalten": p.erhalten}
            for p in daten.praemien
        ],
        {"quelle": "bank", "betrag": "", "auszahlung_erwartet": "", "erhalten": False},
        _LEERZEILEN_PRAEMIEN,
    )
    bedingungen_zeilen = _zeilen_mit_leerzeilen(
        [{"beschreibung": b.beschreibung, "faellig_bis": b.faellig_bis.isoformat() if b.faellig_bis else ""} for b in daten.bedingungen],
        {"beschreibung": "", "faellig_bis": ""},
        _LEERZEILEN_BEDINGUNGEN,
    )
    url_zeilen = _zeilen_mit_leerzeilen(
        [{"bezeichnung": u.bezeichnung or "", "url": u.url} for u in daten.urls],
        {"bezeichnung": "", "url": ""},
        _LEERZEILEN_URLS,
    )
    aufgaben_zeilen = _zeilen_mit_leerzeilen(
        [{"beschreibung": a.beschreibung, "faellig_bis": a.faellig_bis.isoformat() if a.faellig_bis else ""} for a in daten.aufgaben],
        {"beschreibung": "", "faellig_bis": ""},
        _LEERZEILEN_AUFGABEN,
    )

    return templates.TemplateResponse(
        "vorschlag_uebernehmen.html",
        {
            "request": request,
            "bank": daten.bank,
            "kontoart": daten.kontoart,
            "kuendbar_ab": daten.kuendbar_ab.isoformat() if daten.kuendbar_ab else "",
            "kommentar": daten.kommentar or "",
            "praemien_zeilen": praemien_zeilen,
            "bedingungen_zeilen": bedingungen_zeilen,
            "url_zeilen": url_zeilen,
            "aufgaben_zeilen": aufgaben_zeilen,
            "mitglieder": gueltig,
            "verwerfen_duplikat_ids": verwerfen_duplikat_ids,
            "kwk_schluessel": kwk_schluessel,
            "kuendigung_schluessel": kuendigung_schluessel,
        },
    )


def _form_zeilen(form, prefix: str, anzahl_feld: str, felder: tuple[str, ...]) -> list[dict[str, str | None]]:
    """Liest die von uebernehmen_vorschau als `{prefix}_{index}_{feld}`
    benannten Formularfelder wieder ein - so bekommt jede Checkbox (z.B.
    "erhalten") einen eindeutigen Namen und es entsteht nicht das klassische
    Problem nicht angehakter Checkboxen, die in einem gemeinsamen Array-Namen
    einfach fehlen würden und die Zuordnung zu ihrer Zeile verschieben. Ein
    Bool-Feld wird an seinem Namen ohne "_wert"-Suffix erkannt (siehe
    Aufrufer) und ist True, wenn der Schlüssel überhaupt vorhanden ist."""
    zeilen = []
    for i in range(int(form.get(anzahl_feld, "0") or "0")):
        zeilen.append({feld: form.get(f"{prefix}_{i}_{feld}") for feld in felder})
    return zeilen


def _rest_vom_budget(deadline: float) -> float:
    """Verbleibende Sekunden bis `deadline` (nie negativ) - siehe
    uebernehmen_bestaetigen: mehrere Recherchen teilen sich ein gemeinsames
    Zeitbudget, statt dass sich ihre einzelnen Timeouts aufsummieren."""
    return max(0.0, deadline - time.monotonic())


@router.post("/vorschlaege/uebernehmen/bestaetigen")
async def uebernehmen_bestaetigen(request: Request, db: Session = Depends(get_db)):
    """Zweiter Schritt: legt jetzt tatsächlich für jede ausgewählte
    Inhaber-Zeile einen eigenen Deal aus roh_json an - über denselben
    Mechanismus wie der händische JSON-Import (Konzept Abschnitt 7). Kündbar
    ab, Kommentar sowie die Prämien-/Bedingungen-/Aufgaben-/Link-Zeilen kommen
    aus dem in uebernehmen_vorschau editierbaren Formular und überschreiben
    die aus roh_json; Bank, Kontoart und Inhaber bleiben unverändert (siehe
    dort). Unbekannte oder bereits entschiedene IDs (z.B. durch einen
    parallel offenen zweiten Tab schon entschieden) werden übergangen statt
    die ganze Anfrage abzubrechen.

    Liest die Formulardaten bewusst manuell über request.form() statt über
    typisierte Form(...)-Parameter, weil die Anzahl der Prämien-/Bedingungen-/
    Aufgaben-/Link-Zeilen von Vorschlag zu Vorschlag unterschiedlich ist
    (siehe _form_zeilen/uebernehmen_vorschau).

    verwerfen_duplikat_ids kommt aus der Duplikat-Gruppe (siehe
    DuplikatGruppe/dup_gruppe_karte): wählt der Nutzer dort eine Quelle zum
    Übernehmen aus, werden die übrigen Quellen desselben Deals hier
    automatisch mit Grund "Duplikat" verworfen - kein zusätzlicher
    Bestätigungsschritt nötig.

    Die KwK- und die Kündigungsweg-Recherche wurden schon beim Öffnen der
    Vorschau einmal im Hintergrund für Bank+Kontoart gestartet
    (uebernehmen_vorschau) und gelten für alle hier angelegten Deals
    gleichermaßen - hier wird höchstens noch kurz auf die Ergebnisse gewartet
    (helpers.kwk_recherche_ergebnis_abholen/kuendigung_hinweis_ergebnis_abholen).
    HINTERGRUND_RECHERCHE_TIMEOUT_SEKUNDEN gilt dabei als gemeinsames Budget
    für beide Wartezeiten zusammen (siehe _hintergrund_ergebnis_abholen),
    nicht als Timeout je Recherche - sonst könnten sich zwei Wartezeiten
    aufsummieren und "Übernehmen" trotzdem spürbar hängen. Liegt ein Ergebnis
    dann immer noch nicht vor oder ist die KwK-Recherche fehlgeschlagen,
    bekommt jeder neue Deal stattdessen eine einfache Erinnerungs-Aufgabe
    (helpers.kwk_ergebnis_anwenden); beim Kündigungsweg bleibt das Feld in
    diesem Fall einfach leer (helpers.kuendigung_ergebnis_anwenden)."""
    form = await request.form()
    vorschlag_ids = [int(v) for v in form.getlist("vorschlag_ids")]
    verwerfen_duplikat_ids = [int(v) for v in form.getlist("verwerfen_duplikat_ids")]
    kwk_schluessel = form.get("kwk_schluessel", "")
    kuendigung_schluessel = form.get("kuendigung_schluessel", "")
    kuendbar_ab = parse_date((form.get("kuendbar_ab") or "").strip() or None)
    kommentar = (form.get("kommentar") or "").strip() or None

    praemien: list[PraemieIn] = []
    for zeile in _form_zeilen(form, "praemie", "praemien_anzahl", ("quelle", "betrag", "auszahlung_erwartet", "erhalten")):
        betrag = parse_decimal(zeile["betrag"])
        if betrag is None:
            continue
        praemien.append(
            PraemieIn(
                quelle=zeile["quelle"] or "bank",
                betrag=betrag,
                erhalten=zeile["erhalten"] is not None,
                auszahlung_erwartet=(zeile["auszahlung_erwartet"] or "").strip() or None,
            )
        )

    bedingungen: list[BedingungIn] = []
    for zeile in _form_zeilen(form, "bedingung", "bedingungen_anzahl", ("beschreibung", "faellig_bis")):
        beschreibung = (zeile["beschreibung"] or "").strip()
        if not beschreibung:
            continue
        bedingungen.append(BedingungIn(beschreibung=beschreibung, erfuellt=False, faellig_bis=parse_date(zeile["faellig_bis"])))

    urls: list[UrlIn] = []
    for zeile in _form_zeilen(form, "url", "urls_anzahl", ("bezeichnung", "url")):
        url = (zeile["url"] or "").strip()
        if not url:
            continue
        urls.append(UrlIn(url=url, bezeichnung=(zeile["bezeichnung"] or "").strip() or None))

    aufgaben: list[AufgabeIn] = []
    for zeile in _form_zeilen(form, "aufgabe", "aufgaben_anzahl", ("beschreibung", "faellig_bis")):
        beschreibung = (zeile["beschreibung"] or "").strip()
        if not beschreibung:
            continue
        aufgaben.append(AufgabeIn(beschreibung=beschreibung, erledigt=False, faellig_bis=parse_date(zeile["faellig_bis"])))

    deadline = time.monotonic() + helpers.HINTERGRUND_RECHERCHE_TIMEOUT_SEKUNDEN
    kwk_ergebnis = helpers.kwk_recherche_ergebnis_abholen(kwk_schluessel, timeout=_rest_vom_budget(deadline))
    kuendigung_ergebnis = helpers.kuendigung_hinweis_ergebnis_abholen(kuendigung_schluessel, timeout=_rest_vom_budget(deadline))

    for vorschlag_id in vorschlag_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is None or vorschlag.status not in STATUS_OFFEN:
            continue
        daten = DealImport.model_validate_json(vorschlag.roh_json)
        daten.kuendbar_ab = kuendbar_ab
        daten.kommentar = kommentar
        daten.praemien = praemien
        daten.bedingungen = bedingungen
        daten.urls = urls
        daten.aufgaben = aufgaben
        deal = build_deal_from_import(db, daten, hintergrund_recherche=True)
        helpers.kwk_ergebnis_anwenden(deal, kwk_ergebnis)
        helpers.kuendigung_ergebnis_anwenden(deal, kuendigung_ergebnis)
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
    quelle: list[str] = Form(default=[]),
    typ: list[str] = Form(default=[]),
    status: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    """Setzt nur den Status der ausgewählten Zeilen, keine Löschung - taucht
    dank Dedup gegen den Inhalts-Hash nicht erneut auf, solange sich am Fund
    nichts ändert. Nicht ausgewählte Personen in derselben Gruppe bleiben
    offen.

    Ein manuelles Verwerfen braucht immer mindestens einen Grund aus dem
    festen Enum (Dialog erzwingt das clientseitig per Checkbox-Auswahl) -
    ohne gültigen Grund passiert serverseitig nichts, damit nie ein Vorschlag
    ohne Begründung verworfen werden kann.

    quelle/typ/status kommen als versteckte Formularfelder aus der zum
    Zeitpunkt des Verwerfens aktiven Filterleiste (siehe vorschlaege.html) -
    der Redirect führt damit in dieselbe gefilterte Ansicht zurück, statt sie
    unbemerkt zurückzusetzen."""
    ziel = _filter_ziel(quelle, typ, status)
    gueltige_gruende = [g for g in gruende if g in matching.VERWERFEN_GRUENDE]
    if not gueltige_gruende:
        return redirect(request, ziel)

    gruende_text = ",".join(gueltige_gruende)
    for vorschlag_id in vorschlag_ids:
        vorschlag = db.get(DealVorschlag, vorschlag_id)
        if vorschlag is not None and vorschlag.status in STATUS_OFFEN:
            vorschlag.status = matching.STATUS_VERWORFEN
            vorschlag.verwerfen_gruende = gruende_text
    db.commit()
    return redirect(request, ziel)


@router.post("/vorschlaege/jetzt-suchen")
def jetzt_suchen(request: Request, db: Session = Depends(get_db)):
    """Manueller Anstoß des täglichen Laufs - nicht Teil des Konzepts, aber
    nötig, um Einrichtung und API-Key zu testen, ohne bis 06:00 Uhr zu warten.

    Läuft im Hintergrund (siehe lauf_im_hintergrund_starten) statt den
    Request zu blockieren, bis alle Funde geprüft sind - das konnte je nach
    Anzahl spürbar dauern, ohne dass währenddessen irgendein Feedback sichtbar
    war. Die Seite zeigt stattdessen sofort "Suche läuft" und lädt automatisch
    neu, sobald der Lauf fertig ist (siehe vorschlaege_view/lauf_status).
    Läuft schon ein anderer Lauf (Button oder 06:00-Job), passiert einfach
    nichts - kein zweiter parallel. Im Demo-Modus komplett gesperrt (auch
    serverseitig, nicht nur der ausgeblendete Button) - sonst könnte ein
    echter API-Key echte, kostenpflichtige Anfragen auslösen und echte Funde
    in die Demo-Daten mischen."""
    if not DEMO_MODUS:
        lauf_im_hintergrund_starten()
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/test-benachrichtigung")
def test_benachrichtigung(request: Request):
    """Sendet sofort eine Testnachricht an die konfigurierten Geräte -
    unabhängig vom Ein/Aus-Schalter für den täglichen Lauf (sonst ließe sich
    bei deaktiviertem Schalter nichts testen) und ohne dass dafür neue
    Vorschläge gefunden werden müssen. Beantwortet die Frage "Funktioniert
    die Benachrichtigung?", ohne bis zum nächsten echten Fund oder 06:00 Uhr
    zu warten. Das Ergebnis (angekommen oder nicht) wird als Query-Parameter
    zurückgegeben und auf der Seite angezeigt (siehe vorschlaege_view)."""
    erfolgreich = notify.benachrichtigen(
        0,
        0,
        aktiv=True,
        geraete=NOTIFY_GERAETE,
        nachricht="Prämien-Tracker: Test-Benachrichtigung",
    )
    status = "ok" if erfolgreich else "fehler"
    return redirect(request, f"vorschlaege?test_benachrichtigung={status}")


@router.post("/vorschlaege/alle-neu-analysieren")
def alle_neu_analysieren(request: Request, db: Session = Depends(get_db)):
    """Erzwingt für jeden aktuell gelisteten Fund einen frischen API-Aufruf
    (Cache übersprungen) und aktualisiert bestehende, noch offene Vorschläge
    mit dem neuen Ergebnis - z.B. damit ältere Karten nachträglich eine
    Prämien-Aufschlüsselung bekommen, die es bei ihrer ersten Prüfung noch
    nicht gab. Der Bestätigungsdialog im Frontend macht auf die höheren
    API-Kosten aufmerksam, bevor diese Route überhaupt aufgerufen wird. Läuft
    wie jetzt_suchen() im Hintergrund, siehe dort. Im Demo-Modus gesperrt,
    siehe jetzt_suchen()."""
    if not DEMO_MODUS:
        lauf_im_hintergrund_starten(ignoriere_cache=True)
    return redirect(request, "vorschlaege")


@router.post("/vorschlaege/zuruecksetzen")
def zuruecksetzen(request: Request, db: Session = Depends(get_db)):
    """Löscht unwiderruflich alle noch nicht übernommenen Vorschläge - egal
    ob vorgeschlagen, zu_pruefen, automatisch_abgelehnt oder manuell
    verworfen (status != STATUS_UEBERNOMMEN deckt alle vier ab) - sowie den
    Rohtext-Cache (finder_funde). Löst selbst *keinen* neuen Lauf aus (kein
    Aufruf von taeglicher_lauf) - reine Aufräum-Aktion, z.B. nach einer
    Häufung von Duplikaten, damit der nächste manuell angestoßene "Jetzt
    suchen" komplett frisch beginnt statt (noch) fehlerhaft
    zwischengespeicherte Extraktionen weiterzuverwenden.

    Bereits übernommene Vorschläge bleiben ausdrücklich erhalten: sie sind
    längst ein echter Deal-Datensatz, und ohne ihre Vorschlags-Zeile würde
    ein künftiger Lauf denselben Deal fälschlich erneut vorschlagen (siehe
    lauf.py: die Dedup-Prüfung erkennt "schon bearbeitet" an der Existenz
    dieser Zeile, unabhängig vom Status)."""
    for vorschlag in db.query(DealVorschlag).filter(DealVorschlag.status != matching.STATUS_UEBERNOMMEN).all():
        db.delete(vorschlag)
    db.query(FinderFund).delete()
    db.commit()
    return redirect(request, "vorschlaege")
