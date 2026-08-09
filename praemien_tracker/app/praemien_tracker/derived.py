"""Abgeleitete Sichten auf die gespeicherten Fakten.

Prinzip des Konzepts: Der Nutzer erfasst nur Fakten (models.py). Status,
Kennzahlen, ToDo-Liste und Vollständigkeit werden hier bei jedem Aufruf aus
diesen Fakten berechnet und nirgends gespeichert.
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Aufgabe, Deal

STATUS_BEDINGUNGEN = "bedingungen"
STATUS_PRAEMIE_WARTEN = "praemie_warten"
STATUS_WARTET_AUF_KUENDIGUNG = "wartet_auf_kuendigung"
STATUS_KUENDIGEN = "kuendigen"
STATUS_BESTAETIGUNG_WARTEN = "bestaetigung_warten"
STATUS_ABGESCHLOSSEN = "abgeschlossen"

STATUS_ORDER = [
    STATUS_BEDINGUNGEN,
    STATUS_PRAEMIE_WARTEN,
    STATUS_WARTET_AUF_KUENDIGUNG,
    STATUS_KUENDIGEN,
    STATUS_BESTAETIGUNG_WARTEN,
    STATUS_ABGESCHLOSSEN,
]

STATUS_LABELS = {
    STATUS_BEDINGUNGEN: "Bedingungen",
    STATUS_PRAEMIE_WARTEN: "Auf Prämie warten",
    STATUS_WARTET_AUF_KUENDIGUNG: "Auf Kündigung warten",
    STATUS_KUENDIGEN: "Kündigen",
    STATUS_BESTAETIGUNG_WARTEN: "Bestätigung warten",
    STATUS_ABGESCHLOSSEN: "Abgeschlossen",
}

STATUS_INDEX = {s: i for i, s in enumerate(STATUS_ORDER)}


def bedingungen_erfuellt(deal: Deal) -> bool:
    """Ein Deal gilt als 'Bedingungen erfüllt', wenn alle Bedingungen abgehakt
    sind oder keine hinterlegt sind."""
    return all(b.erfuellt for b in deal.bedingungen)


def alle_praemien_erhalten(deal: Deal) -> bool:
    """Ohne hinterlegte Prämien gilt ein Deal nicht als 'Prämie erhalten' -
    es gibt schlicht noch nichts zu erhalten, der Deal bleibt in Stufe 2."""
    if not deal.praemien:
        return False
    return all(p.erhalten for p in deal.praemien)


def ist_kuendbar(deal: Deal, heute: datetime.date | None = None) -> bool:
    """Ein leeres kuendbar_ab bedeutet *keine Sperrfrist* - gekündigt werden
    kann, sobald die Prämie da ist. Es heißt nicht "Datum unbekannt"."""
    heute = heute or datetime.date.today()
    return deal.kuendbar_ab is None or deal.kuendbar_ab <= heute


def status(deal: Deal) -> str:
    """Sechsstufige Pipeline (Konzept Abschnitt 6, erweitert um 'Auf
    Kündigung warten' für den Fall, dass alles erledigt ist, aber
    kuendbar_ab noch in der Zukunft liegt).

    Zwei Zustände sind *terminal* und werden vor allem anderen geprüft: ein
    stornierter Deal und ein gekündigter mit bestätigter Kündigung. Sonst
    galt ein längst abgeschlossener Deal wegen einer nie abgehakten Bedingung
    weiter als 'in Bearbeitung' - er stand gleichzeitig in der ToDo-Liste und
    in den Sperrfristen. Offene Bedingungen verschwinden dadurch nicht,
    sie erscheinen unter 'Zu prüfen' (siehe pruefpunkte).
    """
    if deal.storniert:
        return STATUS_ABGESCHLOSSEN
    if deal.gekuendigt and deal.kuendigung_bestaetigt:
        return STATUS_ABGESCHLOSSEN
    if not bedingungen_erfuellt(deal):
        return STATUS_BEDINGUNGEN
    if not alle_praemien_erhalten(deal):
        return STATUS_PRAEMIE_WARTEN
    if not deal.gekuendigt:
        if not ist_kuendbar(deal):
            return STATUS_WARTET_AUF_KUENDIGUNG
        return STATUS_KUENDIGEN
    return STATUS_BESTAETIGUNG_WARTEN


# --- Sperrfristen ---

SPERRFRIST_ROT = "rot"
SPERRFRIST_ORANGE = "orange"
SPERRFRIST_GRUEN = "gruen"


def parse_monat(wert: str | None) -> datetime.date | None:
    """Monatsangabe zum ersten Tag des Monats.

    Kanonisch ist ISO ('2026-07'); geschrieben wird nur dieses Format.
    Gelesen wird zusätzlich das frühere 'MM.YY' bzw. 'M.YY', damit ein nach
    der Umstellung übrig gebliebener Altwert - etwa aus einem eingespielten
    Backup - nicht lautlos als "kein Datum" gilt und der Deal aus der
    Sperrfristen-Auswertung fällt.
    """
    if not wert:
        return None
    text = wert.strip()

    if "-" in text:
        teile = text.split("-")
        if len(teile) != 2:
            return None
        try:
            jahr, monat = int(teile[0]), int(teile[1])
        except ValueError:
            return None
    elif "." in text:
        teile = text.split(".")
        if len(teile) != 2:
            return None
        try:
            monat, jahr = int(teile[0]), int(teile[1])
        except ValueError:
            return None
    else:
        return None

    if not (1 <= monat <= 12):
        return None
    if jahr < 100:
        jahr += 2000
    try:
        return datetime.date(jahr, monat, 1)
    except ValueError:
        return None


def format_monat(datum: datetime.date) -> str:
    """Kanonische Schreibweise für gespeicherte Monatsangaben."""
    return datum.strftime("%Y-%m")


# Alter Name, solange noch Aufrufer darauf zeigen.
parse_gekuendigt_monat = parse_monat


def monate_seit_kuendigung(kuendigungsdatum: datetime.date, heute: datetime.date | None = None) -> int:
    heute = heute or datetime.date.today()
    diff = (heute.year - kuendigungsdatum.year) * 12 + (heute.month - kuendigungsdatum.month)
    return max(0, diff)


def sperrfrist_stufe(monate: int) -> str:
    """< 6 Monate: rot · 6-12 Monate: orange · > 12 Monate: grün."""
    if monate < 6:
        return SPERRFRIST_ROT
    if monate <= 12:
        return SPERRFRIST_ORANGE
    return SPERRFRIST_GRUEN


@dataclass
class Kennzahlen:
    gesamt: Decimal
    erhalten: Decimal
    offen: Decimal


def kennzahlen(praemien) -> Kennzahlen:
    gesamt = sum((p.betrag for p in praemien), Decimal("0"))
    erhalten = sum((p.betrag for p in praemien if p.erhalten), Decimal("0"))
    return Kennzahlen(gesamt=gesamt, erhalten=erhalten, offen=gesamt - erhalten)


@dataclass
class Todo:
    kategorie: str
    text: str
    deal: Deal | None
    faellig_bis: datetime.date | None = None
    ueberfaellig: bool = False
    # Zugrunde liegende Fakten-Objekte (Bedingung/Praemie/Aufgabe), damit die
    # Oberfläche bei mehreren offenen Posten einen Dialog zum einzelnen
    # Abhaken anbieten kann. Bei Kündigen/Bestätigung/Zugangsdaten leer,
    # weil dort direkt am Deal abgehakt wird.
    elemente: list = field(default_factory=list)


QUELLE_SPARTANIEN = "spartanien"
QUELLE_BANK = "bank"
QUELLE_LABELS = {QUELLE_SPARTANIEN: "Spartanien", QUELLE_BANK: "Bank"}
QUELLEN = tuple(QUELLE_LABELS)


def normalisiere_quelle(wert: str | None) -> str | None:
    """Auf die kanonische Schreibweise bringen. Fachlich gibt es nur diese
    zwei Quellen, jeder abweichende Wert ist ein Schreibfehler - er wird
    nicht stillschweigend zugeordnet, sondern als None zurückgegeben."""
    if wert is None:
        return None
    normalisiert = wert.strip().lower()
    return normalisiert if normalisiert in QUELLE_LABELS else None


def quelle_label(quelle: str) -> str:
    return QUELLE_LABELS.get(quelle, quelle)


def bank_name_normalisieren(name: str) -> str:
    """Bank-Namen robust vergleichbar machen: Groß-/Kleinschreibung,
    Leerzeichen und Interpunktion werden ignoriert (z.B. "SMARTBROKER" ==
    "Smart Broker" == "smart-broker"). Ohne das gilt ein bereits bekannter
    Kunde beim KI-Deal-Finder fälschlich als Neukunde, nur weil eine vom
    Angebot gelieferte Schreibweise leicht von der selbst erfassten abweicht
    - und beim Übernehmen entstünde ein doppelter Bank-Datensatz."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def deal_todos(deal: Deal, heute: datetime.date | None = None) -> list[Todo]:
    """Abgeleitete ToDos aus Status und offenen Bedingungen. Zukünftige
    Kündigungstermine erscheinen erst, wenn sie fällig sind. Bedingungen und
    Prämien werden pro Deal zu einem ToDo zusammengefasst (elemente trägt
    die einzelnen offenen Posten für den Abhak-Dialog)."""
    heute = heute or datetime.date.today()
    todos: list[Todo] = []
    s = status(deal)
    bezeichnung = f"{deal.bank.name} · {deal.inhaber.name}"

    if s == STATUS_BEDINGUNGEN:
        offene = [b for b in deal.bedingungen if not b.erfuellt]
        if len(offene) == 1:
            b = offene[0]
            ueberfaellig = bool(b.faellig_bis and b.faellig_bis < heute)
            todos.append(Todo("Bedingungen", f"{bezeichnung}: {b.beschreibung}", deal, b.faellig_bis, ueberfaellig, offene))
        elif offene:
            ueberfaellig = any(b.faellig_bis and b.faellig_bis < heute for b in offene)
            todos.append(
                Todo("Bedingungen", f"{bezeichnung}: {len(offene)} Bedingungen offen", deal, None, ueberfaellig, offene)
            )
    elif s == STATUS_PRAEMIE_WARTEN:
        offene = [p for p in deal.praemien if not p.erhalten]
        ueberfaellig = any(praemie_ueberfaellig(deal, p, heute) for p in offene)
        if len(offene) == 1:
            p = offene[0]
            text = f"{bezeichnung}: Prämie prüfen ({quelle_label(p.quelle)}, {p.betrag} €)"
            if p.auszahlung_erwartet:
                text += f" – erwartet {p.auszahlung_erwartet}"
            if ueberfaellig:
                text += " – überfällig, bei der Bank nachhaken"
            todos.append(Todo("Auf Prämie warten", text, deal, None, ueberfaellig, offene))
        elif offene:
            text = f"{bezeichnung}: {len(offene)} Prämien offen"
            if ueberfaellig:
                text += " – davon überfällig"
            todos.append(Todo("Auf Prämie warten", text, deal, None, ueberfaellig, offene))
    elif s == STATUS_KUENDIGEN:
        todos.append(Todo("Kündigen", f"{bezeichnung}: jetzt kündbar – kündigen", deal, deal.kuendbar_ab))
    elif s == STATUS_BESTAETIGUNG_WARTEN:
        todos.append(Todo("Bestätigung warten", f"{bezeichnung}: Kündigung bestätigen lassen", deal))

    # Für ein gekündigtes Konto sind die Zugangsdaten gegenstandslos - das
    # ToDo hing bisher unabhängig vom Status am Deal und blieb selbst bei
    # abgeschlossenen Deals dauerhaft stehen.
    if not deal.zugangsdaten_gespeichert and not deal.gekuendigt and not deal.storniert:
        todos.append(Todo("Zugangsdaten", f"{bezeichnung}: Zugangsdaten sichern", deal))

    for punkt in pruefpunkte(deal, heute):
        todos.append(Todo("Zu prüfen", f"{bezeichnung}: {punkt.text}", deal, elemente=[punkt]))

    return todos


