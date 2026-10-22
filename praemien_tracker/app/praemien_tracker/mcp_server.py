"""MCP-Server: Claude (z. B. Claude Code im Heimnetz) liest den Prämien-Tracker.

Ausschließlich lesend - kein Werkzeug ändert etwas an der Datenbank. Läuft
auf einem eigenen Port (MCP_PORT, Standard 8001) neben der eigentlichen
Oberfläche, weil die nur über den Home-Assistant-Ingress mit HA-Anmeldung
erreichbar ist, an der sich ein MCP-Client nicht anmelden kann. Der Port ist
im Add-on standardmäßig nicht nach außen freigegeben (config.yaml: ports
null) und der Server startet nur mit gesetztem Schlüssel (Option
"mcp_token"); jede Anfrage muss ihn als "Authorization: Bearer <token>"
mitschicken.

Status, ToDos, Sperrfristen und Kennzahlen kommen aus denselben Funktionen
wie die Oberfläche (derived.py) - Claude sieht also dasselbe wie die Seiten,
ohne dass hier eine zweite Fachlogik entsteht.

Bewusst NICHT herausgegeben werden persönliche Daten, die für die Arbeit an
den Prämien nicht nötig sind: Kontonummern (nur "hinterlegt ja/nein"),
Anschrift, Geburtsdatum, E-Mail und IBAN der Inhaber, der Text gespeicherter
Kündigungsschreiben (enthält die IBAN) sowie die entsprechenden Werte im
Änderungsprotokoll.
"""

# Bewusst ohne "from __future__ import annotations": FastMCP baut die
# Eingabeschemas der Werkzeuge aus den echten Typangaben.
import contextlib
import datetime
import hmac
import logging
from decimal import Decimal
from typing import Any, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session, joinedload
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import derived
from .database import SessionLocal
from .finder import matching
from .kuendigung_hinweise import hinweis_fuer
from .models import (
    Aufgabe,
    Deal,
    DealVorschlag,
    FinderLauf,
    Inhaber,
    KuendigungAnforderung,
    KuendigungFormular,
    KuendigungRecherche,
    ProtokollEintrag,
)

logger = logging.getLogger("praemien_tracker.mcp")

# Unter dieser Länge startet der Server nicht - ein kurzer Schlüssel ist im
# Heimnetz schnell erraten.
MINDESTLAENGE_TOKEN = 16

# Felder, deren Werte im Änderungsprotokoll nicht an Claude gehen - nur, dass
# sie geändert wurden.
_VERDECKTE_PROTOKOLLFELDER = {"kontonummer", "iban", "voller_name", "strasse", "plz", "ort", "geburtsdatum", "email"}

_NUR_LESEN = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

ANWEISUNGEN = """\
Lesezugriff auf den Prämien-Tracker: Bank-Prämien-Deals (Neukunden-Prämien für \
Girokonto, Depot, Tagesgeld, Kreditkarte), Konten ohne Prämie, die nur bis zur \
Kündigung mitverfolgt werden, abgeleitete ToDos, Sperrfristen, Statistiken, \
Vorschläge des KI-Deal-Finders und das Änderungsprotokoll. Beträge in Euro. \
Einstieg: uebersicht(), dann deals_suchen()/deal_details() oder todos(). \
Nur lesend - Änderungen macht die Nutzerin/der Nutzer in der App."""


# --- Hilfen ---------------------------------------------------------------


def _wert(x: Any) -> Any:
    """JSON-taugliche Werte: Decimal als float, Datum als ISO-Text."""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (datetime.date, datetime.datetime)):
        return x.isoformat()
    return x


def _kennzahlen(praemien) -> dict:
    kz = derived.kennzahlen(praemien)
    return {"gesamt": _wert(kz.gesamt), "erhalten": _wert(kz.erhalten), "offen": _wert(kz.offen)}


def _bezeichnung(deal: Deal) -> str:
    return f"{deal.bank.name} · {deal.kontoart} · {deal.inhaber.name}"


def _deal_query(db: Session):
    return db.query(Deal).options(
        joinedload(Deal.bank),
        joinedload(Deal.inhaber),
        joinedload(Deal.praemien),
        joinedload(Deal.bedingungen),
        joinedload(Deal.aufgaben),
        joinedload(Deal.urls),
    )


