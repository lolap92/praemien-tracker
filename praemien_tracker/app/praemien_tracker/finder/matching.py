"""Deterministische Prüfung der von der KI extrahierten Angaben gegen die
Kriterien und die bestehenden Deals - gewöhnlicher, nachvollziehbarer
Python-Code, keine KI-Entscheidung (Konzept Abschnitt 6, Schritt 5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from .. import derived
from ..models import Bank, Deal, DealVorschlag, Inhaber
from .extraktion import AngebotExtraktion
from .quellen import RohFund

STATUS_VORGESCHLAGEN = "vorgeschlagen"
STATUS_ZU_PRUEFEN = "zu_pruefen"
STATUS_ABGELEHNT = "automatisch_abgelehnt"
STATUS_UEBERNOMMEN = "uebernommen"
STATUS_VERWORFEN = "verworfen"

# Noch nicht vom Nutzer entschieden - im Unterschied zu uebernommen/verworfen
# darf lauf.py diese Zeilen bei einer erneuten Bewertung noch verändern.
STATUS_OFFEN = (STATUS_VORGESCHLAGEN, STATUS_ZU_PRUEFEN, STATUS_ABGELEHNT)

# Feste Gründe für ein manuelles Verwerfen (Mehrfachauswahl im Dialog) -
# bewusst ein Enum statt Freitext, damit die Gründe später auswertbar bleiben
# (z.B. "wie oft wird wegen zu aufwendiger Bedingungen verworfen?").
VERWERFEN_GRUND_DUPLIKAT = "duplikat"
VERWERFEN_GRUND_BEDINGUNGEN = "bedingungen_aufwendig"
VERWERFEN_GRUND_NEUKUNDE = "noch_nicht_neukunde"
VERWERFEN_GRUENDE_LABELS = {
    VERWERFEN_GRUND_DUPLIKAT: "Duplikat",
    VERWERFEN_GRUND_BEDINGUNGEN: "Bedingungen zu aufwendig",
    VERWERFEN_GRUND_NEUKUNDE: "Noch nicht wieder Neukunde",
}
VERWERFEN_GRUENDE = tuple(VERWERFEN_GRUENDE_LABELS)

EINSCHAETZUNG_ERFUELLT = "erfuellt"
EINSCHAETZUNG_ZU_PRUEFEN = "zu_pruefen"
EINSCHAETZUNG_NICHT_ERFUELLT = "nicht_erfuellt"


@dataclass(frozen=True)
class BedingungBewertung:
    beschreibung: str
    einschaetzung: str


@dataclass(frozen=True)
class PraemieBewertung:
    """Eine einzelne Teilprämie eines Angebots (Betrag, Geber, Voraussetzung) -
    nur zur Anzeige im Vorschlag. Die kanonische Quelle (spartanien/bank) für
    den späteren Deal steckt in roh_json."""

    betrag: Decimal
    geber: str | None
    bedingung: str | None


@dataclass(frozen=True)
class MatchErgebnis:
    """Ergebnis der Prüfung für einen Fund und einen Inhaber - alles, was
    lauf.py braucht, um daraus eine deal_vorschlaege-Zeile zu bauen."""

    status: str
    ablehnungsgruende: str | None
    praemie_betrag: Decimal
    sperrfrist_monate: int | None
    bedingungen: list[BedingungBewertung]
    praemien: list[PraemieBewertung]
    roh_json: str
    inhalt_hash: str


def _bank_finden(db: Session, bank_name: str) -> Bank | None:
    """Freitext-Bankname gegen bestehende Banken abgleichen (nur Groß-/
    Kleinschreibung und Randleerzeichen werden verziehen). Findet sich keine
    passende Bank, gilt der Inhaber für diese Bank automatisch als
    Neukunde - eine unscharfe Namenssuche wäre hier riskanter als ein
    verpasster Treffer, der stattdessen einfach zu einem echten neuen
    Bank-Datensatz beim Übernehmen führt."""
    ziel = bank_name.strip().lower()
    return next((b for b in db.query(Bank).all() if b.name.strip().lower() == ziel), None)


def _sperrfrist_pruefen(
    db: Session, bank: Bank | None, kontoart: str, inhaber_id: int, sperrfrist_monate: int | None
) -> tuple[str, str | None]:
    """Neukunden-/Sperrfrist-Kriterium prüfen. Liefert (einschaetzung, grund),
    grund ist None bei "erfuellt"."""
    if bank is None:
        return EINSCHAETZUNG_ERFUELLT, None

    # Stornierte Deals zählen nicht als "war schon Kunde" - sie sind nie
    # zustande gekommen (siehe models.Deal.storniert).
    bestehende = [
        d
        for d in db.query(Deal).filter(
            Deal.bank_id == bank.id, Deal.inhaber_id == inhaber_id, Deal.storniert.is_(False)
        )
        if d.kontoart.strip().lower() == kontoart.strip().lower()
    ]
    if not bestehende:
        return EINSCHAETZUNG_ERFUELLT, None

    aktiv = [d for d in bestehende if not d.gekuendigt]
    if aktiv:
        return (
            EINSCHAETZUNG_NICHT_ERFUELLT,
            f"Ist bei {bank.name} ({kontoart}) bereits Kundin/Kunde, kein gekündigter Deal vorhanden.",
        )

    monate_werte = [d.gekuendigt_im_monat for d in bestehende if d.gekuendigt_im_monat]
    if not monate_werte:
        return (
            EINSCHAETZUNG_ZU_PRUEFEN,
            f"Bereits Kundin/Kunde bei {bank.name} ({kontoart}), Kündigungsmonat nicht erfasst.",
        )

    letzter_monat = max(monate_werte)
    kuendigungsdatum = derived.parse_monat(letzter_monat)
    if kuendigungsdatum is None:
        return (
            EINSCHAETZUNG_ZU_PRUEFEN,
            f"Bereits Kundin/Kunde bei {bank.name} ({kontoart}), Kündigungsmonat nicht lesbar.",
        )

    if sperrfrist_monate is None:
        return (
            EINSCHAETZUNG_ZU_PRUEFEN,
            f"Bereits Kundin/Kunde bei {bank.name} ({kontoart}) (gekündigt {letzter_monat}) - "
            "im Angebotstext keine erkennbare Sperrfrist.",
        )

    vergangen = derived.monate_seit_kuendigung(kuendigungsdatum)
    if vergangen >= sperrfrist_monate:
        return EINSCHAETZUNG_ERFUELLT, None
    return (
        EINSCHAETZUNG_NICHT_ERFUELLT,
        f"Sperrfrist von {sperrfrist_monate} Monaten noch nicht erreicht "
        f"(gekündigt {letzter_monat}, davon {vergangen} Monate vergangen).",
    )


def _inhalt_hash(
    bank_name: str,
    kontoart: str,
    praemie_betrag: Decimal,
    sperrfrist_monate: int | None,
    bedingungen: list[BedingungBewertung],
) -> str:
    """Fachlich relevante Felder zu einem stabilen Hash - Grundlage der
    Dedup-Prüfung. Ändert sich einer dieser Werte (z.B. eine höhere Prämie),
    entsteht bewusst ein neuer Datensatz statt eines stillen Updates, damit
    die Historie nachvollziehbar bleibt."""
    nutzlast = {
        "bank_name": bank_name.strip().lower(),
        "kontoart": kontoart.strip().lower(),
        "praemie_betrag": str(praemie_betrag),
        "sperrfrist_monate": sperrfrist_monate,
        "bedingungen": sorted((b.beschreibung.strip().lower(), b.einschaetzung) for b in bedingungen),
    }
    rohtext = json.dumps(nutzlast, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(rohtext.encode("utf-8")).hexdigest()


def _praemie_betrag(wert: float) -> Decimal:
    try:
        return Decimal(str(round(wert, 2)))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _quelle_aus_geber(geber: str | None, fund_quelle: str) -> str:
    """Freitext-Geber ("Spartanien", "Santander", ...) auf die kanonische
    Quelle (spartanien/bank) abbilden. Nur Spartanien selbst zahlt als
    "spartanien"; alles andere (die eigentliche Bank) ist "bank"."""
    if geber and "spartanien" in geber.strip().lower():
        return "spartanien"
    return "bank"


def _teilpraemien(extraktion: AngebotExtraktion, fund_quelle: str) -> list[PraemieBewertung]:
    """Aus der Extraktion die Teilprämien für die Anzeige ableiten. Liefert die
    KI eine Aufteilung, wird sie übernommen; sonst eine einzelne Prämie über
    die Gesamtsumme (Geber/Bedingung dann unbekannt)."""
    if extraktion.praemien:
        return [
            PraemieBewertung(_praemie_betrag(p.betrag), (p.geber or "").strip() or None, (p.wofuer or "").strip() or None)
            for p in extraktion.praemien
        ]
    return [PraemieBewertung(_praemie_betrag(extraktion.praemie_betrag), None, None)]


def bewerten(
    db: Session,
    fund: RohFund,
    extraktion: AngebotExtraktion,
    inhaber: Inhaber,
    mindestpraemie: Decimal,
) -> MatchErgebnis:
    """Ein extrahiertes Angebot für einen Inhaber bewerten (Konzept
    Abschnitt 6, Schritt 5)."""
    teilpraemien = _teilpraemien(extraktion, fund.quelle)
    praemie_betrag = sum((p.betrag for p in teilpraemien), Decimal("0"))
    # Zwei getrennte Listen, keine gemeinsame: eine eindeutig verfehlte
    # Bedingung lehnt automatisch ab, eine unklare macht nur "zu prüfen" -
    # im Zweifel wird lieber vorgeschlagen als ausgeschlossen (Konzept,
    # zentrale Idee). Beides in eine Liste zu werfen würde "zu prüfen" nicht
    # von "abgelehnt" unterscheidbar machen.
    ablehnung_gruende: list[str] = []
    unklar_gruende: list[str] = []

    # 1) Mindestprämie - deterministisch, kein Teil der Bedingungen-Liste.
    if praemie_betrag < mindestpraemie:
        ablehnung_gruende.append(f"Prämie {praemie_betrag} € liegt unter der Mindestprämie von {mindestpraemie} €.")

    # 2) Neukunden-/Sperrfrist-Check.
    bank = _bank_finden(db, extraktion.bank_name)
    sperrfrist_einschaetzung, sperrfrist_grund = _sperrfrist_pruefen(
        db, bank, extraktion.kontoart, inhaber.id, extraktion.sperrfrist_monate
    )
    if sperrfrist_einschaetzung == EINSCHAETZUNG_NICHT_ERFUELLT:
        ablehnung_gruende.append(sperrfrist_grund)
    elif sperrfrist_einschaetzung == EINSCHAETZUNG_ZU_PRUEFEN:
        unklar_gruende.append(sperrfrist_grund)

    # 3) Von der KI erkannte Einzel-Bedingungen (können mehrere sein - siehe
    # VorschlagBedingung in models.py).
    bedingungen = [
        BedingungBewertung(b.beschreibung.strip(), b.einschaetzung) for b in extraktion.bedingungen
    ]
    for b in bedingungen:
        if b.einschaetzung == EINSCHAETZUNG_NICHT_ERFUELLT:
            ablehnung_gruende.append(f"Bedingung nicht erfüllbar: {b.beschreibung}")
        elif b.einschaetzung == EINSCHAETZUNG_ZU_PRUEFEN:
            unklar_gruende.append(f"Bedingung unklar: {b.beschreibung}")

    if ablehnung_gruende:
        status = STATUS_ABGELEHNT
        gruende = ablehnung_gruende
    elif unklar_gruende:
        status = STATUS_ZU_PRUEFEN
        gruende = unklar_gruende
    else:
        status = STATUS_VORGESCHLAGEN
        gruende = []

    # Herkunft je Teilprämie: Spartanien zahlt als "spartanien", die
    # eigentliche Bank als "bank" (das Kernmodell kennt nur diese zwei
    # Quellen). Ohne KI-Aufteilung fällt alles auf die Fund-Quelle zurück.
    if extraktion.praemien:
        praemien_json = [
            {"quelle": _quelle_aus_geber(p.geber, fund.quelle), "betrag": str(p.betrag), "erhalten": False}
            for p in teilpraemien
        ]
    else:
        fallback_quelle = "spartanien" if fund.quelle == "spartanien" else "bank"
        praemien_json = [{"quelle": fallback_quelle, "betrag": str(praemie_betrag), "erhalten": False}]
    roh_json = json.dumps(
        {
            "bank": extraktion.bank_name.strip(),
            "kontoart": extraktion.kontoart.strip(),
            "inhaber": inhaber.name,
            "praemien": praemien_json,
            "bedingungen": [
                {"beschreibung": b.beschreibung, "erfuellt": b.einschaetzung == EINSCHAETZUNG_ERFUELLT}
                for b in bedingungen
            ],
            "urls": [{"url": fund.quelle_url, "bezeichnung": f"{fund.quelle}-Angebot"}],
        },
        ensure_ascii=False,
    )

    return MatchErgebnis(
        status=status,
        ablehnungsgruende="; ".join(gruende) or None,
        praemie_betrag=praemie_betrag,
        sperrfrist_monate=extraktion.sperrfrist_monate,
        bedingungen=bedingungen,
        praemien=teilpraemien,
        roh_json=roh_json,
        inhalt_hash=_inhalt_hash(
            extraktion.bank_name, extraktion.kontoart, praemie_betrag, extraktion.sperrfrist_monate, bedingungen
        ),
    )


def bestehenden_vorschlag_finden(
    db: Session, quelle_url: str, inhaber_id: int, inhalt_hash: str
) -> DealVorschlag | None:
    """Liefert den Vorschlag mit identischem Inhalt (gleicher Hash) für diese
    Quelle+Inhaber, falls vorhanden - unabhängig von dessen Status (auch ein
    bereits übernommener oder verworfener zählt). Bei geänderten Daten
    (anderer Hash, z.B. eine höhere Prämie) greift diese Prüfung bewusst
    nicht: dann liefert sie None und es entsteht ein neuer Datensatz.

    Ein Treffer heißt nicht zwangsläufig "nichts zu tun" - lauf.py nutzt ihn
    auch, um den Status einer bestehenden, noch offenen Zeile nachzuziehen,
    wenn sich die Bewertung rein durch Zeitablauf geändert hat (z.B. eine
    Sperrfrist ist inzwischen erreicht, obwohl sich am Angebot selbst nichts
    geändert hat und deshalb kein neuer API-Aufruf nötig war)."""
    return (
        db.query(DealVorschlag)
        .filter(
            DealVorschlag.quelle_url == quelle_url,
            DealVorschlag.inhaber_id == inhaber_id,
            DealVorschlag.inhalt_hash == inhalt_hash,
        )
        .first()
    )
