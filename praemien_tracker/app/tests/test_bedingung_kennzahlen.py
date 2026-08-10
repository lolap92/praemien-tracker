"""Strukturierte Bedingungs-Kennzahlen (anzahl/betrag_euro/frist_wochen)
überstehen den JSON-Import und landen an der Bedingung des angelegten Deals -
derselbe Weg, den 'Übernehmen' eines KI-Vorschlags nutzt
(build_deal_from_import)."""

from __future__ import annotations

from decimal import Decimal

from praemien_tracker.helpers import build_deal_from_import
from praemien_tracker.schemas import BedingungIn, DealImport


def test_kennzahlen_landen_an_der_bedingung(db):
    daten = DealImport(
        bank="Hanseatic Bank",
        kontoart="Kreditkarte",
        inhaber="Max",
        bedingungen=[
            BedingungIn(
                beschreibung="Karte innerhalb von 4 Wochen mindestens 2x für insgesamt 50 € einsetzen",
                anzahl=2,
                betrag_euro=Decimal("50"),
                frist_wochen=4,
            )
        ],
    )
    deal = build_deal_from_import(db, daten)
    (bed,) = deal.bedingungen
    assert bed.anzahl == 2
    assert bed.betrag_euro == Decimal("50")
    assert bed.frist_wochen == 4


def test_kennzahlen_optional_default_none(db):
    """Eine Bedingung ohne Zahlenangaben bleibt bei None - kein 0-Rauschen."""
    daten = DealImport(
        bank="Neubank",
        kontoart="Girokonto",
        inhaber="Erika",
        bedingungen=[BedingungIn(beschreibung="Kontoeröffnung online")],
    )
    deal = build_deal_from_import(db, daten)
    (bed,) = deal.bedingungen
    assert bed.anzahl is None
    assert bed.betrag_euro is None
    assert bed.frist_wochen is None
