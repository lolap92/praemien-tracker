from __future__ import annotations

import datetime
import json
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from .models import Aufgabe, Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie
from .schemas import DealImport


def parse_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def get_or_create_bank(db: Session, name: str) -> Bank:
    name = name.strip()
    bank = db.query(Bank).filter(Bank.name == name).one_or_none()
    if bank is None:
        bank = Bank(name=name)
        db.add(bank)
        db.flush()
    return bank


def get_or_create_inhaber(db: Session, name: str) -> Inhaber:
    name = name.strip()
    inhaber = db.query(Inhaber).filter(Inhaber.name == name).one_or_none()
    if inhaber is None:
        inhaber = Inhaber(name=name)
        db.add(inhaber)
        db.flush()
    return inhaber


def _leer_zu_none(wert: str | None) -> str | None:
    """Randleerzeichen entfernen, Leerstrings zu None - damit der Importpfad
    dieselben Werte erzeugt wie der Formularpfad."""
    if wert is None:
        return None
    return wert.strip() or None


def build_deal_from_import(db: Session, daten: DealImport) -> Deal:
    """Legt einen Deal inkl. Prämien/Bedingungen/Aufgaben/Links aus validierten
    JSON-Importdaten an."""
    deal = Deal(
        bank=get_or_create_bank(db, daten.bank),
        inhaber=get_or_create_inhaber(db, daten.inhaber),
        kontoart=daten.kontoart.strip(),
        kontonummer=_leer_zu_none(daten.kontonummer),
        kuendbar_ab=daten.kuendbar_ab,
        gekuendigt=daten.gekuendigt,
        gekuendigt_im_monat=_leer_zu_none(daten.gekuendigt_im_monat),
        kuendigung_bestaetigt=daten.kuendigung_bestaetigt,
        kuendigung_hinweis=_leer_zu_none(daten.kuendigung_hinweis),
        kuendigung_hinweis_url=_leer_zu_none(daten.kuendigung_hinweis_url),
        freibetrag=daten.freibetrag,
        praemien_auf_sparkonto=daten.praemien_auf_sparkonto,
        kommentar=_leer_zu_none(daten.kommentar),
        zugangsdaten_gespeichert=daten.zugangsdaten_gespeichert,
    )
    if daten.uebersprungene_felder:
        deal.uebersprungene_felder = json.dumps(sorted(set(daten.uebersprungene_felder)))
    for p in daten.praemien:
        deal.praemien.append(
            Praemie(
                quelle=p.quelle,
                betrag=p.betrag,
                erhalten=p.erhalten,
                auszahlung_erwartet=_leer_zu_none(p.auszahlung_erwartet),
            )
        )
    for b in daten.bedingungen:
        deal.bedingungen.append(
            Bedingung(beschreibung=b.beschreibung.strip(), erfuellt=b.erfuellt, faellig_bis=b.faellig_bis)
        )
    for u in daten.urls:
        deal.urls.append(DealUrl(url=u.url.strip(), bezeichnung=_leer_zu_none(u.bezeichnung)))
    for a in daten.aufgaben:
        deal.aufgaben.append(
            Aufgabe(beschreibung=a.beschreibung.strip(), erledigt=a.erledigt, faellig_bis=a.faellig_bis)
        )
    db.add(deal)
    return deal
