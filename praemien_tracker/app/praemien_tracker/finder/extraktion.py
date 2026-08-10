"""Rohtext über die Anthropic-API in strukturierte Felder übersetzen.

Zweistufig, wie im Konzept festgelegt: zuerst ein Themen-Check (ist das
überhaupt ein Konto-/Depot-Neukundenprämien-Angebot?), erst bei "ja" die
teurere Struktur-Extraktion. Die KI übersetzt Text in Felder - ob ein Fund
am Ende vorgeschlagen wird, entscheidet ausschließlich matching.py als
gewöhnlicher, deterministischer Code.

Der Anthropic-Client wird als Parameter übergeben (kein Modul-globaler
Client) - so lässt sich diese Datei mit einem Fake-Client testen, ohne
Netzwerk oder echten API-Key.
"""

from __future__ import annotations

import logging
from typing import Literal, Protocol

from pydantic import BaseModel

logger = logging.getLogger("praemien_tracker.finder")


class RelevanzErgebnis(BaseModel):
    ist_relevant: bool


class BedingungExtraktion(BaseModel):
    beschreibung: str
    # erfuellt: keine Hürde erkennbar. zu_pruefen: unklar formuliert.
    # nicht_erfuellt: eindeutig eine Hürde (z.B. "Gehaltseingang zwingend
    # erforderlich"). Sonstiger Geldeingang statt Gehalt zählt als erfuellt.
    einschaetzung: Literal["erfuellt", "zu_pruefen", "nicht_erfuellt"]
    # Strukturierte Kennzahlen der Auflage, sofern im Text ausdrücklich
    # genannt - erlauben eine kompakte Darstellung ("2× · 50 € · 4 Wochen") und
    # eine spätere maschinelle Prüfung. Jeweils None, wenn die Größe im Text
    # nicht vorkommt: nicht raten, der Freitext in beschreibung bleibt die
    # verbindliche Quelle.
    anzahl: int | None = None  # geforderte Anzahl (z.B. Kartenzahlungen)
    betrag_euro: float | None = None  # zugehöriger Mindest-/Umsatzbetrag in Euro
    frist_wochen: int | None = None  # Frist in Wochen (1 Monat = 4 Wochen)


class PraemieExtraktion(BaseModel):
    """Eine einzelne Teilprämie eines Angebots. Ein Angebot bringt häufig
    mehrere Prämien mit unterschiedlichen Voraussetzungen mit (z.B. 50 EUR von
    Spartanien für die Kontoeröffnung plus 250 EUR von der Bank für den
    Kontowechselservice)."""

    betrag: float
    # Wer die Prämie zahlt, aus dem Text (z.B. "Spartanien", "Santander").
    geber: str
    # Wofür es diese Teilprämie gibt (z.B. "für die Kontoeröffnung").
    wofuer: str


class AngebotExtraktion(BaseModel):
    bank_name: str
    kontoart: str
    praemie_betrag: float
    # Monate bis wieder Neukunde bei derselben Bank, aus dem Angebotstext.
    # None, wenn im Text keine Sperrfrist erkennbar ist - wird in matching.py
    # zu "zu_pruefen", nicht zu "automatisch_abgelehnt".
    sperrfrist_monate: int | None = None
    # Ob das Angebot (auch) für Minderjährige offensteht (z.B. Kinderdepot,
    # Junior-Konto). Steuert in lauf.py, ob minderjährigen Inhabern der Fund
    # überhaupt vorgeschlagen wird. Default False (konservativ): fehlt das
    # Feld in einem alten Cache-Eintrag oder ist es unklar, gilt der Deal als
    # nicht für Kinder - Erwachsenen-Angebote werden Kindern dann nicht
    # vorgeschlagen.
    fuer_kinder: bool = False
    # Einzelne Teilprämien mit je eigener Voraussetzung (z.B. 50 EUR von
    # Spartanien für die Kontoeröffnung plus 250 EUR von der Bank für den
    # Kontowechselservice). Leer lassen, wenn es nur eine einzige Prämie ohne
    # sinnvolle Aufteilung gibt - dann zählt allein praemie_betrag.
    praemien: list[PraemieExtraktion] = []
    bedingungen: list[BedingungExtraktion]


class AnthropicMessagesClient(Protocol):
    """Nur der Ausschnitt der Anthropic-SDK-Oberfläche, den dieses Modul
    braucht - erlaubt in Tests einen einfachen Fake statt eines echten
    Clients."""

    messages: object


THEMEN_CHECK_PROMPT = """\
Prüfe, ob der folgende Text ein Angebot für eine Neukunden-Prämie bei \
Eröffnung eines Girokontos, Tagesgeldkontos, Depots oder einer Kreditkarte \
(mit Prämie) beschreibt - im Unterschied zu z.B. Versicherungen, reinen \
Gutscheincodes, Kreditkarten ohne Prämie oder anderen Themen.

Beurteile nur das im Titel bzw. Hauptteil beschriebene Hauptangebot. \
Ignoriere Kommentare, Randspalten, andere nur nebenbei verlinkte Deals und \
Blog-Beiwerk - ein solcher Nebentreffer macht den Text nicht relevant.

Text:
{text}"""

