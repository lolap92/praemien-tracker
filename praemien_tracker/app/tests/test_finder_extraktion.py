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


def test_bedingung_gilt_fuer_teilpraemie_default_none_und_uebernommen():
    """Santander-Fall: eine Bedingung, die nur einen Teilbetrag freischaltet,
    trägt dessen Label; eine Grundvoraussetzung bleibt bei None."""
    grund = BedingungExtraktion(beschreibung="Neukunde sein", einschaetzung="erfuellt")
    assert grund.gilt_fuer is None

    teil = BedingungExtraktion(
        beschreibung="Kontowechselservice nutzen",
        einschaetzung="zu_pruefen",
        gilt_fuer="250 € für den Kontowechselservice",
    )
    assert teil.gilt_fuer == "250 € für den Kontowechselservice"


def test_geschaeftskunden_feld_default_false_und_uebernommen():
    """Das Feld muss optional bleiben: bereits zwischengespeicherte
    Extraktionen (finder_funde.extraktion_json) kennen es noch nicht und
    dürfen deshalb nicht ungültig werden."""
    ohne = AngebotExtraktion.model_validate_json(
        '{"bank_name": "C24", "kontoart": "Girokonto", "praemie_betrag": 125.0, "bedingungen": []}'
    )
    assert ohne.nur_geschaeftskunden is False

    client = FakeClient(
        AngebotExtraktion(
            bank_name="Firmenbank",
            kontoart="Geschäftskonto",
            praemie_betrag=300.0,
            nur_geschaeftskunden=True,
            bedingungen=[],
        )
    )
    ergebnis = extrahiere_angebot(client, "Businesskonto fuer Selbststaendige", model="claude-haiku-4-5")
    assert ergebnis.nur_geschaeftskunden is True


def test_extraktions_prompt_fragt_die_zielgruppe_ab():
    """Ohne die Anweisung im Prompt bliebe das Feld immer beim Default False -
    das Kriterium wäre dann wirkungslos."""
    from praemien_tracker.finder.extraktion import EXTRAKTION_PROMPT

    assert "nur_geschaeftskunden" in EXTRAKTION_PROMPT
    assert "Geschäftskonto" in EXTRAKTION_PROMPT