def _deal_kurz(deal: Deal, heute: datetime.date) -> dict:
    status = derived.status(deal, heute)
    return {
        "id": deal.id,
        "bezeichnung": _bezeichnung(deal),
        "bank": deal.bank.name,
        "kontoart": deal.kontoart,
        "inhaber": deal.inhaber.name,
        "art": "Konto ohne Prämie" if deal.ist_konto else "Deal",
        "status": derived.STATUS_LABELS[status],
        "status_code": status,
        "praemien": _kennzahlen(deal.praemien),
        "kuendbar_ab": _wert(deal.kuendbar_ab),
        "gekuendigt": deal.gekuendigt,
        "gekuendigt_im_monat": deal.gekuendigt_im_monat,
        "kuendigung_bestaetigt": deal.kuendigung_bestaetigt,
        "kontofuehrungsgebuehren_monatlich": _wert(deal.kontofuehrungsgebuehren),
    }


def _todo(t: derived.Todo) -> dict:
    return {
        "kategorie": t.kategorie,
        "text": t.text,
        "deal_id": t.deal.id if t.deal else None,
        "faellig_bis": _wert(t.faellig_bis),
        "ueberfaellig": t.ueberfaellig,
        "erst_spaeter_faellig": t.zukuenftig,
    }


def _alle_todos(db: Session, heute: datetime.date) -> list[derived.Todo]:
    deals = _deal_query(db).all()
    aufgaben = (
        db.query(Aufgabe)
        .options(joinedload(Aufgabe.deal).joinedload(Deal.bank), joinedload(Aufgabe.deal).joinedload(Deal.inhaber))
        .all()
    )
    return derived.alle_todos(deals, aufgaben, heute)


def _in_sitzung(funktion, *args):
    with SessionLocal() as db:
        return funktion(db, *args)


# --- Abfragen (synchron, je eine eigene DB-Sitzung) ------------------------


def uebersicht_abfragen(db: Session) -> dict:
    heute = datetime.date.today()
    deals = _deal_query(db).all()
    todos = [t for t in _alle_todos(db, heute) if not t.zukuenftig]
    je_status: dict[str, int] = {}
    for d in deals:
        label = derived.STATUS_LABELS[derived.status(d, heute)]
        je_status[label] = je_status.get(label, 0) + 1
    je_kategorie: dict[str, dict] = {}
    for t in todos:
        eintrag = je_kategorie.setdefault(t.kategorie, {"anzahl": 0, "ueberfaellig": 0})
        eintrag["anzahl"] += 1
        eintrag["ueberfaellig"] += int(t.ueberfaellig)
    vorschlaege: dict[str, int] = {}
    for (status,) in db.query(DealVorschlag.status).all():
        vorschlaege[status] = vorschlaege.get(status, 0) + 1
    letzter_lauf = db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()
    return {
        "stand": heute.isoformat(),
        "praemien_gesamt": _kennzahlen([p for d in deals for p in d.praemien]),
        "anzahl_deals": sum(1 for d in deals if not d.ist_konto),
        "anzahl_konten_ohne_praemie": sum(1 for d in deals if d.ist_konto),
        "je_status": je_status,
        "offene_todos_je_kategorie": je_kategorie,
        "vorschlaege_je_status": vorschlaege,
        "letzter_finder_lauf": _lauf(letzter_lauf) if letzter_lauf else None,
    }


def deals_suchen_abfragen(
    db: Session, status: list[str] | None, inhaber: str | None, art: str | None, bank: str | None
) -> dict:
    heute = datetime.date.today()
    status_codes = {s for s in (status or []) if s in derived.STATUS_INDEX}
    status_codes |= {code for code, label in derived.STATUS_LABELS.items() if label in (status or [])}
    deals = _deal_query(db).all()
    treffer = []
    for d in sorted(deals, key=lambda d: (d.bank.name.lower(), d.kontoart, d.inhaber.name)):
        if status_codes and derived.status(d, heute) not in status_codes:
            continue
        if inhaber and inhaber.strip().lower() not in d.inhaber.name.lower():
            continue
        if art and d.art != art:
            continue
        if bank and bank.strip().lower() not in d.bank.name.lower():
            continue
        treffer.append(_deal_kurz(d, heute))
    return {"anzahl": len(treffer), "deals": treffer}


