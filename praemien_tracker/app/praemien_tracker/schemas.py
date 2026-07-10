"""Validierung für die JSON-Deal-Anlage (Konzept Abschnitt 6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PraemieIn(BaseModel):
    quelle: str
    betrag: Decimal
    erhalten: bool = False
    auszahlung_erwartet: Optional[str] = None


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
    kommentar: Optional[str] = None
    freibetrag: Optional[Decimal] = None
    praemien_auf_sparkonto: Optional[bool] = None
    zugangsdaten_gespeichert: bool = False
    praemien: list[PraemieIn] = Field(default_factory=list)
    bedingungen: list[BedingungIn] = Field(default_factory=list)
    urls: list[UrlIn] = Field(default_factory=list)
    aufgaben: list[AufgabeIn] = Field(default_factory=list)


class SeedData(BaseModel):
    schema_version: int
    hinweis: Optional[str] = None
    deals: list[DealImport] = Field(default_factory=list)