def alle_todos(
    deals: list[Deal], aufgaben: list[Aufgabe], heute: datetime.date | None = None
) -> list[Todo]:
    """Führt abgeleitete ToDos und manuelle Aufgaben in einer Liste zusammen."""
    heute = heute or datetime.date.today()
    todos: list[Todo] = []
    for deal in deals:
        todos.extend(deal_todos(deal, heute))
    for a in aufgaben:
        if a.erledigt:
            continue
        ueberfaellig = bool(a.faellig_bis and a.faellig_bis < heute)
        prefix = f"{a.deal.bank.name} · {a.deal.inhaber.name}: " if a.deal else ""
        todos.append(Todo("Manuelle Aufgaben", f"{prefix}{a.beschreibung}", a.deal, a.faellig_bis, ueberfaellig, [a]))
    return todos


# --- Überfällige Prämien ---
#
# Das zentrale Signal beim Prämien-Hopping: die Prämie ist nicht gekommen,
# also nachhaken, bevor die Frist der Bank abläuft. Bewusst keine eigene
# ToDo-Kategorie, sondern eine Markierung am bestehenden ToDo "Auf Prämie
# warten" - so wie Bedingungen und Aufgaben es schon haben.

KARENZ_MIT_DATUM_MONATE = 1
KARENZ_OHNE_DATUM_MONATE = 2


