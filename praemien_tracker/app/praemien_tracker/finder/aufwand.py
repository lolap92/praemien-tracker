"""Aufwand eines Vorschlags als Punktewert von 1 bis 5.

Jede Bedingung wird anhand ihres Textes einer Stufe zugeordnet; der Vorschlag
bekommt die höchste Stufe seiner Bedingungen - die aufwendigste Auflage
bestimmt, was man insgesamt tun muss.

  1  Nur eröffnen      Neukunde sein, online eröffnen, App aktivieren …
  2  Geld überweisen   Mindesteinzahlung, Geldeingang, Dauerauftrag, Einlage …
  3  Karte einsetzen   Kartenzahlungen, Kartenumsatz, Apple Pay …
  4  Wertpapiere       Aktien-/ETF-Kauf, Sparplan, Trade, Depotübertrag
  5  Gehaltseingang    Eingang von Gehalt, Lohn, Rente, BAföG, Einkommen

Bewusst fester, deterministischer Code statt einer KI-Einschätzung (wie
matching.einkommen_gefordert): wirkt sofort auf alle vorhandenen Vorschläge,
ohne Neuanalyse und ohne API-Kosten, und ist nachvollziehbar.

Nennt eine Bedingung Alternativen ("Dazu zählen Gehaltseingänge,
Kartenzahlungen oder Lastschriften", "z. B. ..."), zählt die einfachste
genannte Möglichkeit - man kann sich ja den leichtesten Weg aussuchen. Sonst
zählt die höchste. Eine Bedingung ohne erkennbares Stichwort ("Neukunde
sein", "Kreditkarte beantragen") gilt als Stufe 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .matching import _EINKOMMEN_MUSTER, einkommen_gefordert

STUFE_EROEFFNEN = 1
STUFE_GELD = 2
STUFE_KARTE = 3
STUFE_WERTPAPIERE = 4
STUFE_GEHALT = 5
HOECHSTE_STUFE = STUFE_GEHALT

STUFEN_LABELS = {
    STUFE_EROEFFNEN: "Nur eröffnen",
    STUFE_GELD: "Geld überweisen",
    STUFE_KARTE: "Karte einsetzen",
    STUFE_WERTPAPIERE: "Wertpapiere kaufen",
    STUFE_GEHALT: "Gehaltseingang",
}

_WERTPAPIER_MUSTER = re.compile(
    r"(?<!gratis)aktie|wertpapier|sparplan|\betfs?\b|\btrades?\b|\btraden|\border(n|s)?\b"
    r"|depot\s*(ü|ue)bertrag|depotwechsel|\bfonds|krypto|anleihe|zertifikat|derivat",
    re.IGNORECASE,
)
# Karte muss *eingesetzt* werden - "Kreditkarte beantragen" allein ist Stufe 1.
_KARTE_MUSTER = re.compile(
    r"karten(zahlung|umsatz|umsätze|transaktion|einsatz)"
    r"|karte\w*\s+(\S+\s+){0,12}?(ein(zu)?setz|einsatz|nutz|zahl|bezahl|verwend)"
    r"|(einsatz|nutzung|verwendung)\s+(\S+\s+){0,3}?\w*karte"
    r"|\w*umsatz|\w*umsätze|einkäuf|einkauf|bezahl|apple\s*pay|google\s*pay|kontaktlos",
    re.IGNORECASE,
)
_GELD_MUSTER = re.compile(
    r"(ü|ue)berweis|einzahl|eingang|eingäng|einlage|guthaben|lastschrift|dauerauftr"
    r"|buchung|gutschrift|kontowechsel|transaktion|bargeld|(€|euro|eur)\s+(\S+\s+){0,3}?anleg|aktiv\s+(zu\s+)?nutz",
    re.IGNORECASE,
)
# Signalwörter für eine Aufzählung von Alternativen innerhalb einer Bedingung.
_ALTERNATIVEN_MUSTER = re.compile(
    r"\boder\b|\bz\.\s*b\.|beispielsweise|\betwa\b|dazu\s+zählen|zählen\s+(u\.\s*a\.\s*)?auch|wahlweise|alternativ|entweder",
    re.IGNORECASE,
)


def bedingung_stufe(beschreibung: str) -> int:
    """Aufwandsstufe (1-5) einer einzelnen Bedingung aus ihrem Text."""
    text = beschreibung or ""
    treffer: set[int] = set()
    if einkommen_gefordert(text):
        treffer.add(STUFE_GEHALT)
    # Einkommenswörter ausblenden, damit "Gehaltseingang" nicht zusätzlich
    # als "Eingang" (Stufe 2) zählt und eine Aufzählung wie "Gehalt, Rente
    # oder ähnlich" nicht auf Stufe 2 herunterrutscht.
    rest = _EINKOMMEN_MUSTER.sub(" ", text)
    if _WERTPAPIER_MUSTER.search(rest):
        treffer.add(STUFE_WERTPAPIERE)
    if _KARTE_MUSTER.search(rest):
        treffer.add(STUFE_KARTE)
    if _GELD_MUSTER.search(rest):
        treffer.add(STUFE_GELD)
    if not treffer:
        return STUFE_EROEFFNEN
    if len(treffer) > 1 and _ALTERNATIVEN_MUSTER.search(text):
        return min(treffer)
    return max(treffer)


@dataclass(frozen=True)
class Aufwand:
    stufe: int
    label: str
    hoechste: int = HOECHSTE_STUFE


def aufwand(bedingungen: Iterable) -> Aufwand:
    """Aufwand eines Vorschlags: höchste Stufe seiner Bedingungen (Objekte mit
    .beschreibung). Ohne Bedingungen bleibt nur die Eröffnung - Stufe 1."""
    stufe = max((bedingung_stufe(b.beschreibung) for b in bedingungen), default=STUFE_EROEFFNEN)
    return Aufwand(stufe=stufe, label=STUFEN_LABELS[stufe])
