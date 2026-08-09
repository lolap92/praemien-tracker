"""Validierung für die JSON-Deal-Anlage (Konzept Abschnitt 6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .derived import QUELLEN, format_monat, normalisiere_quelle, parse_monat


def _monat_pruefen(wert: Optional[str]) -> Optional[str]:
    """Monatsangaben auf ISO normalisieren und dabei prüfen.

    Bisher waren beide Monatsfelder ungeprüfter Freitext; eine falsch
    formatierte Eingabe fiel erst später als "fehlt" auf.
    """
    if wert is None or not wert.strip():
        return None
    datum = parse_monat(wert)
    if datum is None:
        raise ValueError(f"ist kein gültiger Monat, erwartet JJJJ-MM (war: {wert!r})")
    return format_monat(datum)


class PraemieIn(BaseModel):
    quelle: str
    betrag: Decimal
    erhalten: bool = False
    auszahlung_erwartet: Optional[str] = None

    @field_validator("quelle")
    @classmethod
    def _quelle_pruefen(cls, wert: str) -> str:
        """Groß-/Kleinschreibung und Randleerzeichen werden verziehen,
        unbekannte Quellen nicht: fachlich gibt es nur diese beiden, alles
        andere ist ein Schreibfehler - und würde beim nächsten Speichern über
        das Formular stillschweigend zu "spartanien" umgedeutet."""
        normalisiert = normalisiere_quelle(wert)
        if normalisiert is None:
            raise ValueError(f"muss {' oder '.join(QUELLEN)} sein (war: {wert!r})")
        return normalisiert

    _auszahlung_normalisieren = field_validator("auszahlung_erwartet")(_monat_pruefen)


class BedingungIn(BaseModel):
    beschreibung: str
    erfuellt: bool = False
    faellig_bis: Optional[date] = None


class AufgabeIn(BaseModel):
    beschreibung: str
    erledigt: bool = False
    faellig_bis: Optional[date] = None


class UrlIn(BaseModel):
    url: str
    bezeichnung: Optional[str] = None


class DealImport(BaseModel):
    bank: str
    kontoart: str
    inhaber: str
    kontonummer: Optional[str] = None
    kuendbar_ab: Optional[date] = None
    gekuendigt: bool = False
    gekuendigt_im_monat: Optional[str] = None
    kuendigung_bestaetigt: bool = False
    kuendigung_hinweis: Optional[str] = None
    kuendigung_hinweis_url: Optional[str] = None
    kommentar: Optional[str] = None
    freibetrag: Optional[Decimal] = None
    # Ohne Angabe fällt ein gesetzter Freibetrag beim Import auf das laufende
    # Jahr (siehe helpers.freibetrag_jahr_bestimmen) - sonst wäre er in der
    # Freibetrag-Übersicht keiner Jahresspalte zugeordnet und unsichtbar.
    freibetrag_jahr: Optional[int] = None
    praemien_auf_sparkonto: Optional[bool] = None
    zugangsdaten_gespeichert: bool = False
    # Felder, die bewusst als "nicht nötig" abgehakt wurden - damit sich die
    # Vollständigkeits-Häkchen mit exportieren und wieder einlesen lassen.
    uebersprungene_felder: list[str] = Field(default_factory=list)
    praemien: list[PraemieIn] = Field(default_factory=list)
    bedingungen: list[BedingungIn] = Field(default_factory=list)
    urls: list[UrlIn] = Field(default_factory=list)
    aufgaben: list[AufgabeIn] = Field(default_factory=list)

    _monat_normalisieren = field_validator("gekuendigt_im_monat")(_monat_pruefen)


class SeedData(BaseModel):
    schema_version: int
    hinweis: Optional[str] = None
    deals: list[DealImport] = Field(default_factory=list)
