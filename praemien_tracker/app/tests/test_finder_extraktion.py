"""finder/extraktion.py gegen einen Fake-Anthropic-Client - kein Netzwerk,
kein echter API-Key nötig."""

from __future__ import annotations

from types import SimpleNamespace

from praemien_tracker.finder.extraktion import (
    AngebotExtraktion,
    BedingungExtraktion,
    RelevanzErgebnis,
    extrahiere_angebot,
    ist_relevantes_angebot,
)


class FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output

    def parse(self, **kwargs):
        return SimpleNamespace(parsed_output=self._parsed_output, stop_reason="end_turn")


class FakeClient:
    def __init__(self, parsed_output):
        self.messages = FakeMessages(parsed_output)


def test_themen_check_erkennt_relevantes_angebot():
    client = FakeClient(RelevanzErgebnis(ist_relevant=True))
    assert ist_relevantes_angebot(client, "C24 125 Euro Praemie", model="claude-haiku-4-5") is True


def test_themen_check_erkennt_irrelevantes_angebot():
    client = FakeClient(RelevanzErgebnis(ist_relevant=False))
    assert ist_relevantes_angebot(client, "Autoversicherung wechseln", model="claude-haiku-4-5") is False


def test_themen_check_ohne_auswertbares_ergebnis_ist_konservativ():
    """Kein parsed_output (z.B. Refusal) heißt: dieser Fund geht nicht in die
    teurere Extraktion - nicht raten."""
    client = FakeClient(None)
    assert ist_relevantes_angebot(client, "Text", model="claude-haiku-4-5") is False


def test_struktur_extraktion_liefert_alle_felder():
    ergebnis = AngebotExtraktion(
        bank_name="C24 Bank",
        kontoart="Girokonto",
        praemie_betrag=125.0,
        sperrfrist_monate=None,
        bedingungen=[BedingungExtraktion(beschreibung="3 Kartenzahlungen", einschaetzung="erfuellt")],
    )
    client = FakeClient(ergebnis)
    out = extrahiere_angebot(client, "Text", model="claude-haiku-4-5")
    assert out is not None
    assert out.bank_name == "C24 Bank"
    assert out.bedingungen[0].einschaetzung == "erfuellt"


def test_struktur_extraktion_ohne_ergebnis_liefert_none():
    client = FakeClient(None)
    assert extrahiere_angebot(client, "Text", model="claude-haiku-4-5") is None


def test_bedingung_kennzahlen_optional_und_default_none():
    """Die strukturierten Kennzahlen sind optional - eine Bedingung ohne
    Zahlenangaben lässt sie auf None (nicht 0)."""
    b = BedingungExtraktion(beschreibung="Kontoeröffnung", einschaetzung="erfuellt")
    assert b.anzahl is None
    assert b.betrag_euro is None
    assert b.frist_wochen is None


def test_bedingung_kennzahlen_werden_uebernommen():
    """awa7-Fall: 'mindestens 2x innerhalb von 4 Wochen für insgesamt 50 €'
    landet als strukturierte Kennzahlen an der Bedingung."""
    ergebnis = AngebotExtraktion(
        bank_name="Hanseatic Bank",
        kontoart="Kreditkarte",
        praemie_betrag=50.0,
        bedingungen=[
            BedingungExtraktion(
                beschreibung="Karte innerhalb von 4 Wochen mindestens 2x für insgesamt 50 € einsetzen",
                einschaetzung="erfuellt",
                anzahl=2,
                betrag_euro=50.0,
                frist_wochen=4,
            )
        ],
    )
    out = extrahiere_angebot(FakeClient(ergebnis), "Text", model="claude-haiku-4-5")
    assert out is not None
    (bed,) = out.bedingungen
    assert bed.anzahl == 2
    assert bed.betrag_euro == 50.0
    assert bed.frist_wochen == 4