def monat_plus(datum: datetime.date, monate: int) -> datetime.date:
    """Monate addieren, ohne auf externe Bibliotheken zurückzugreifen. Der Tag
    wird auf die Länge des Zielmonats begrenzt (31.01. + 1 Monat = 28.02.)."""
    gesamt = datum.month - 1 + monate
    jahr = datum.year + gesamt // 12
    monat = gesamt % 12 + 1
    if monat == 12:
        naechster = datetime.date(jahr + 1, 1, 1)
    else:
        naechster = datetime.date(jahr, monat + 1, 1)
    letzter_tag = (naechster - datetime.timedelta(days=1)).day
    return datetime.date(jahr, monat, min(datum.day, letzter_tag))


def praemie_faellig_ab(deal: Deal, praemie) -> datetime.date | None:
    """Ab wann eine noch offene Prämie als überfällig gilt - None, wenn es
    keinen Bezugspunkt gibt.

    Mit hinterlegtem Auszahlungsmonat: Ende dieses Monats plus ein Monat
    Karenz, weil Banken erfahrungsgemäß spät zahlen. Ohne Auszahlungsmonat:
    zwei Monate nach der zuletzt erfüllten Bedingung - ab dann schuldet die
    Bank die Prämie. Hat ein Deal überhaupt keine Bedingungen, gibt es keinen
    Anker; dann wird nicht markiert (die Vollständigkeit mahnt das fehlende
    Auszahlungsdatum ohnehin an).
    """
    if praemie.erhalten:
        return None

    if praemie.auszahlung_erwartet:
        erwartet = parse_monat(praemie.auszahlung_erwartet)
        if erwartet is None:
            return None
        # erster Tag des Monats nach der Karenz
        return monat_plus(erwartet, KARENZ_MIT_DATUM_MONATE + 1)

    if not deal.bedingungen or not all(b.erfuellt for b in deal.bedingungen):
        return None
    zeitpunkte = [b.erfuellt_am for b in deal.bedingungen if b.erfuellt_am]
    if not zeitpunkte:
        return None
    return monat_plus(max(zeitpunkte), KARENZ_OHNE_DATUM_MONATE)


