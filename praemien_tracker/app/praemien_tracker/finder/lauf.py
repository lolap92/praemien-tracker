"""Orchestriert den täglichen Lauf: Quellen abfragen, extrahieren, bewerten,
speichern, benachrichtigen (Konzept Abschnitt 6).

Jeder gefundene, thematisch passende Fund wird für *jeden* Inhaber als eigene
Zeile gespeichert und angezeigt - auch bei Nichterfüllung. Nichts wird
stillschweigend verworfen (zentrale Idee des Konzepts).

Bevor ein Rohfund gegen die Anthropic-API geschickt wird, prüft der Lauf
gegen FinderFund (models.py), ob dieselbe Quelle-URL mit demselben Rohtext
schon einmal geprüft wurde. Trifft das zu, entfällt der API-Aufruf: ein
bereits als irrelevant erkannter Fund wird direkt übersprungen, ein bereits
extrahiertes Angebot wird aus dem Cache übernommen. Nur wenn sich der
Rohtext geändert hat (z.B. ein bearbeiteter Beitrag) oder die URL neu ist,
wird tatsächlich Themen-Check und/oder Struktur-Extraktion aufgerufen. Das
deterministische Matching läuft trotzdem bei jedem Lauf erneut, weil sich
z.B. eine Sperrfrist rein durch Zeitablauf ändern kann, ohne dass sich am
Angebot selbst etwas ändert.

Jeder Aufruf von taeglicher_lauf() schreibt am Ende immer eine FinderLauf-
Zeile (models.py) - Grundlage für die Statusanzeige im Vorschläge-Tab:
erfolgreich?, wie viele Funde je Quelle, wie viele neu, wie viele aus dem
Cache ohne API-Aufruf, welche Fehler.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import anthropic
from sqlalchemy.orm import Session

from .. import config
from ..anthropic_client import anthropic_client as _anthropic_client_basis
from ..database import SessionLocal
from ..models import DealVorschlag, FinderFund, FinderLauf, Inhaber, VorschlagBedingung
from . import extraktion, matching, notify
from .extraktion import AngebotExtraktion
from .quellen import RohFund, fetch_mydealz, fetch_spartanien

logger = logging.getLogger("praemien_tracker.finder")


@dataclass
class _QuellenErgebnis:
    mydealz_funde: list[RohFund] = field(default_factory=list)
    spartanien_funde: list[RohFund] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)

    @property
    def alle(self) -> list[RohFund]:
        return self.mydealz_funde + self.spartanien_funde


def _anthropic_client() -> anthropic.Anthropic | None:
    client = _anthropic_client_basis()
    if client is None:
        logger.warning("Kein Anthropic-API-Key hinterlegt (Add-on-Optionen) - KI-Deal-Finder übersprungen.")
    return client


def _rohfunde_holen() -> _QuellenErgebnis:
    """Beide Quellen abfragen. Schlägt eine fehl (z.B. geändertes Markup bei
    spartanien, Netzwerkfehler), läuft der Rest mit der anderen Quelle weiter
    - ein einzelner Quellenausfall soll nicht den ganzen Tageslauf stoppen,
    wird aber als Fehler im Protokoll festgehalten."""
    ergebnis = _QuellenErgebnis()
    try:
        ergebnis.mydealz_funde = fetch_mydealz(config.MYDEALZ_GRUPPE)
    except Exception as exc:
        logger.exception("mydealz-Abruf fehlgeschlagen, Lauf wird ohne diese Quelle fortgesetzt.")
        ergebnis.fehler.append(f"mydealz nicht erreichbar: {exc}")
    try:
        ergebnis.spartanien_funde = fetch_spartanien(config.SPARTANIEN_URL)
    except Exception as exc:
        logger.exception("spartanien-Abruf fehlgeschlagen, Lauf wird ohne diese Quelle fortgesetzt.")
        ergebnis.fehler.append(f"spartanien nicht erreichbar: {exc}")
    return ergebnis


def _rohtext_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_speichern(
    db: Session,
    bestehender: FinderFund | None,
    fund: RohFund,
    rohtext_hash: str,
    *,
    ist_relevant: bool,
    extraktion_ergebnis: AngebotExtraktion | None,
) -> None:
    """Legt den Cache-Eintrag an oder aktualisiert ihn (quelle_url ist
    eindeutig - bei geändertem Rohtext wird der bestehende Eintrag
    überschrieben, nicht dupliziert)."""
    eintrag = bestehender
    if eintrag is None:
        eintrag = FinderFund(quelle=fund.quelle, quelle_url=fund.quelle_url)
        db.add(eintrag)
    eintrag.rohtext_hash = rohtext_hash
    eintrag.ist_relevant = ist_relevant
    eintrag.extraktion_json = extraktion_ergebnis.model_dump_json() if extraktion_ergebnis is not None else None
    eintrag.zuletzt_gesehen_am = datetime.datetime.utcnow()


def _protokoll_speichern(db: Session, **werte) -> None:
    """Schreibt eine neue FinderLauf-Zeile. Läuft in einer eigenen kleinen
    Transaktion - wird nach einem db.rollback() im Hauptteil aufgerufen,
    braucht also eine saubere Session, keine, in der noch ein gescheiterter
    Schreibvorgang hängt."""
    eintrag = FinderLauf(beendet_am=datetime.datetime.utcnow(), **werte)
    db.add(eintrag)
    db.commit()


def taeglicher_lauf(db: Session, *, client: anthropic.Anthropic | None = None) -> dict[str, int]:
    """Führt einen kompletten Lauf aus und gibt Zähler zurück (fürs Logging
    und den manuellen "Jetzt suchen"-Button im Vorschläge-Tab). Wirft nie -
    ein unerwarteter Fehler wird abgefangen, zurückgerollt und als
    nicht erfolgreicher Lauf protokolliert, statt die aufrufende Seite
    (Scheduler-Job oder "Jetzt suchen") abstürzen zu lassen."""
    zaehler = {
        # gefunden = neu angelegte Vorschlags-Zeilen (eine je Inhaber) -
        # internes Maß, das die Tests gegen die Zeilenanlage prüfen.
        "gefunden": 0,
        # neue_vorschlaege = neue Angebote/Karten (eine je Fund, unabhängig
        # von der Zahl der Inhaber) - ein neuer Deal zählt genau einmal.
        "neue_vorschlaege": 0,
        "aktualisiert": 0,
        matching.STATUS_VORGESCHLAGEN: 0,
        matching.STATUS_ZU_PRUEFEN: 0,
        matching.STATUS_ABGELEHNT: 0,
        "uebersprungen": 0,
        "aus_cache": 0,
    }

    # Aufschlüsselung je Quelle für die Tabelle im Vorschläge-Tab. Jeder
    # geladene Fund wird genau einer Kategorie zugeordnet (neu / vorhanden /
    # aktualisiert / rauschen), die Summe je Quelle ergibt <quelle>_geladen.
    kategorie: dict[str, Counter] = defaultdict(Counter)

    aktiver_client = client if client is not None else _anthropic_client()
    if aktiver_client is None:
        _protokoll_speichern(db, erfolgreich=True, fehler="Kein Anthropic-API-Key hinterlegt - Lauf übersprungen.")
        return zaehler

    inhaber_liste = db.query(Inhaber).all()
    if not inhaber_liste:
        _protokoll_speichern(db, erfolgreich=True, fehler="Kein Inhaber angelegt - Lauf übersprungen.")
        return zaehler

    quellen = _rohfunde_holen()
    fehlermeldungen = list(quellen.fehler)

    try:
        bereits_verarbeitet: set[str] = set()
        for fund in quellen.alle:
            # Bewusst zusätzlich zur Deduplizierung in den Parsern (z.B.
            # quellen.parse_mydealz_rss): finder_funde.quelle_url ist
            # eindeutig, ein doppelter Fund - egal aus welcher Quelle oder
            # welchem Grund - würde sonst den ganzen Lauf mit einem
            # IntegrityError abbrechen statt nur diesen einen Fund zu
            # überspringen.
            if fund.quelle_url in bereits_verarbeitet:
                kategorie[fund.quelle]["rauschen"] += 1
                continue
            bereits_verarbeitet.add(fund.quelle_url)

            rohtext_hash = _rohtext_hash(fund.text)
            cache_eintrag = db.query(FinderFund).filter(FinderFund.quelle_url == fund.quelle_url).one_or_none()

            aus_cache = False
            extrahiert: AngebotExtraktion | None = None

            if cache_eintrag is not None and cache_eintrag.rohtext_hash == rohtext_hash:
                cache_eintrag.zuletzt_gesehen_am = datetime.datetime.utcnow()
                if not cache_eintrag.ist_relevant:
                    zaehler["aus_cache"] += 1
                    kategorie[fund.quelle]["rauschen"] += 1
                    continue
                try:
                    extrahiert = AngebotExtraktion.model_validate_json(cache_eintrag.extraktion_json)
                    aus_cache = True
                except Exception:
                    # Fällt z.B. an, wenn sich die extrahierten Felder seit
                    # einem App-Update geändert haben - kein API-Fehler,
                    # einfach neu extrahieren statt an einem kaputten
                    # Cache-Eintrag festzuhalten.
                    logger.exception(
                        "Gecachte Extraktion für %s ließ sich nicht lesen, wird neu geprüft.", fund.quelle_url
                    )

            if not aus_cache:
                try:
                    relevant = extraktion.ist_relevantes_angebot(
                        aktiver_client, fund.text, model=config.ANTHROPIC_MODEL
                    )
                except Exception as exc:
                    logger.exception("Themen-Check für %s fehlgeschlagen, Fund wird übersprungen.", fund.quelle_url)
                    fehlermeldungen.append(f"Themen-Check für {fund.quelle_url}: {exc}")
                    zaehler["uebersprungen"] += 1
                    kategorie[fund.quelle]["rauschen"] += 1
                    continue
                if not relevant:
                    _cache_speichern(
                        db, cache_eintrag, fund, rohtext_hash, ist_relevant=False, extraktion_ergebnis=None
                    )
                    kategorie[fund.quelle]["rauschen"] += 1
                    continue

                try:
                    extrahiert = extraktion.extrahiere_angebot(aktiver_client, fund.text, model=config.ANTHROPIC_MODEL)
                except Exception as exc:
                    logger.exception(
                        "Struktur-Extraktion für %s fehlgeschlagen, Fund wird übersprungen.", fund.quelle_url
                    )
                    fehlermeldungen.append(f"Extraktion für {fund.quelle_url}: {exc}")
                    zaehler["uebersprungen"] += 1
                    kategorie[fund.quelle]["rauschen"] += 1
                    continue
                if extrahiert is None:
                    fehlermeldungen.append(f"Extraktion für {fund.quelle_url} lieferte kein Ergebnis.")
                    zaehler["uebersprungen"] += 1
                    kategorie[fund.quelle]["rauschen"] += 1
                    continue

                _cache_speichern(
                    db, cache_eintrag, fund, rohtext_hash, ist_relevant=True, extraktion_ergebnis=extrahiert
                )
            else:
                zaehler["aus_cache"] += 1

            # Pro Inhaber eine eigene Zeile, weil Sperrfrist- und Neukunden-
            # Prüfung je Inhaber unterschiedlich ausfallen kann (Konzept
            # Abschnitt 5). Läuft bewusst auch bei einem Cache-Treffer erneut
            # (kostet nichts, ist reiner Python-Code): eine Sperrfrist kann
            # rein durch Zeitablauf erfüllt werden, ohne dass sich am
            # Angebot etwas ändert.
            neuer_vorschlag_fuer_fund = False
            aktualisiert_fuer_fund = False
            for inhaber in inhaber_liste:
                # Minderjährigen wird ein Angebot nur vorgeschlagen, wenn es
                # laut Text (auch) für Kinder abschließbar ist (z.B. Junior-
                # Depot, Kinderkonto). Die meisten Neukunden-Prämien setzen
                # Volljährigkeit voraus - steht nichts im Text, gilt der Deal
                # als reines Erwachsenen-Angebot (extrahiert.fuer_kinder=False),
                # und das Kind erscheint gar nicht erst als Auswahl.
                if inhaber.ist_minderjaehrig and not extrahiert.fuer_kinder:
                    continue
                match = matching.bewerten(db, fund, extrahiert, inhaber, config.MINDESTPRAEMIE)
                bestehend = matching.bestehenden_vorschlag_finden(
                    db, fund.quelle_url, inhaber.id, match.inhalt_hash
                )
                if bestehend is not None:
                    # Gleicher Inhalt wie zuvor - i.d.R. nichts zu tun. Nur
                    # wenn sich die Bewertung rein durch Zeitablauf geändert
                    # hat (z.B. eine Sperrfrist ist inzwischen erreicht, ohne
                    # dass sich am Angebot etwas geändert hätte), wird die
                    # bestehende, noch offene Zeile nachgezogen - ein bereits
                    # vom Nutzer übernommener oder verworfener Vorschlag
                    # bleibt unangetastet.
                    if bestehend.status in matching.STATUS_OFFEN and bestehend.status != match.status:
                        bestehend.status = match.status
                        bestehend.ablehnungsgruende = match.ablehnungsgruende
                        zaehler["aktualisiert"] += 1
                        aktualisiert_fuer_fund = True
                        zaehler[match.status] = zaehler.get(match.status, 0) + 1
                    continue

                vorschlag = DealVorschlag(
                    inhaber_id=inhaber.id,
                    quelle=fund.quelle,
                    quelle_url=fund.quelle_url,
                    bank_name=extrahiert.bank_name.strip(),
                    kontoart=extrahiert.kontoart.strip(),
                    praemie_betrag=match.praemie_betrag,
                    sperrfrist_monate=match.sperrfrist_monate,
                    ablehnungsgruende=match.ablehnungsgruende,
                    roh_json=match.roh_json,
                    inhalt_hash=match.inhalt_hash,
                    status=match.status,
                )
                for bewertung in match.bedingungen:
                    vorschlag.bedingungen.append(
                        VorschlagBedingung(beschreibung=bewertung.beschreibung, einschaetzung=bewertung.einschaetzung)
                    )
                db.add(vorschlag)

                zaehler["gefunden"] += 1
                neuer_vorschlag_fuer_fund = True
                zaehler[match.status] = zaehler.get(match.status, 0) + 1

            # Jedes relevante Bank-Angebot zählt genau einmal (eine Karte, nicht
            # eine Zeile je Person) - je nachdem, was in diesem Lauf passiert
            # ist: ganz neu, ein Status nachgezogen, oder unverändert bekannt.
            if neuer_vorschlag_fuer_fund:
                zaehler["neue_vorschlaege"] += 1
                kategorie[fund.quelle]["neu"] += 1
            elif aktualisiert_fuer_fund:
                kategorie[fund.quelle]["aktualisiert"] += 1
            else:
                kategorie[fund.quelle]["vorhanden"] += 1

        db.commit()
        erfolgreich = True
    except Exception as exc:
        logger.exception("KI-Deal-Finder-Lauf unerwartet abgebrochen.")
        db.rollback()
        fehlermeldungen.append(f"Lauf abgebrochen: {exc}")
        erfolgreich = False

    _protokoll_speichern(
        db,
        erfolgreich=erfolgreich,
        mydealz_geladen=len(quellen.mydealz_funde),
        spartanien_geladen=len(quellen.spartanien_funde),
        mydealz_neu=kategorie["mydealz"]["neu"],
        mydealz_vorhanden=kategorie["mydealz"]["vorhanden"],
        mydealz_aktualisiert=kategorie["mydealz"]["aktualisiert"],
        mydealz_rauschen=kategorie["mydealz"]["rauschen"],
        spartanien_neu=kategorie["spartanien"]["neu"],
        spartanien_vorhanden=kategorie["spartanien"]["vorhanden"],
        spartanien_aktualisiert=kategorie["spartanien"]["aktualisiert"],
        spartanien_rauschen=kategorie["spartanien"]["rauschen"],
        neu_gefunden=zaehler["neue_vorschlaege"],
        uebersprungen=zaehler["uebersprungen"],
        aus_cache=zaehler["aus_cache"],
        fehler="; ".join(fehlermeldungen) or None,
    )

    # Rein automatisch abgelehnte Funde lösen bewusst keine Benachrichtigung
    # aus - nur vorgeschlagen und zu_pruefen (Konzept Abschnitt 6, Schritt 7).
    zu_benachrichtigen = zaehler[matching.STATUS_VORGESCHLAGEN] + zaehler[matching.STATUS_ZU_PRUEFEN]
    if zu_benachrichtigen:
        try:
            notify.benachrichtigen(
                zaehler[matching.STATUS_VORGESCHLAGEN],
                zaehler[matching.STATUS_ZU_PRUEFEN],
                aktiv=config.BENACHRICHTIGUNGEN_AKTIV,
                dienst=config.NOTIFY_DIENST,
            )
        except Exception:
            logger.exception("HA-Benachrichtigung fehlgeschlagen.")

    logger.info(
        "KI-Deal-Finder-Lauf abgeschlossen: %d neue Vorschläge (%d Zeilen), %d Status aktualisiert "
        "(%d vorgeschlagen, %d zu prüfen, %d abgelehnt insgesamt), %d übersprungen, %d aus Cache ohne API-Aufruf.",
        zaehler["neue_vorschlaege"],
        zaehler["gefunden"],
        zaehler["aktualisiert"],
        zaehler[matching.STATUS_VORGESCHLAGEN],
        zaehler[matching.STATUS_ZU_PRUEFEN],
        zaehler[matching.STATUS_ABGELEHNT],
        zaehler["uebersprungen"],
        zaehler["aus_cache"],
    )
    return zaehler


def geplanter_lauf() -> None:
    """Einstiegspunkt für den APScheduler-Job (main.py) - öffnet eine eigene
    Session, da der Job außerhalb eines Requests läuft."""
    with SessionLocal() as db:
        taeglicher_lauf(db)
