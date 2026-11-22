"""Aufwand eines Vorschlags als Punktewert von 1 bis 5.

Jede Bedingung wird anhand ihres Textes einer Stufe zugeordnet; der Vorschlag
bekommt die höchste Stufe seiner Bedingungen - die aufwendigste Auflage
bestimmt, was man insgesamt tun muss.

  1  Nur eröffnen      Neukunde sein, online eröffnen, App aktivieren …
  2  Geld überweisen   Mindesteinzahlung, Geldeingang, Dauerauftrag, Einlage …
  3  Karte einsetzen   Kartenzahlungen, Kartenumsatz, Apple Pay …
  4  Wertpapiere       Aktien-/ETF-Kauf, Sparplan, Trade, Depotübertrag
  4  Kontowechsel      Kontowechselservice/Kontoumzug nutzen - zieht
                       Daueraufträge, Lastschriften und Gehalt ums Konto um
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


@dataclass(frozen=True)
class Kategorie:
    """Art einer Bedingung: Stufe für die Punkte, Label fürs Etikett. Zwei
    Kategorien können dieselbe Stufe haben (Wertpapiere, Kontowechsel)."""

    stufe: int
    label: str


EROEFFNEN = Kategorie(STUFE_EROEFFNEN, "Nur eröffnen")
GELD = Kategorie(STUFE_GELD, "Geld überweisen")
KARTE = Kategorie(STUFE_KARTE, "Karte einsetzen")
WERTPAPIERE = Kategorie(STUFE_WERTPAPIERE, "Wertpapiere kaufen")
# Gleich aufwendig wie Wertpapiere: Der Wechselservice zieht Daueraufträge,
# Lastschriften und Gehaltseingang aufs neue Konto um - das muss man nach dem
# Prämien-Deal alles wieder zurückholen.
KONTOWECHSEL = Kategorie(STUFE_WERTPAPIERE, "Kontowechselservice")
GEHALT = Kategorie(STUFE_GEHALT, "Gehaltseingang")

_KONTOWECHSEL_MUSTER = re.compile(
    r"konto\s*-?\s*wechsel|wechsel\s*-?\s*(service|hilfe|assistent)|konto\s*-?\s*umzug|umzugs\s*-?\s*service",
    re.IGNORECASE,
)
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
    r"|buchung|gutschrift|transaktion|bargeld|(€|euro|eur)\s+(\S+\s+){0,3}?anleg|aktiv\s+(zu\s+)?nutz",
    re.IGNORECASE,
)
# Signalwörter für eine Aufzählung von Alternativen innerhalb einer Bedingung.
_ALTERNATIVEN_MUSTER = re.compile(
    r"\boder\b|\bz\.\s*b\.|beispielsweise|\betwa\b|dazu\s+zählen|zählen\s+(u\.\s*a\.\s*)?auch|wahlweise|alternativ|entweder",
    re.IGNORECASE,
)


def bedingung_kategorie(beschreibung: str) -> Kategorie:
    """Kategorie (und damit Aufwandsstufe 1-5) einer Bedingung aus ihrem Text."""
    text = beschreibung or ""
    treffer: list[Kategorie] = []
    if einkommen_gefordert(text):
        treffer.append(GEHALT)
    # Einkommenswörter ausblenden, damit "Gehaltseingang" nicht zusätzlich
    # als "Eingang" (Stufe 2) zählt und eine Aufzählung wie "Gehalt, Rente
    # oder ähnlich" nicht auf Stufe 2 herunterrutscht.
    rest = _EINKOMMEN_MUSTER.sub(" ", text)
    if _KONTOWECHSEL_MUSTER.search(rest):
        treffer.append(KONTOWECHSEL)
        # "Kontowechselservice nutzen, Daueraufträge umziehen" ist eine
        # Auflage, nicht zusätzlich "Geld überweisen" als Alternative.
        rest = _KONTOWECHSEL_MUSTER.sub(" ", rest)
    if _WERTPAPIER_MUSTER.search(rest):
        treffer.append(WERTPAPIERE)
    if _KARTE_MUSTER.search(rest):
        treffer.append(KARTE)
    if _GELD_MUSTER.search(rest) and not (KONTOWECHSEL in treffer and len(treffer) == 1):
        treffer.append(GELD)
    if not treffer:
        return EROEFFNEN
    if len(treffer) > 1 and _ALTERNATIVEN_MUSTER.search(text):
        return min(treffer, key=lambda k: k.stufe)
    return max(treffer, key=lambda k: k.stufe)


def bedingung_stufe(beschreibung: str) -> int:
    """Aufwandsstufe (1-5) einer einzelnen Bedingung aus ihrem Text."""
    return bedingung_kategorie(beschreibung).stufe


@dataclass(frozen=True)
class Aufwand:
    stufe: int
    label: str
    hoechste: int = HOECHSTE_STUFE


def aufwand(bedingungen: Iterable) -> Aufwand:
    """Aufwand eines Vorschlags: höchste Stufe seiner Bedingungen (Objekte mit
    .beschreibung). Ohne Bedingungen bleibt nur die Eröffnung - Stufe 1."""
    kategorie = max((bedingung_kategorie(b.beschreibung) for b in bedingungen), key=lambda k: k.stufe, default=EROEFFNEN)
    return Aufwand(stufe=kategorie.stufe, label=kategorie.label)


# --- Zweite Einstufung: Kontoführungsgebühren -------------------------------
#
#   1  Kostenlos    keine Gebühr
#   2  Vermeidbar   Gebühr entfällt bei regelmäßiger Aktivität (Geldeingang …)
#   3  Fest         Gebühr fällt in jedem Fall an
#
# Anders als der Aufwand kommt das nicht aus Stichwörtern, sondern direkt aus
# der KI-Extraktion (DealVorschlag.kontofuehrung): Gebühren stehen selten als
# Bedingung im Text, sondern im Fließtext oder Kleingedruckten.

GEBUEHREN_STUFEN = {"kostenlos": 1, "vermeidbar": 2, "fest": 3}
GEBUEHREN_LABELS = {"kostenlos": "Kostenlos", "vermeidbar": "Vermeidbar", "fest": "Feste Gebühr"}
GEBUEHREN_HOECHSTE = 3


@dataclass(frozen=True)
class Gebuehren:
    stufe: int | None  # None = nicht bekannt
    label: str
    hinweis: str | None
    hoechste: int = GEBUEHREN_HOECHSTE


def _euro(wert) -> str:
    return f"{wert:.2f}".replace(".", ",") + " €"


def gebuehren(vorschlag) -> Gebuehren:
    """Gebühren-Einstufung eines Vorschlags (Objekt mit kontofuehrung,
    kontofuehrung_euro_monat, kontofuehrung_hinweis)."""
    art = getattr(vorschlag, "kontofuehrung", None)
    if art not in GEBUEHREN_STUFEN:
        return Gebuehren(stufe=None, label="Unbekannt", hinweis=None)
    label = GEBUEHREN_LABELS[art]
    betrag = getattr(vorschlag, "kontofuehrung_euro_monat", None)
    if art != "kostenlos" and betrag:
        label += f" · {_euro(betrag)}/Monat"
    return Gebuehren(stufe=GEBUEHREN_STUFEN[art], label=label, hinweis=getattr(vorschlag, "kontofuehrung_hinweis", None))
