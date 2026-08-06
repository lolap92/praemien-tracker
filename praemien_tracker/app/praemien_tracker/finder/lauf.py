"""Orchestriert den täglichen Lauf: Quellen abfragen, extrahieren, bewerten,
speichern, benachrichtigen (Konzept Abschnitt 6).

Jeder gefundene, thematisch passende Fund wird für *jeden* Inhaber als eigene
Zeile gespeichert und angezeigt - auch bei Nichterfüllung. Nichts wird
stillschweigend verworfen (zentrale Idee des Konzepts).

Jeder Aufruf von taeglicher_lauf() schreibt am Ende immer eine FinderLauf-
Zeile (models.py) - Grundlage für die Statusanzeige im Vorschläge-Tab:
erfolgreich?, wie viele Funde je Quelle, wie viele neu, welche Fehler.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

import anthropic
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import DealVorschlag, FinderLauf, Inhaber, VorschlagBedingung
from . import extraktion, matching, notify
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
    if not config.ANTHROPIC_API_KEY:
        logger.warning("Kein Anthropic-API-Key hinterlegt (Add-on-Optionen) - KI-Deal-Finder übersprungen.")
        return None
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


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
        "gefunden": 0,
        matching.STATUS_VORGESCHLAGEN: 0,
        matching.STATUS_ZU_PRUEFEN: 0,
        matching.STATUS_ABGELEHNT: 0,
        "uebersprungen": 0,
    }

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
        for fund in quellen.alle:
            try:
                relevant = extraktion.ist_relevantes_angebot(aktiver_client, fund.text, model=config.ANTHROPIC_MODEL)
            except Exception as exc:
                logger.exception("Themen-Check für %s fehlgeschlagen, Fund wird übersprungen.", fund.quelle_url)
                fehlermeldungen.append(f"Themen-Check für {fund.quelle_url}: {exc}")
                zaehler["uebersprungen"] += 1
                continue
            if not relevant:
                continue

            try:
                extrahiert = extraktion.extrahiere_angebot(aktiver_client, fund.text, model=config.ANTHROPIC_MODEL)
            except Exception as exc:
                logger.exception("Struktur-Extraktion für %s fehlgeschlagen, Fund wird übersprungen.", fund.quelle_url)
                fehlermeldungen.append(f"Extraktion für {fund.quelle_url}: {exc}")
                zaehler["uebersprungen"] += 1
                continue
            if extrahiert is None:
                fehlermeldungen.append(f"Extraktion für {fund.quelle_url} lieferte kein Ergebnis.")
                zaehler["uebersprungen"] += 1
                continue

            # Pro Inhaber eine eigene Zeile, weil Sperrfrist- und Neukunden-
            # Prüfung je Inhaber unterschiedlich ausfallen kann (Konzept
            # Abschnitt 5).
            for inhaber in inhaber_liste:
                match = matching.bewerten(db, fund, extrahiert, inhaber, config.MINDESTPRAEMIE)
                if matching.ist_duplikat(db, fund.quelle_url, inhaber.id, match.inhalt_hash):
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
                zaehler[match.status] = zaehler.get(match.status, 0) + 1

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
        neu_gefunden=zaehler["gefunden"],
        uebersprungen=zaehler["uebersprungen"],
        fehler="; ".join(fehlermeldungen) or None,
    )

    # Rein automatisch abgelehnte Funde lösen bewusst keine Benachrichtigung
    # aus - nur vorgeschlagen und zu_pruefen (Konzept Abschnitt 6, Schritt 7).
    zu_benachrichtigen = zaehler[matching.STATUS_VORGESCHLAGEN] + zaehler[matching.STATUS_ZU_PRUEFEN]
    if zu_benachrichtigen:
        try:
            notify.benachrichtigen(zaehler[matching.STATUS_VORGESCHLAGEN], zaehler[matching.STATUS_ZU_PRUEFEN])
        except Exception:
            logger.exception("HA-Benachrichtigung fehlgeschlagen.")

    logger.info(
        "KI-Deal-Finder-Lauf abgeschlossen: %d gefunden (%d vorgeschlagen, %d zu prüfen, %d abgelehnt, %d übersprungen).",
        zaehler["gefunden"],
        zaehler[matching.STATUS_VORGESCHLAGEN],
        zaehler[matching.STATUS_ZU_PRUEFEN],
        zaehler[matching.STATUS_ABGELEHNT],
        zaehler["uebersprungen"],
    )
    return zaehler


def geplanter_lauf() -> None:
    """Einstiegspunkt für den APScheduler-Job (main.py) - öffnet eine eigene
    Session, da der Job außerhalb eines Requests läuft."""
    with SessionLocal() as db:
        taeglicher_lauf(db)
