"""Abgeleitete Sichten auf die gespeicherten Fakten.

Prinzip des Konzepts: Der Nutzer erfasst nur Fakten (models.py). Status,
Kennzahlen, ToDo-Liste und Vollständigkeit werden hier bei jedem Aufruf aus
diesen Fakten berechnet und nirgends gespeichert.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Aufgabe, Deal

STATUS_BEDINGUNGEN = "bedingungen"
STATUS_PRAEMIE_WARTEN = "praemie_warten"
STATUS_KUENDIGEN = "kuendigen"
STATUS_BESTAETIGUNG_WARTEN = "bestaetigung_warten"
STATUS_ABGESCHLOSSEN = "abgeschlossen"

STATUS_ORDER = [
    STATUS_BEDINGUNGEN,
    STATUS_PRAEMIE_WARTEN,
    STATUS_KUENDIGEN,
    STATUS_BESTAETIGUNG_WARTEN,
    STATUS_ABGESCHLOSSEN,
]

STATUS_LABELS = {
    STATUS_BEDINGUNGEN: "Bedingungen",
    STATUS_PRAEMIE_WARTEN: "Auf Prämie warten",
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
    heute = heute or datetime.date.today()
    return deal.kuendbar_ab is None or deal.kuendbar_ab <= heute


def status(deal: Deal) -> str:
    """Fünfstufige Pipeline, siehe Konzept Abschnitt 6."""
    if not bedingungen_erfuellt(deal):
        return STATUS_BEDINGUNGEN
    if not alle_praemien_erhalten(deal):
        return STATUS_PRAEMIE_WARTEN
    if not deal.gekuendigt:
        return STATUS_KUENDIGEN
    if not deal.kuendigung_bestaetigt:
        return STATUS_BESTAETIGUNG_WARTEN
    return STATUS_ABGESCHLOSSEN


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


def deal_todos(deal: Deal, heute: datetime.date | None = None) -> list[Todo]:
    """Abgeleitete ToDos aus Status und offenen Bedingungen. Zukünftige
    Kündigungstermine erscheinen erst, wenn sie fällig sind."""
    heute = heute or datetime.date.today()
    todos: list[Todo] = []
    s = status(deal)
    bezeichnung = f"{deal.bank.name} · {deal.inhaber.name}"

    if s == STATUS_BEDINGUNGEN:
        for b in deal.bedingungen:
            if not b.erfuellt:
                ueberfaellig = bool(b.faellig_bis and b.faellig_bis < heute)
                todos.append(
                    Todo("Bedingungen", f"{bezeichnung}: {b.beschreibung}", deal, b.faellig_bis, ueberfaellig)
                )
    elif s == STATUS_PRAEMIE_WARTEN:
        for p in deal.praemien:
            if not p.erhalten:
                text = f"{bezeichnung}: Prämie prüfen ({p.quelle}, {p.betrag} €)"
                if p.auszahlung_erwartet:
                    text += f" – erwartet {p.auszahlung_erwartet}"
                todos.append(Todo("Auf Prämie warten", text, deal))
    elif s == STATUS_KUENDIGEN:
        if ist_kuendbar(deal, heute):
            todos.append(Todo("Kündigen", f"{bezeichnung}: jetzt kündbar – kündigen", deal, deal.kuendbar_ab))
    elif s == STATUS_BESTAETIGUNG_WARTEN:
        todos.append(Todo("Bestätigung warten", f"{bezeichnung}: Kündigung bestätigen lassen", deal))

    if not deal.zugangsdaten_gespeichert:
        todos.append(Todo("Zugangsdaten", f"{bezeichnung}: Zugangsdaten sichern", deal))

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
        todos.append(Todo("Manuelle Aufgaben", f"{prefix}{a.beschreibung}", a.deal, a.faellig_bis, ueberfaellig))
    return todos


# --- Vollständigkeits-Übersicht ---

WUENSCHENSWERTE_FELDER = {
    "kontonummer": "Kontonummer",
    "kuendbar_ab": "Kündbar ab",
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
                OffenesFeld(feldname, f"Erwartete Auszahlung ({p.quelle}, {p.betrag} €)", p.id)
            )

    return offen


def ist_vollstaendig(deal: Deal) -> bool:
    return len(offene_felder(deal)) == 0