def deal_details_abfragen(db: Session, deal_id: int) -> dict:
    heute = datetime.date.today()
    deal = _deal_query(db).filter(Deal.id == deal_id).one_or_none()
    if deal is None:
        return {"fehler": f"Deal {deal_id} existiert nicht."}
    ergebnis = _deal_kurz(deal, heute)
    entstanden_aus = db.query(DealVorschlag).filter(DealVorschlag.deal_id == deal.id).first()
    ergebnis.update(
        {
            "kontonummer_hinterlegt": bool(deal.kontonummer),
            "zugangsdaten_gesichert": deal.zugangsdaten_gespeichert,
            "storniert": deal.storniert,
            "freibetrag": _wert(deal.freibetrag),
            "freibetrag_jahr": deal.freibetrag_jahr,
            "praemien_auf_sparkonto": deal.praemien_auf_sparkonto,
            "kommentar": deal.kommentar,
            "kuendigung_hinweis": deal.kuendigung_hinweis,
            "kuendigung_hinweis_url": deal.kuendigung_hinweis_url,
            "kuendigung_hinweis_ki_recherchiert": deal.kuendigung_hinweis_ki,
            "praemien_einzeln": [
                {
                    "quelle": derived.quelle_label(p.quelle),
                    "betrag": _wert(p.betrag),
                    "zweck": p.zweck,
                    "erhalten": p.erhalten,
                    "auszahlung_erwartet": p.auszahlung_erwartet,
                    "naechste_pruefung": _wert(derived.praemie_naechste_pruefung(p, heute)) if not p.erhalten else None,
                    "ueberfaellig": derived.praemie_ueberfaellig(deal, p, heute) if not p.erhalten else False,
                }
                for p in deal.praemien
            ],
            "bedingungen": [
                {
                    "beschreibung": b.beschreibung,
                    "erfuellt": b.erfuellt,
                    "erfuellt_am": _wert(b.erfuellt_am),
                    "faellig_bis": _wert(b.faellig_bis),
                    "anzahl": b.anzahl,
                    "betrag_euro": _wert(b.betrag_euro),
                    "frist_wochen": b.frist_wochen,
                    "gilt_fuer": b.gilt_fuer,
                }
                for b in deal.bedingungen
            ],
            "aufgaben": [
                {
                    "beschreibung": a.beschreibung,
                    "erledigt": a.erledigt,
                    "faellig_bis": _wert(a.faellig_bis),
                    "wiederholung": a.wiederholung,
                }
                for a in deal.aufgaben
            ],
            "links": [{"bezeichnung": u.bezeichnung, "url": u.url} for u in deal.urls],
            "offene_angaben": [f.label for f in derived.offene_felder(deal)],
            "zu_pruefen": [p.text for p in derived.pruefpunkte(deal, heute)],
            "todos": [_todo(t) for t in derived.deal_todos(deal, heute)],
            # Nur die Eckdaten - der Text enthält die IBAN im Klartext.
            "kuendigungsschreiben": [
                {
                    "kanal": k.kanal,
                    "datum": _wert(k.datum),
                    "betreff": k.betreff,
                    "versendet_am": _wert(k.versendet_am),
                }
                for k in deal.kuendigungsschreiben
            ],
            "entstanden_aus_vorschlag_id": entstanden_aus.id if entstanden_aus else None,
            "erstellt_am": _wert(deal.erstellt_am),
            "geaendert_am": _wert(deal.geaendert_am),
        }
    )
    return ergebnis


def todos_abfragen(db: Session, kategorie: str | None, auch_spaeter_faellige: bool) -> dict:
    heute = datetime.date.today()
    todos = [
        t
        for t in _alle_todos(db, heute)
        if (auch_spaeter_faellige or not t.zukuenftig)
        and (not kategorie or kategorie.strip().lower() in t.kategorie.lower())
    ]
    todos.sort(key=lambda t: (not t.ueberfaellig, t.faellig_bis or datetime.date.max, t.kategorie))
    return {"stand": heute.isoformat(), "anzahl": len(todos), "todos": [_todo(t) for t in todos]}


