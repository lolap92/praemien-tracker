"""KI-Recherche per Web-Suche, ob eine Bank für eine Kontoart ein "Kunden
wirbt Kunden"-Programm (Empfehlungsprämie) anbietet - analog zu
kuendigung_recherche.py, aber bewusst ohne Cache: ein KwK-Programm ist oft
eine befristete Marketing-Aktion und ändert sich regelmäßiger als ein
Kündigungsweg - ein veraltetes "gibt es nicht" aus einem Cache wäre riskanter
als der zusätzliche API-Aufruf. Läuft deshalb auch nur einmalig beim Anlegen
eines Deals (siehe helpers.kwk_vorschlag), nicht im täglichen
KI-Deal-Finder-Lauf - dort gäbe es ohne Cache keinen verlässlichen Schutz vor
wiederholten Aufrufen für dieselbe Bank.

Ohne hinterlegten API-Key oder wenn nichts gefunden wird, passiert einfach
nichts - reine Ergänzung, kein Blockierer für die Deal-Anlage. Schlägt die
Recherche selbst fehl (API-Fehler, kein auswertbares Ergebnis), bekommt der
Nutzer stattdessen einen Hinweis, es manuell zu prüfen (siehe
helpers.kwk_vorschlag und routers/vorschlaege.uebernehmen).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from . import config
from .anthropic_client import anthropic_client

logger = logging.getLogger("praemien_tracker")

KWK_PROMPT = (
    "Bietet die Bank \"{bank}\" in Deutschland für ein {kontoart} ein "
    "\"Kunden wirbt Kunden\"-Programm an (Empfehlungsprämie für die Werbung "
    "neuer Kundinnen/Kunden)? Recherchiere über die Websuche den aktuellen "
    "Stand und gib bei Erfolg die offizielle URL der zugehörigen Seite auf "
    "der Bank-Website an. Wenn du keine verlässliche, auf diese Bank "
    "bezogene Information findest, setze moeglich auf false und lass url "
    "leer."
)


class _KwkErgebnis(BaseModel):
    moeglich: bool
    url: str = ""


def moeglichkeit_recherchieren(bank_name: str, kontoart: str) -> tuple[str | None, bool]:
    """Liefert (url, fehlgeschlagen).

    - (url, False): die Bank bietet für diese Kontoart ein KwK-Programm an,
      url zeigt auf die zugehörige Seite.
    - (None, False): kein API-Key hinterlegt, oder verlässlich ermittelt,
      dass es kein Programm gibt - beides kein Fehler, einfach kein Treffer.
    - (None, True): die Recherche ist fehlgeschlagen (API-Fehler, kein
      auswertbares Ergebnis, oder "möglich" ohne belastbare URL) - unbekannt,
      ob es ein Programm gibt. Der Aufrufer (helpers.kwk_vorschlag) nutzt das,
      um den Nutzer auf eine manuelle Prüfung hinzuweisen, statt es einfach
      zu verschweigen."""
    client = anthropic_client()
    if client is None:
        return None, False

    try:
        antwort = client.messages.parse(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": KWK_PROMPT.format(bank=bank_name, kontoart=kontoart)}],
            output_format=_KwkErgebnis,
        )
    except Exception:
        logger.exception("Kunden-wirbt-Kunden-Recherche für %s (%s) fehlgeschlagen.", bank_name, kontoart)
        return None, True

    ergebnis = antwort.parsed_output
    if ergebnis is None:
        return None, True
    if not ergebnis.moeglich:
        return None, False
    url = ergebnis.url.strip()
    if not url:
        return None, True
    return url, False