def praemie_ueberfaellig(deal: Deal, praemie, heute: datetime.date | None = None) -> bool:
    heute = heute or datetime.date.today()
    ab = praemie_faellig_ab(deal, praemie)
    return ab is not None and heute >= ab


PRUEFUNG_KARENZ_TAGE = 14


def praemie_naechste_pruefung(praemie, heute: datetime.date | None = None) -> datetime.date:
    """Wann die offene Prämie als nächstes auf Eingang geprüft werden sollte.

    Ohne eigenen Eintrag (Nutzer hat noch nie "+2 Wochen" geklickt) gilt als
    Ausgangspunkt das erwartete Auszahlungsdatum, falls hinterlegt, sonst der
    heutige Tag - so zeigt die Oberfläche von Anfang an ein sinnvolles Datum,
    ohne dass beim Anlegen der Prämie schon etwas gespeichert werden muss."""
    if praemie.naechste_pruefung_am:
        return praemie.naechste_pruefung_am
    if praemie.auszahlung_erwartet:
        erwartet = parse_monat(praemie.auszahlung_erwartet)
        if erwartet:
            return erwartet
    return heute or datetime.date.today()


def praemie_pruefung_verschieben(praemie, heute: datetime.date | None = None) -> None:
    """Setzt naechste_pruefung_am auf den aktuellen Ausgangspunkt plus 2
    Wochen - der Button in der Todo-Liste markiert damit "gerade
    nachgeschaut, nächstes Mal in 2 Wochen wieder". Liegt der bisherige
    Ausgangspunkt (z.B. ein längst verstrichenes erwartetes
    Auszahlungsdatum) schon in der Vergangenheit, wird stattdessen ab heute
    gerechnet - sonst würde "verschieben" ein weiterhin überfälliges Datum
    liefern."""
    heute = heute or datetime.date.today()
    basis = max(praemie_naechste_pruefung(praemie, heute), heute)
    praemie.naechste_pruefung_am = basis + datetime.timedelta(days=PRUEFUNG_KARENZ_TAGE)


