"""Orchestriert den täglichen Lauf: Quellen abfragen, extrahieren, bewerten,
speichern, benachrichtigen (Konzept Abschnitt 6).

Jeder gefundene, thematisch passende Fund wird für *jeden* Inhaber als eigene
Zeile gespeichert und angezeigt - auch bei Nichterfüllung. Nichts wird
stillschweigend verworfen (zentrale Idee des Konzepts).

Bevor ein Rohfund gegen die Anthropic-API geschickt wird, prüft der Lauf
gegen FinderFund (models.py), ob dieselbe Quelle-URL mit demselben Rohtext
schon einmal geprüft wurde. Trifft das zu, entfällt der API-Aufruf: ein
bereits als irrelevant erkannter Fund wird direkt übersprungen, ein bereits
extrahiertes Angebot wird aus dem Cache übernommen. Existiert für eine
Quelle-URL bereits mindestens ein Vorschlag (für irgendeinen Inhaber, egal
welcher Status), gilt sie zusätzlich als endgültig geprüft: geringfügig
schwankender Rohtext derselben URL (z.B. Kommentar-/Bewertungszahlen im
RSS-Feed) - selbst eine echte spätere Änderung an Prämie oder Bedingungen -
löst dann keinen erneuten API-Aufruf mehr aus, bewusst zulasten davon, eine
solche spätere Änderung zu verpassen (verhindert dafür zuverlässig
unnötige API-Kosten und Duplikate durch schwankenden Rohtext derselben
URL). Nur bei einer wirklich neuen URL wird tatsächlich Themen-Check
und/oder Struktur-Extraktion aufgerufen, oder wenn "Alle neu analysieren"
(ignoriere_cache) das gezielt überstimmt. Das deterministische Matching
läuft trotzdem bei jedem Lauf erneut, weil sich z.B. eine Sperrfrist rein
durch Zeitablauf ändern kann, ohne dass sich am Angebot selbst etwas
ändert.

Jeder Aufruf von taeglicher_lauf() schreibt am Ende immer eine FinderLauf-
Zeile (models.py) - Grundlage für die Statusanzeige im Vorschläge-Tab:
erfolgreich?, wie viele Funde je Quelle, wie viele neu, wie viele aus dem
Cache ohne API-Aufruf, welche Fehler.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import anthropic
from sqlalchemy.orm import Session

from .. import config
from ..anthropic_client import anthropic_client as _anthropic_client_basis
from ..database import SessionLocal
from ..models import DealVorschlag, FinderFund, FinderLauf, Inhaber, VorschlagBedingung, VorschlagPraemie
from . import extraktion, matching, notify
from .extraktion import AngebotExtraktion
from .quellen import RohFund, fetch_dealdoktor, fetch_mydealz, fetch_spartanien

logger = logging.getLogger("praemien_tracker.finder")


@dataclass
class _QuellenErgebnis:
    mydealz_funde: list[RohFund] = field(default_factory=list)
    spartanien_funde: list[RohFund] = field(default_factory=list)
    dealdoktor_funde: list[RohFund] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)

    @property
    def alle(self) -> list[RohFund]:
        return self.mydealz_funde + self.spartanien_funde + self.dealdoktor_funde


def _anthropic_client() -> anthropic.Anthropic | None:
    client = _anthropic_client_basis()
    if client is None:
        logger.warning("Kein Anthropic-API-Key hinterlegt (Add-on-Optionen) - KI-Deal-Finder übersprungen.")
    return client


def _rohfunde_holen() -> _QuellenErgebnis:
    """Alle Quellen abfragen. Schlägt eine fehl (z.B. geändertes Markup bei
    spartanien, Netzwerkfehler), läuft der Rest mit den anderen Quellen weiter
    - ein einzelner Quellenausfall soll nicht den ganzen Tageslauf stoppen,
    wird aber als Fehler im Protokoll festgehalten."""
    ergebnis = _QuellenErgebnis()
    mydealz_funde: list[RohFund] = []
    for gruppe in config.MYDEALZ_GRUPPEN:
        # Jede Gruppe einzeln abgefangen, gleiche Logik wie bei den
        # dealdoktor-Feeds unten: eine nicht (mehr) erreichbare Gruppe soll
        # nicht die anderen mydealz-Gruppen mit ausfallen lassen. Dedupliziert
        # wird hier bewusst nicht (anders als bei dealdoktor mit seinen
        # überlappenden Themenwelten) - eine doppelte quelle_url innerhalb
        # eines Laufs wird ohnehin weiter unten als "rauschen" gezählt und
        # übersprungen (siehe finder_funde-Verarbeitung).
        try:
            mydealz_funde.extend(fetch_mydealz(gruppe))
        except Exception as exc:
            logger.exception("mydealz-Abruf (%s) fehlgeschlagen, Lauf wird ohne diese Gruppe fortgesetzt.", gruppe)
            ergebnis.fehler.append(f"mydealz ({gruppe}) nicht erreichbar: {exc}")
    ergebnis.mydealz_funde = mydealz_funde
    try:
        ergebnis.spartanien_funde = fetch_spartanien(config.SPARTANIEN_URL)
    except Exception as exc:
        logger.exception("spartanien-Abruf fehlgeschlagen, Lauf wird ohne diese Quelle fortgesetzt.")
        ergebnis.fehler.append(f"spartanien nicht erreichbar: {exc}")
    dealdoktor_funde: list[RohFund] = []
    gesehene_dealdoktor_urls: set[str] = set()
    for feed_url in config.DEALDOKTOR_FEED_URLS:
        # Jeder Feed einzeln abgefangen: eine nicht (mehr) erreichbare
        # Rubrik/Themenwelt soll nicht die anderen dealdoktor-Feeds mit
        # ausfallen lassen, gleiche Logik wie bei mydealz/spartanien oben.
        try:
            for fund in fetch_dealdoktor(feed_url):
                if fund.quelle_url in gesehene_dealdoktor_urls:
                    continue
                gesehene_dealdoktor_urls.add(fund.quelle_url)
                dealdoktor_funde.append(fund)
        except Exception as exc:
            logger.exception(
                "dealdoktor-Abruf (%s) fehlgeschlagen, Lauf wird ohne diesen Feed fortgesetzt.", feed_url
            )
            ergebnis.fehler.append(f"dealdoktor ({feed_url}) nicht erreichbar: {exc}")
    ergebnis.dealdoktor_funde = dealdoktor_funde
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


def _vorschlag_felder_setzen(
    vorschlag: DealVorschlag, extrahiert: AngebotExtraktion, match: matching.MatchErgebnis
) -> None:
    """Setzt alle aus der Extraktion/Bewertung abgeleiteten Felder eines
    Vorschlags - für neu angelegte Zeilen und, bei "Alle neu analysieren"
    (ignoriere_cache), auch für bereits bestehende: der Inhalts-Hash allein
    (Bank/Kontoart/Prämie/Sperrfrist/Bedingungen) erkennt keine Änderung an
    Detailfeldern wie der Prämien-Aufschlüsselung oder den Bedingungstexten,
    deshalb müssen die bei einer erzwungenen Neuprüfung explizit ersetzt
    werden statt sich auf den Hash-Vergleich zu verlassen."""
    vorschlag.bank_name = extrahiert.bank_name.strip()
    vorschlag.kontoart = extrahiert.kontoart.strip()
    vorschlag.praemie_betrag = match.praemie_betrag
    vorschlag.sperrfrist_monate = match.sperrfrist_monate
    vorschlag.ablehnungsgruende = match.ablehnungsgruende
    vorschlag.roh_json = match.roh_json
    vorschlag.status = match.status
    vorschlag.bedingungen = [
        VorschlagBedingung(
            beschreibung=b.beschreibung,
            einschaetzung=b.einschaetzung,
            anzahl=b.anzahl,
            betrag_euro=b.betrag_euro,
            frist_wochen=b.frist_wochen,
        )
        for b in match.bedingungen
    ]
    vorschlag.praemien = [
        VorschlagPraemie(betrag=p.betrag, geber=p.geber, bedingung=p.bedingung) for p in match.praemien
    ]


def _ist_anwendbar(ist_minderjaehrig: bool, fuer_kinder: bool) -> bool:
    """Ob ein Angebot für einen Inhaber mit dieser Alterseinstufung
    grundsätzlich infrage kommt - symmetrisch: ein Kinderdeal
    (fuer_kinder=True) gilt nur für Minderjährige, ein reines
    Erwachsenen-Angebot (fuer_kinder=False) nur für Erwachsene. Beide Seiten
    lassen sich im "Für wen übernehmen?"-Dialog trotzdem manuell ergänzen
    ("+ Kinder"/"+ Eltern", siehe routers/vorschlaege.py) - diese Prüfung
    entscheidet nur, wer automatisch eine eigene Zeile bekommt."""
    return ist_minderjaehrig == fuer_kinder


def _nicht_anwendbaren_vorschlag_entfernen(db: Session, quelle_url: str, inhaber_id: int) -> None:
    """Löscht eine für diesen Inhaber schon bestehende, noch offene
    Vorschlagszeile zu `quelle_url`, sobald die aktuelle Prüfung ergibt, dass
    das Angebot für ihn gar nicht anwendbar ist (siehe Aufrufer und
    _ist_anwendbar). Ohne das würde eine früher - z.B. vor Einführung dieser
    Alterprüfung oder unter einer damals abweichenden fuer_kinder-Einschätzung
    - angelegte Zeile für immer offen hängen bleiben: der Inhaber wird ja
    gerade übersprungen und nie wieder neu bewertet, und die Vorschlags-Karte
    würde trotz Übernahme durch die übrigen Haushaltsmitglieder nie
    verschwinden.

    Bewusst gelöscht statt verworfen: ein Kind kann ein reines
    Erwachsenen-Angebot (und umgekehrt ein Erwachsener einen reinen
    Kinderdeal) strukturell gar nicht abschließen, das ist keine
    Entscheidung, die "übernehmen" oder "verwerfen" bräuchte oder sich später
    nochmal überstimmen ließe (anders als ein echtes manuelles Verwerfen,
    siehe "Doch übernehmen" in vorschlaege.html) - die Zeile soll einfach so
    verschwinden, als wäre sie nie entstanden."""
    offene = (
        db.query(DealVorschlag)
        .filter(
            DealVorschlag.quelle_url == quelle_url,
            DealVorschlag.inhaber_id == inhaber_id,
            DealVorschlag.status.in_(matching.STATUS_OFFEN),
        )
        .all()
    )
    for vorschlag in offene:
        db.delete(vorschlag)


def _nicht_mehr_anwendbare_vorschlaege_bereinigen(db: Session, inhaber_liste: list[Inhaber]) -> None:
    """Pauschaler Aufräumdurchlauf vor dem eigentlichen Lauf: löscht jede noch
    offene Vorschlagszeile, deren zwischengespeicherte Extraktion
    (FinderFund.extraktion_json) laut _ist_anwendbar inzwischen nicht mehr zum
    Alter des jeweiligen Inhabers passt - auch für Funde, die in diesem Lauf
    gar nicht erneut aus einer Quelle geladen werden (z.B. weil das Angebot
    dort nicht mehr gelistet ist). Ohne diesen pauschalen Vorablauf würde eine
    solche Alt-Zeile nur bereinigt, wenn ausgerechnet noch genau derselbe Fund
    erneut geladen wird (siehe _nicht_anwendbaren_vorschlag_entfernen weiter
    unten im Hauptlauf) - bei einem inzwischen nicht mehr gelisteten Deal nie,
    auch nicht durch "Jetzt suchen" oder "Alle neu analysieren". Rein lokale
    DB-Prüfung, kein API-Aufruf nötig, da die Klassifizierung schon im Cache
    liegt. Löscht statt zu verwerfen - siehe Begründung dort."""
    inhaber_by_id = {i.id: i for i in inhaber_liste}
    offene = db.query(DealVorschlag).filter(DealVorschlag.status.in_(matching.STATUS_OFFEN)).all()
    for vorschlag in offene:
        inhaber = inhaber_by_id.get(vorschlag.inhaber_id)
        if inhaber is None:
            continue
        cache_eintrag = db.query(FinderFund).filter(FinderFund.quelle_url == vorschlag.quelle_url).one_or_none()
        if cache_eintrag is None or not cache_eintrag.ist_relevant or not cache_eintrag.extraktion_json:
            # Kein oder kein brauchbarer Cache-Eintrag (z.B. nach einem
            # "Zurücksetzen" ohne begleitendes Löschen der Zeile) - im
            # Zweifel unangetastet lassen statt zu raten.
            continue
        try:
            extrahiert = AngebotExtraktion.model_validate_json(cache_eintrag.extraktion_json)
        except Exception:
            continue
        if not _ist_anwendbar(inhaber.ist_minderjaehrig, extrahiert.fuer_kinder):
            db.delete(vorschlag)


def _protokoll_speichern(db: Session, **werte) -> None:
    """Schreibt eine neue FinderLauf-Zeile. Läuft in einer eigenen kleinen
    Transaktion - wird nach einem db.rollback() im Hauptteil aufgerufen,
    braucht also eine saubere Session, keine, in der noch ein gescheiterter
    Schreibvorgang hängt."""
    eintrag = FinderLauf(beendet_am=datetime.datetime.utcnow(), **werte)
    db.add(eintrag)
    db.commit()


def taeglicher_lauf(
    db: Session, *, client: anthropic.Anthropic | None = None, ignoriere_cache: bool = False
) -> dict[str, int]:
    """Führt einen kompletten Lauf aus und gibt Zähler zurück (fürs Logging
    und den manuellen "Jetzt suchen"-Button im Vorschläge-Tab). Wirft nie -
    ein unerwarteter Fehler wird abgefangen, zurückgerollt und als
    nicht erfolgreicher Lauf protokolliert, statt die aufrufende Seite
    (Scheduler-Job oder "Jetzt suchen") abstürzen zu lassen.

    ignoriere_cache=True (Button "Alle neu analysieren") überspringt den
    Rohtext-Cache komplett: jeder aktuell gelistete Fund wird erneut per KI
    geprüft, auch unverändert - und bestehende, noch offene Vorschläge werden
    mit dem frischen Ergebnis überschrieben statt nur ihren Status
    nachzuziehen. Kostet spürbar mehr API-Aufrufe als ein normaler Lauf,
    deshalb nur auf ausdrücklichen Nutzerwunsch (Bestätigungsdialog)."""
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

    _nicht_mehr_anwendbare_vorschlaege_bereinigen(db, inhaber_liste)

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

            # Sobald für diese Quelle-URL schon mindestens ein Vorschlag
            # existiert (für irgendeinen Inhaber, egal welcher Status), gilt
            # sie bewusst als endgültig geprüft: geringfügig schwankender
            # Rohtext derselben URL (z.B. Kommentar-/Bewertungszahlen im
            # RSS-Feed) löst dann keine erneute KI-Extraktion mehr aus - auch
            # nicht bei einer echten Änderung von Prämie oder Bedingungen.
            # Bewusste Entscheidung gegen zusätzliche API-Kosten und
            # Duplikate zulasten davon, eine spätere echte Änderung am Deal
            # nicht mehr mitzubekommen. "Alle neu analysieren" (ignoriere_cache)
            # überstimmt das weiterhin gezielt.
            bereits_vorgeschlagen = (
                not ignoriere_cache
                and db.query(DealVorschlag.id).filter(DealVorschlag.quelle_url == fund.quelle_url).first() is not None
            )

            aus_cache = False
            extrahiert: AngebotExtraktion | None = None

            if not ignoriere_cache and cache_eintrag is not None and (
                cache_eintrag.rohtext_hash == rohtext_hash or bereits_vorgeschlagen
            ):
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
                # Depot, Kinderkonto) - umgekehrt einem Erwachsenen ein
                # Kinderdeal nur, wenn er nicht ausschließlich für Kinder ist
                # (_ist_anwendbar, symmetrisch). Die meisten Neukunden-Prämien
                # setzen Volljährigkeit voraus - steht nichts im Text, gilt
                # der Deal als reines Erwachsenen-Angebot
                # (extrahiert.fuer_kinder=False), und das Kind erscheint gar
                # nicht erst als Auswahl (und umgekehrt bei einem echten
                # Kinderdeal die Erwachsenen nicht). Beide Seiten lassen sich
                # im "Für wen übernehmen?"-Dialog trotzdem manuell ergänzen
                # (siehe routers/vorschlaege.py). Existiert für diesen
                # Inhaber schon eine offene Zeile (z.B. aus einer Zeit vor
                # dieser Prüfung), wird sie hier automatisch gelöscht statt
                # für immer offen zu bleiben
                # (_nicht_anwendbaren_vorschlag_entfernen).
                if not _ist_anwendbar(inhaber.ist_minderjaehrig, extrahiert.fuer_kinder):
                    _nicht_anwendbaren_vorschlag_entfernen(db, fund.quelle_url, inhaber.id)
                    continue
                match = matching.bewerten(db, fund, extrahiert, inhaber, config.MINDESTPRAEMIE)
                bestehend = matching.bestehenden_vorschlag_finden(
                    db, fund.quelle_url, inhaber.id, match.inhalt_hash
                )
                if bestehend is not None:
                    if bestehend.status not in matching.STATUS_OFFEN:
                        # Bereits vom Nutzer übernommen oder verworfen -
                        # bleibt in jedem Fall unangetastet.
                        continue
                    if ignoriere_cache:
                        # Erzwungene Neuprüfung: die Zeile komplett mit dem
                        # frischen Ergebnis überschreiben, auch wenn sich der
                        # Inhalts-Hash nicht geändert hat (z.B. weil jetzt
                        # erstmals eine Prämien-Aufschlüsselung erkannt wurde).
                        _vorschlag_felder_setzen(bestehend, extrahiert, match)
                        zaehler["aktualisiert"] += 1
                        aktualisiert_fuer_fund = True
                        zaehler[match.status] = zaehler.get(match.status, 0) + 1
                    elif bestehend.status != match.status:
                        # Gleicher Inhalt wie zuvor - i.d.R. nichts zu tun.
                        # Nur wenn sich die Bewertung rein durch Zeitablauf
                        # geändert hat (z.B. eine Sperrfrist ist inzwischen
                        # erreicht, ohne dass sich am Angebot etwas geändert
                        # hätte), wird die Zeile nachgezogen.
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
                    inhalt_hash=match.inhalt_hash,
                )
                _vorschlag_felder_setzen(vorschlag, extrahiert, match)
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
        dealdoktor_geladen=len(quellen.dealdoktor_funde),
        mydealz_neu=kategorie["mydealz"]["neu"],
        mydealz_vorhanden=kategorie["mydealz"]["vorhanden"],
        mydealz_aktualisiert=kategorie["mydealz"]["aktualisiert"],
        mydealz_rauschen=kategorie["mydealz"]["rauschen"],
        spartanien_neu=kategorie["spartanien"]["neu"],
        spartanien_vorhanden=kategorie["spartanien"]["vorhanden"],
        spartanien_aktualisiert=kategorie["spartanien"]["aktualisiert"],
        spartanien_rauschen=kategorie["spartanien"]["rauschen"],
        dealdoktor_neu=kategorie["dealdoktor"]["neu"],
        dealdoktor_vorhanden=kategorie["dealdoktor"]["vorhanden"],
        dealdoktor_aktualisiert=kategorie["dealdoktor"]["aktualisiert"],
        dealdoktor_rauschen=kategorie["dealdoktor"]["rauschen"],
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
                geraete=config.NOTIFY_GERAETE,
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


_lauf_lock = threading.Lock()
_lauf_status: dict[str, object] = {"laeuft": False, "gestartet_am": None}


def lauf_status() -> tuple[bool, datetime.datetime | None]:
    """Ob gerade ein Lauf aktiv ist (Button-Klick oder der 06:00-Job) und
    wann er gestartet wurde - für die Live-Anzeige im Vorschläge-Tab ("Suche
    läuft ..."), da ein Lauf je nach Anzahl der Funde eine Weile dauern kann
    und sonst kein Feedback sichtbar wäre."""
    with _lauf_lock:
        return bool(_lauf_status["laeuft"]), _lauf_status["gestartet_am"]


def _lauf_beginnen() -> bool:
    """Markiert den Start eines Laufs. Liefert False, wenn schon einer aktiv
    ist - kein zweiter parallel, sonst konkurrierende Schreibzugriffe auf
    dieselbe SQLite-Datenbank durch zwei gleichzeitige Läufe."""
    with _lauf_lock:
        if _lauf_status["laeuft"]:
            return False
        _lauf_status["laeuft"] = True
        _lauf_status["gestartet_am"] = datetime.datetime.utcnow()
        return True


def _lauf_beenden() -> None:
    with _lauf_lock:
        _lauf_status["laeuft"] = False


def lauf_im_hintergrund_starten(*, ignoriere_cache: bool = False) -> bool:
    """Startet taeglicher_lauf() in einem eigenen Thread mit eigener Session,
    statt den auslösenden Request ("Jetzt suchen"/"Alle neu analysieren")
    bis zu einer Minute oder länger zu blockieren. Liefert False (kein neuer
    Thread gestartet), wenn bereits ein Lauf aktiv ist - egal ob durch einen
    der beiden Buttons oder den 06:00-Job."""
    if not _lauf_beginnen():
        return False

    def _ausfuehren() -> None:
        try:
            with SessionLocal() as db:
                taeglicher_lauf(db, ignoriere_cache=ignoriere_cache)
        except Exception:
            # taeglicher_lauf() faengt eigene Fehler bereits ab und
            # protokolliert sie (siehe Docstring dort) - dieser Fang ist nur
            # ein zusaetzliches Netz, falls z.B. schon SessionLocal() selbst
            # scheitert.
            logger.exception("Hintergrund-Lauf fehlgeschlagen.")
        finally:
            _lauf_beenden()

    threading.Thread(target=_ausfuehren, daemon=True, name="ki-deal-finder-lauf").start()
    return True


def geplanter_lauf() -> None:
    """Einstiegspunkt für den APScheduler-Job (main.py) - öffnet eine eigene
    Session, da der Job außerhalb eines Requests läuft. Markiert sich
    ebenfalls über lauf_status(), damit ein zeitgleicher Klick auf "Jetzt
    suchen" nicht parallel gegen dieselbe Datenbank schreibt."""
    if not _lauf_beginnen():
        logger.warning("Geplanter Lauf übersprungen - es läuft bereits ein anderer Lauf.")
        return
    try:
        with SessionLocal() as db:
            taeglicher_lauf(db)
    finally:
        _lauf_beenden()