EXTRAKTION_PROMPT = """\
Extrahiere aus dem folgenden Angebotstext für eine Bank-Neukunden-Prämie \
die strukturierten Angaben.

Beziehe dich ausschließlich auf die aktuell beworbene Aktion. Der Text kann \
zusätzlich Kommentare, Fußnoten, andere verlinkte Deals sowie erkennbar \
abgelaufene oder frühere Aktionen (alte Beträge/Zeiträume) enthalten - solche \
Nebeninhalte ignorierst du vollständig.

- bank_name: Name der Bank/des Instituts.
- kontoart: Art des Kontos (z.B. "Girokonto", "Tagesgeld", "Depot", \
"Kreditkarte").
- praemie_betrag: Gesamte Prämiensumme in Euro als Zahl (nur die Zahl, ohne \
Währungszeichen). Wenn mehrere Teilprämien genannt sind, die Summe.
- praemien: Wenn sich die Gesamtprämie aus mehreren Teilprämien mit \
unterschiedlichen Voraussetzungen zusammensetzt (z.B. "50 EUR von Spartanien \
für die Kontoeröffnung" und "250 EUR von der Bank für den \
Kontowechselservice"), jede Teilprämie einzeln auflisten mit: betrag (Zahl in \
Euro), geber (wer zahlt, z.B. "Spartanien" oder der Bankname) und wofuer \
(kurz, wofür es diese Teilprämie gibt). Gibt es nur eine einzige Prämie ohne \
sinnvolle Aufteilung, eine leere Liste zurückgeben.
- sperrfrist_monate: Anzahl Monate, die seit einer vorherigen Kündigung bei \
dieser Bank vergangen sein müssen, um wieder als Neukunde zu gelten - aus \
Formulierungen wie "Kündigung darf nicht in den letzten 12 Monaten erfolgt \
sein". Bei einer Mehrdeutigkeit wie "6 oder 12 Monate" die kürzere Zahl \
übernehmen. Lässt sich aus dem Text keine Sperrfrist erkennen, dieses Feld \
weglassen (null) - nicht raten.
- fuer_kinder: true nur, wenn das Angebot ausdrücklich (auch) für \
Minderjährige/Kinder offensteht - z.B. ein Kinderdepot, Junior-Depot, \
Junior-Konto oder Kinder-Tagesgeld, oder wenn der Text explizit sagt, dass \
Minderjährige teilnehmen können. Im Zweifel false (die meisten \
Neukunden-Prämien setzen Volljährigkeit voraus).
- bedingungen: ALLE einzelnen Bedingungen, die für die Prämie erfüllt werden \
müssen (z.B. Mindesteinlage, Kontoeröffnung online, TAN-Verfahren aktivieren, \
Anzahl Kartenzahlungen, Mindestumsatz, Gehaltseingang, Vertragslaufzeit). \
Suche sie im gesamten Text, ausdrücklich auch in Fußnoten, Kleingedrucktem \
und Abschnitten wie "Bonusbedingungen" - die eigentliche Auflage steht oft \
nicht im Einleitungssatz. Jede Bedingung einzeln mit eigener beschreibung und \
einschaetzung.
  Übernimm in die beschreibung alle konkreten Zahlen einer zusammengehörenden \
Auflage wörtlich: geforderte Anzahl, Mindest-/Umsatzbeträge, Fristen und \
Reihenfolge. Fasse mehrere Zahlen einer Auflage NICHT zu "Karte nutzen" \
zusammen. Gutes Beispiel für eine beschreibung: "Kreditkarte innerhalb von \
4 Wochen nach Kontoeröffnung mindestens 2x für insgesamt 50 € einsetzen".
  Fülle zusätzlich, sofern im Text ausdrücklich genannt, die strukturierten \
Felder der Bedingung (sonst weglassen/null, nicht raten):
    - anzahl: geforderte Anzahl (z.B. 2 bei "mindestens 2x einsetzen").
    - betrag_euro: zugehöriger Mindest-/Umsatzbetrag in Euro als Zahl.
    - frist_wochen: Frist in Wochen; rechne dabei 1 Monat = 4 Wochen, 3 Monate \
= 12 Wochen.
  einschaetzung je Bedingung:
  - "erfuellt": keine erkennbare Hürde für einen typischen Neukunden (z.B. \
"3 Kartenzahlungen im ersten Monat").
  - "nicht_erfuellt": eindeutig eine Hürde laut Text, z.B. ein zwingend \
geforderter regelmäßiger Gehaltseingang. Ein sonstiger regelmäßiger \
Geldeingang (nicht zwingend Gehalt) zählt NICHT als Hürde, sondern als \
"erfuellt".
  - "zu_pruefen": unklar formuliert oder nicht eindeutig aus dem Text zu \
beurteilen.
Ist im Text keine Bedingung erkennbar, eine leere Liste zurückgeben.

Angebotstext:
{text}"""


def ist_relevantes_angebot(client: AnthropicMessagesClient, roh_text: str, *, model: str) -> bool:
    """Themen-Check: erst bei True lohnt sich die teurere Struktur-Extraktion."""
    antwort = client.messages.parse(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": THEMEN_CHECK_PROMPT.format(text=roh_text)}],
        output_format=RelevanzErgebnis,
    )
    ergebnis = getattr(antwort, "parsed_output", None)
    if ergebnis is None:
        logger.warning("Themen-Check lieferte kein auswertbares Ergebnis (stop_reason=%s)", getattr(antwort, "stop_reason", "?"))
        return False
    return bool(ergebnis.ist_relevant)


def extrahiere_angebot(client: AnthropicMessagesClient, roh_text: str, *, model: str) -> AngebotExtraktion | None:
    """Struktur-Extraktion. None, wenn die KI kein auswertbares Ergebnis liefert
    (z.B. Refusal) - der Fund wird dann in lauf.py übersprungen und geloggt,
    nicht stillschweigend verworfen."""
    antwort = client.messages.parse(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": EXTRAKTION_PROMPT.format(text=roh_text)}],
        output_format=AngebotExtraktion,
    )
    ergebnis = getattr(antwort, "parsed_output", None)
    if ergebnis is None:
        logger.warning(
            "Struktur-Extraktion lieferte kein auswertbares Ergebnis (stop_reason=%s)",
            getattr(antwort, "stop_reason", "?"),
        )
    return ergebnis