# --- Zu prüfen: querliegende Auffälligkeiten ---
#
# Kein siebter Pipeline-Status: "zu prüfen" ist keine Stufe im Lebenszyklus,
# sondern ein loser Faden. Ein gekündigter, bestätigter Deal mit offener
# Bedingung *ist* abgeschlossen - status() bleibt deshalb einwertig, und ein
# Deal kann gleichzeitig "Abgeschlossen" und "zu prüfen" sein.

PRUEF_BEDINGUNGEN_OFFEN = "bedingungen_offen"
PRUEF_PRAEMIEN_OFFEN = "praemien_offen"
PRUEF_KEINE_PRAEMIE = "keine_praemie"
PRUEF_KUENDIGUNGSMONAT_FEHLT = "kuendigungsmonat_fehlt"

PRUEF_TEXTE = {
    PRUEF_BEDINGUNGEN_OFFEN: "Bedingungen nach der Kündigung noch offen",
    PRUEF_PRAEMIEN_OFFEN: "Prämien nach der Kündigung noch nicht erhalten",
    PRUEF_KEINE_PRAEMIE: "Keine Prämie erfasst",
    PRUEF_KUENDIGUNGSMONAT_FEHLT: "Gekündigt, aber ohne auswertbaren Kündigungsmonat",
}

# Ein frisch angelegter Deal hat naturgemäß noch keine Prämien - die trägt man
# erst danach ein. Ohne diese Schonfrist landet jeder neue Deal sofort in der
# Liste.
KEINE_PRAEMIE_SCHONFRIST = datetime.timedelta(hours=72)


@dataclass
class Pruefpunkt:
    regel: str
    text: str
    signatur: str


def _geprueft_liste(deal: Deal) -> dict[str, str]:
    if not deal.pruefung_geprueft:
        return {}
    try:
        werte = json.loads(deal.pruefung_geprueft)
    except (json.JSONDecodeError, TypeError):
        return {}
    return werte if isinstance(werte, dict) else {}


def pruefung_abhaken(deal: Deal, regel: str, signatur: str) -> None:
    """Merkt, dass diese Auffälligkeit in *diesem* Zustand angesehen wurde.
    Gespeichert wird die Signatur, nicht bloß ein Häkchen - ändern sich die
    Fakten, passt sie nicht mehr und der Hinweis kommt zurück."""
    geprueft = _geprueft_liste(deal)
    geprueft[regel] = signatur
    deal.pruefung_geprueft = json.dumps(geprueft, sort_keys=True)