def sperrfristen_abfragen(db: Session) -> dict:
    """Wie die Seite "Sperrfristen": gekündigte, nicht stornierte Deals und
    Konten mit Monaten seit der Kündigung - wann eine Bank wieder als
    Neukunden-Ziel in Frage kommt."""
    heute = datetime.date.today()
    deals = (
        db.query(Deal)
        .options(joinedload(Deal.bank), joinedload(Deal.inhaber))
        .filter(Deal.gekuendigt.is_(True), Deal.storniert.is_(False))
        .all()
    )
    zeilen = []
    ohne_monat = []
    for d in deals:
        datum = derived.parse_monat(d.gekuendigt_im_monat)
        if datum is None:
            ohne_monat.append(_bezeichnung(d))
            continue
        monate = derived.monate_seit_kuendigung(datum, heute)
        zeilen.append(
            {
                "deal_id": d.id,
                "bezeichnung": _bezeichnung(d),
                "art": "Konto ohne Prämie" if d.ist_konto else "Deal",
                "gekuendigt_im_monat": d.gekuendigt_im_monat,
                "monate_seit_kuendigung": monate,
                "stufe": {"rot": "unter 6 Monate", "orange": "6 bis 12 Monate", "gruen": "über 12 Monate"}[
                    derived.sperrfrist_stufe(monate)
                ],
            }
        )
    zeilen.sort(key=lambda z: -z["monate_seit_kuendigung"])
    return {"stand": heute.isoformat(), "kuendigungen": zeilen, "gekuendigt_ohne_auswertbaren_monat": ohne_monat}


def statistiken_abfragen(db: Session) -> dict:
    heute = datetime.date.today()
    deals = _deal_query(db).all()
    pipeline = {label: 0 for label in derived.STATUS_LABELS.values()}
    for d in deals:
        pipeline[derived.STATUS_LABELS[derived.status(d, heute)]] += 1

    def freibetrag(deals_inh, jahr):
        # Wie die Statistik-Seite: alle Deals des Jahres, auch gekündigte -
        # ein Freistellungsauftrag ist im Jahr seiner Erteilung verbraucht.
        return _wert(
            sum((d.freibetrag for d in deals_inh if d.freibetrag is not None and d.freibetrag_jahr == jahr), Decimal("0"))
        )

    je_inhaber = []
    for inh in db.query(Inhaber).order_by(Inhaber.name).all():
        deals_inh = [d for d in deals if d.inhaber_id == inh.id]
        je_inhaber.append(
            {
                "inhaber": inh.name,
                "anzahl_deals": sum(1 for d in deals_inh if not d.ist_konto),
                "anzahl_konten_ohne_praemie": sum(1 for d in deals_inh if d.ist_konto),
                "praemien": _kennzahlen([p for d in deals_inh for p in d.praemien]),
                f"freibetrag_{heute.year}": freibetrag(deals_inh, heute.year),
                f"freibetrag_{heute.year - 1}": freibetrag(deals_inh, heute.year - 1),
            }
        )
    return {"stand": heute.isoformat(), "pipeline": pipeline, "je_inhaber": je_inhaber}


def vorschlaege_abfragen(
    db: Session, status: list[str] | None, quelle: list[str] | None, bank: str | None, limit: int
) -> dict:
    abfrage = db.query(DealVorschlag).options(
        joinedload(DealVorschlag.inhaber), joinedload(DealVorschlag.bedingungen), joinedload(DealVorschlag.praemien)
    )
    if status:
        abfrage = abfrage.filter(DealVorschlag.status.in_(status))
    if quelle:
        abfrage = abfrage.filter(DealVorschlag.quelle.in_(quelle))
    zeilen = abfrage.order_by(DealVorschlag.gefunden_am.desc()).all()
    if bank:
        zeilen = [v for v in zeilen if bank.strip().lower() in v.bank_name.lower()]
    gesamt = len(zeilen)
    return {
        "anzahl_gesamt": gesamt,
        "anzahl_angezeigt": min(gesamt, limit),
        "vorschlaege": [
            {
                "id": v.id,
                "status": v.status,
                "bank": v.bank_name,
                "kontoart": v.kontoart,
                "fuer_inhaber": v.inhaber.name if v.inhaber else None,
                "quelle": v.quelle,
                "quelle_url": v.quelle_url,
                "gefunden_am": _wert(v.gefunden_am),
                "praemie_sicher": _wert(v.praemie_betrag),
                "praemie_bis": _wert(v.praemie_bis),
                "praemie_art": v.praemie_art,
                "praemie_beschreibung": v.praemie_beschreibung,
                "teilpraemien": [{"betrag": _wert(p.betrag), "geber": p.geber, "wofuer": p.bedingung} for p in v.praemien],
                "sperrfrist_monate": v.sperrfrist_monate,
                "bedingungen": [{"beschreibung": b.beschreibung, "einschaetzung": b.einschaetzung} for b in v.bedingungen],
                "ablehnungs_oder_pruefgruende": [g for g in (v.ablehnungsgruende or "").split("; ") if g],
                "verwerfen_gruende": [
                    matching.VERWERFEN_GRUENDE_ANZEIGE.get(c, c) for c in (v.verwerfen_gruende or "").split(",") if c
                ],
                "uebernommen_als_deal_id": v.deal_id,
            }
            for v in zeilen[:limit]
        ],
    }