def _offene_pruefpunkte(deal: Deal, heute: datetime.date) -> list[Pruefpunkt]:
    punkte: list[Pruefpunkt] = []

    if deal.gekuendigt and not deal.storniert:
        offene_bedingungen = [b.id for b in deal.bedingungen if not b.erfuellt]
        if offene_bedingungen:
            punkte.append(
                Pruefpunkt(
                    PRUEF_BEDINGUNGEN_OFFEN,
                    PRUEF_TEXTE[PRUEF_BEDINGUNGEN_OFFEN],
                    ",".join(str(i) for i in sorted(offene_bedingungen)),
                )
            )
        offene_praemien = [p.id for p in deal.praemien if not p.erhalten]
        if offene_praemien:
            punkte.append(
                Pruefpunkt(
                    PRUEF_PRAEMIEN_OFFEN,
                    PRUEF_TEXTE[PRUEF_PRAEMIEN_OFFEN],
                    ",".join(str(i) for i in sorted(offene_praemien)),
                )
            )
        if parse_monat(deal.gekuendigt_im_monat) is None:
            punkte.append(
                Pruefpunkt(
                    PRUEF_KUENDIGUNGSMONAT_FEHLT,
                    PRUEF_TEXTE[PRUEF_KUENDIGUNGSMONAT_FEHLT],
                    deal.gekuendigt_im_monat or "",
                )
            )

    if not deal.praemien and not deal.storniert:
        angelegt = deal.erstellt_am
        alt_genug = angelegt is None or (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - angelegt) > KEINE_PRAEMIE_SCHONFRIST
        if alt_genug:
            punkte.append(Pruefpunkt(PRUEF_KEINE_PRAEMIE, PRUEF_TEXTE[PRUEF_KEINE_PRAEMIE], ""))

    return punkte


def pruefpunkte(deal: Deal, heute: datetime.date | None = None) -> list[Pruefpunkt]:
    """Auffälligkeiten, die noch nicht in diesem Zustand abgehakt wurden."""
    heute = heute or datetime.date.today()
    geprueft = _geprueft_liste(deal)
    return [p for p in _offene_pruefpunkte(deal, heute) if geprueft.get(p.regel) != p.signatur]


# --- Vollständigkeits-Übersicht ---

# "kuendbar_ab" steht hier bewusst nicht: ein leeres Feld ist keine Lücke,
# sondern die Aussage "keine Sperrfrist" (siehe ist_kuendbar).
WUENSCHENSWERTE_FELDER = {
    "kontonummer": "Kontonummer",
    "freibetrag": "Freibetrag",
}


def uebersprungene_felder_liste(deal: Deal) -> list[str]:
    if not deal.uebersprungene_felder:
        return []
    try:
        werte = json.loads(deal.uebersprungene_felder)
    except (json.JSONDecodeError, TypeError):
        return []
    return werte if isinstance(werte, list) else []


def uebersprungene_felder_speichern(deal: Deal, felder: list[str]) -> None:
    deal.uebersprungene_felder = json.dumps(felder)


@dataclass
class OffenesFeld:
    feld: str
    label: str
    praemie_id: int | None = None


def offene_felder(deal: Deal) -> list[OffenesFeld]:
    """Ein leeres Feld gilt nur dann als 'offen', wenn es nicht bewusst als
    'nicht nötig' abgehakt wurde (uebersprungene_felder)."""
    uebersprungen = set(uebersprungene_felder_liste(deal))
    offen: list[OffenesFeld] = []

    for feldname, label in WUENSCHENSWERTE_FELDER.items():
        if feldname in uebersprungen:
            continue
        if getattr(deal, feldname) is None:
            offen.append(OffenesFeld(feldname, label))

    for p in deal.praemien:
        feldname = f"praemie_{p.id}_auszahlung_erwartet"
        if feldname in uebersprungen:
            continue
        if not p.erhalten and not p.auszahlung_erwartet:
            offen.append(
                OffenesFeld(feldname, f"Erwartete Auszahlung ({quelle_label(p.quelle)}, {p.betrag} €)", p.id)
            )

    return offen


def ist_vollstaendig(deal: Deal) -> bool:
    return len(offene_felder(deal)) == 0