def inhaber_abfragen(db: Session) -> dict:
    ergebnis = []
    for inh in db.query(Inhaber).options(joinedload(Inhaber.deals)).order_by(Inhaber.name).all():
        ergebnis.append(
            {
                "name": inh.name,
                "minderjaehrig": inh.ist_minderjaehrig,
                "anzahl_deals": sum(1 for d in inh.deals if not d.ist_konto),
                "anzahl_konten_ohne_praemie": sum(1 for d in inh.deals if d.ist_konto),
                # Nur ob die Absenderangaben für Kündigungen vollständig sind -
                # Anschrift, Geburtsdatum, E-Mail und IBAN selbst nicht.
                "absenderangaben_vollstaendig": bool(inh.voller_name and inh.strasse and inh.plz and inh.ort),
                "iban_hinterlegt": bool(inh.iban),
            }
        )
    return {"inhaber": ergebnis}


def kuendigung_infos_abfragen(db: Session, bank: str, kontoart: str | None) -> dict:
    """Was über das Kündigen bei einer Bank bekannt ist: fest hinterlegter
    Hinweis, KI-Recherche des nächtlichen Batches, Anforderungen aus dem
    Kündigungs-Assistenten und ob ein Bankformular vorliegt."""
    suche = bank.strip().lower()

    def passt(b: str, k: str) -> bool:
        return suche in b.lower() and (not kontoart or kontoart.strip().lower() == k.lower())

    fest = hinweis_fuer(bank, kontoart) if kontoart else None
    return {
        "fest_hinterlegt": {"hinweis": fest[0], "url": fest[1]} if fest else None,
        "ki_recherchen": [
            {"bank": r.bank_name, "kontoart": r.kontoart, "hinweis": r.hinweis, "url": r.hinweis_url, "recherchiert_am": _wert(r.recherchiert_am)}
            for r in db.query(KuendigungRecherche).all()
            if passt(r.bank_name, r.kontoart)
        ],
        "anforderungen": [
            {
                "bank": a.bank_name,
                "kontoart": a.kontoart,
                "kanal": a.kanal,
                "empfaenger_anschrift": a.empfaenger_anschrift,
                "empfaenger_email": a.empfaenger_email,
                "formular_url": a.formular_url,
                "besonderheiten": a.besonderheiten,
                "quelle_url": a.quelle_url,
                "recherchiert_am": _wert(a.recherchiert_am),
            }
            for a in db.query(KuendigungAnforderung).all()
            if passt(a.bank_name, a.kontoart)
        ],
        "formulare": [
            {"bank": f.bank_name, "kontoart": f.kontoart, "quelle": f.quelle, "hinweis": f.hinweis}
            for f in db.query(KuendigungFormular).all()
            if passt(f.bank_name, f.kontoart)
        ],
    }


def protokoll_abfragen(db: Session, deal_id: int | None, limit: int) -> dict:
    abfrage = db.query(ProtokollEintrag)
    if deal_id is not None:
        abfrage = abfrage.filter(ProtokollEintrag.deal_id == deal_id)
    eintraege = abfrage.order_by(ProtokollEintrag.id.desc()).limit(limit).all()

    def verdeckt(e: ProtokollEintrag, wert):
        return "(verdeckt)" if e.feld in _VERDECKTE_PROTOKOLLFELDER and wert is not None else wert

    return {
        "eintraege": [
            {
                "zeitpunkt_utc": _wert(e.zeitpunkt),
                "aktion": e.aktion,
                "tabelle": e.tabelle,
                "deal_id": e.deal_id,
                "bank": e.bank_name,
                "kontoart": e.kontoart,
                "inhaber": e.inhaber_name,
                "feld": e.feld,
                "alter_wert": verdeckt(e, e.alter_wert),
                "neuer_wert": verdeckt(e, e.neuer_wert),
            }
            for e in eintraege
        ]
    }


def _lauf(lauf: FinderLauf) -> dict:
    return {
        "gestartet_am_utc": _wert(lauf.gestartet_am),
        "beendet_am_utc": _wert(lauf.beendet_am),
        "erfolgreich": lauf.erfolgreich,
        "neu_gefunden": lauf.neu_gefunden,
        "aus_cache": lauf.aus_cache,
        "uebersprungen": lauf.uebersprungen,
        "je_quelle": {
            q: {k: getattr(lauf, f"{q}_{k}") for k in ("geladen", "neu", "vorhanden", "aktualisiert", "rauschen")}
            for q in ("mydealz", "spartanien", "dealdoktor")
        },
        "fehler": lauf.fehler,
    }


def finder_laeufe_abfragen(db: Session, limit: int) -> dict:
    return {"laeufe": [_lauf(l) for l in db.query(FinderLauf).order_by(FinderLauf.id.desc()).limit(limit).all()]}


# --- MCP-Werkzeuge -------------------------------------------------------


def server_bauen() -> FastMCP:
    """Je Aufruf ein frischer Server - der Session-Manager eines FastMCP lässt
    sich nur einmal starten (relevant für Tests, die die App mehrfach
    hochfahren)."""
    mcp = FastMCP(
        "Prämien-Tracker",
        instructions=ANWEISUNGEN,
        # Zustandslos: jede Anfrage steht für sich, nichts bleibt im Speicher
        # hängen. Antworten bewusst als Event-Stream (Standard) statt
        # json_response - im JSON-Modus loggt mcp 1.12 nach jeder Anfrage einen
        # harmlosen, aber als ERROR markierten ClosedResourceError ins
        # Add-on-Log.
        stateless_http=True,
        host="0.0.0.0",
    )

    async def laufen(funktion, *args):
        # Die Abfragen sind synchrone SQLAlchemy-Aufrufe - im Worker-Thread,
        # damit sie die Oberfläche (gleicher Prozess) nicht blockieren.
        return await anyio.to_thread.run_sync(_in_sitzung, funktion, *args)

    @mcp.tool(annotations=_NUR_LESEN)
    async def uebersicht() -> dict:
        """Gesamtüberblick: Prämiensummen, Anzahl Deals und Konten, Deals je
        Status, offene ToDos je Kategorie (mit überfälligen), Vorschläge je
        Status und der letzte Lauf des KI-Deal-Finders. Guter Einstieg."""
        return await laufen(uebersicht_abfragen)

    @mcp.tool(annotations=_NUR_LESEN)
    async def deals_suchen(
        status: list[str] | None = None,
        inhaber: str | None = None,
        art: Literal["deal", "konto"] | None = None,
        bank: str | None = None,
    ) -> dict:
        """Deals und Konten ohne Prämie auflisten, optional gefiltert.

        status: Status-Codes oder -Namen, z. B. "kuendigen", "Bedingungen",
        "praemie_warten", "abgeschlossen". inhaber und bank: Teil des Namens.
        art: "deal" oder "konto" (Konto ohne Prämie)."""
        return await laufen(deals_suchen_abfragen, status, inhaber, art, bank)

    @mcp.tool(annotations=_NUR_LESEN)
    async def deal_details(deal_id: int) -> dict:
        """Alles zu einem Deal oder Konto: Prämien mit nächstem Prüftermin,
        Bedingungen, Aufgaben, Links, Kündigungshinweis, offene Angaben,
        Prüfpunkte, ToDos, Kündigungsschreiben (Eckdaten) und Herkunft aus
        einem Vorschlag. Kontonummer nur als "hinterlegt ja/nein"."""
        return await laufen(deal_details_abfragen, deal_id)

    @mcp.tool(annotations=_NUR_LESEN)
    async def todos(kategorie: str | None = None, auch_spaeter_faellige: bool = False) -> dict:
        """Was zu tun ist - dieselbe Liste wie der Reiter "Zu erledigen".
        kategorie (Teil des Namens): "Bedingungen", "Auf Prämie warten",
        "Prämienauszahlung prüfen", "Kündigen", "Bestätigung warten",
        "Deal pflegen", "Zu prüfen", "Manuelle Aufgaben". Überfällige zuerst.
        auch_spaeter_faellige: manuelle Aufgaben mit Termin in der Zukunft
        mitliefern."""
        return await laufen(todos_abfragen, kategorie, auch_spaeter_faellige)

    @mcp.tool(annotations=_NUR_LESEN)
    async def sperrfristen() -> dict:
        """Gekündigte Deals und Konten mit Monaten seit der Kündigung, älteste
        zuerst - wann eine Bank wieder als Neukunden-Ziel in Frage kommt."""
        return await laufen(sperrfristen_abfragen)

    @mcp.tool(annotations=_NUR_LESEN)
    async def statistiken() -> dict:
        """Anzahl je Status (Pipeline) und je Inhaber: Deals, Konten,
        Prämiensummen und genutzter Freistellungsauftrag im laufenden und im
        Vorjahr."""
        return await laufen(statistiken_abfragen)

    @mcp.tool(annotations=_NUR_LESEN)
    async def vorschlaege(
        status: list[
            Literal["vorgeschlagen", "zu_pruefen", "automatisch_abgelehnt", "verworfen", "uebernommen"]
        ]
        | None = None,
        quelle: list[Literal["mydealz", "spartanien", "dealdoktor"]] | None = None,
        bank: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Funde des KI-Deal-Finders, neueste zuerst, je Inhaber eine Zeile:
        Prämie (sicher / bis zu / Sachprämie), Bedingungen mit Einschätzung,
        Ablehnungs- oder Prüfgründe, Verwerfen-Gründe, Link zum Angebot."""
        return await laufen(vorschlaege_abfragen, status, quelle, bank, max(1, min(limit, 500)))

    @mcp.tool(annotations=_NUR_LESEN)
    async def inhaber() -> dict:
        """Die Inhaber mit Anzahl Deals und Konten und ob ihre Angaben für
        Kündigungsschreiben vollständig sind (ohne die Angaben selbst)."""
        return await laufen(inhaber_abfragen)

    @mcp.tool(annotations=_NUR_LESEN)
    async def kuendigung_infos(bank: str, kontoart: str | None = None) -> dict:
        """Was über das Kündigen bei einer Bank bekannt ist: fest hinterlegter
        Hinweis, KI-recherchierte Kündigungswege, Anforderungen und Anschrift
        aus dem Kündigungs-Assistenten, vorhandene Bankformulare."""
        return await laufen(kuendigung_infos_abfragen, bank, kontoart)

    @mcp.tool(annotations=_NUR_LESEN)
    async def aenderungsprotokoll(deal_id: int | None = None, limit: int = 50) -> dict:
        """Letzte Änderungen, neueste zuerst, optional nur für einen Deal.
        Persönliche Angaben (Kontonummer, Anschrift, IBAN ...) erscheinen nur
        als "(verdeckt)"."""
        return await laufen(protokoll_abfragen, deal_id, max(1, min(limit, 500)))

    @mcp.tool(annotations=_NUR_LESEN)
    async def finder_laeufe(limit: int = 5) -> dict:
        """Die letzten Läufe des KI-Deal-Finders mit Zählern je Quelle und
        Fehlern."""
        return await laufen(finder_laeufe_abfragen, max(1, min(limit, 50)))

    return mcp


# --- Zugriffsschutz und Start --------------------------------------------


class BearerSchutz:
    """Lässt nur Anfragen mit "Authorization: Bearer <token>" durch -
    Vergleich in konstanter Zeit."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.erwartet = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            kopf = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(kopf, self.erwartet):
                antwort = JSONResponse({"fehler": "Nicht autorisiert"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
                await antwort(scope, receive, send)
                return
        await self.app(scope, receive, send)


def asgi_app(token: str) -> ASGIApp:
    return BearerSchutz(server_bauen().streamable_http_app(), token)


def token_ok(token: str | None) -> bool:
    return bool(token) and len(token) >= MINDESTLAENGE_TOKEN


def server_erstellen(token: str, port: int):
    """uvicorn-Server für den MCP-Endpunkt. main.py startet ihn als
    Hintergrund-Task im Lifespan der Haupt-App und beendet ihn dort über
    should_exit wieder. Die Signalbehandlung bleibt beim Haupt-Server
    (run.sh) - zwei Server, die SIGTERM abfangen, nähmen sich gegenseitig das
    Herunterfahren ab."""
    import uvicorn

    config = uvicorn.Config(asgi_app(token), host="0.0.0.0", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
    return server
