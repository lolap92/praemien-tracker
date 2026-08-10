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
import threading

from pydantic import BaseModel

from . import config
from .anthropic_client import anthropic_client

logger = logging.getLogger("praemien_tracker")

KWK_PROMPT = (
    "Bietet die Bank \"{bank}\" in Deutschland für ein {kontoart} ein "
    "\"Kunden wirbt Kunden\"-Programm an (Empfehlungsprämie für die Werbung "
    "neuer Kundinnen/Kunden)? Recherchiere über die Websuche den aktuellen "
    "Stand und gib bei Erfolg die offizielle URL der konkreten Programm-Seite "
    "auf der Bank-Website an (die Seite, die das Werbeprogramm selbst "
    "beschreibt - nicht die Startseite oder eine allgemeine Produktseite). "
    "Wenn du keine verlässliche, auf diese Bank bezogene Information findest, "
    "setze moeglich auf false und lass url leer."
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


# Hintergrund-Recherche für den Übernehmen-Vorschau-Schritt (siehe
# routers/vorschlaege.uebernehmen und helpers.kwk_recherche_vorab_starten):
# moeglichkeit_recherchieren() lief bisher synchron beim Anlegen jedes
# einzelnen Deals und blockierte dadurch "Übernehmen" - bei mehreren
# ausgewählten Inhabern derselben Gruppe sogar mehrfach hintereinander, obwohl
# das Ergebnis für alle identisch ist (dieselbe Bank+Kontoart). Die Recherche
# läuft jetzt stattdessen einmal je Bank+Kontoart im Hintergrund, während der
# Nutzer die Vorschau sieht/bearbeitet - Locking dedupliziert parallele
# Anfragen für denselben Schlüssel statt einen zweiten Thread zu starten.
_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_ergebnisse: dict[str, tuple[str | None, bool]] = {}


def hintergrund_starten(schluessel: str, bank_name: str, kontoart: str) -> None:
    """Startet moeglichkeit_recherchieren() in einem eigenen Thread,
    dedupliziert über `schluessel` - ein zweiter Aufruf für denselben
    Schlüssel, während der erste Thread noch läuft (z.B. mehrere ausgewählte
    Inhaber im selben Übernehmen-Vorgang), startet keinen zweiten Thread, da
    ohnehin dasselbe Ergebnis gilt. Das Ergebnis wird über ergebnis_abholen()
    abgeholt.

    Ist der vorherige Thread für denselben Schlüssel dagegen schon fertig,
    aber sein Ergebnis nie abgeholt worden (z.B. eine Vorschau, die der
    Nutzer nie bestätigt hat), wird trotzdem neu recherchiert statt für immer
    auf dem alten, nie abgeholten Ergebnis sitzen zu bleiben - das alte
    Ergebnis wird dabei verworfen, damit ergebnis_abholen() nicht versehentlich
    die Antwort eines längst abgebrochenen Vorgangs ausliefert."""
    with _lock:
        bestehend = _threads.get(schluessel)
        if bestehend is not None and bestehend.is_alive():
            return
        _ergebnisse.pop(schluessel, None)

        def _ausfuehren() -> None:
            ergebnis = moeglichkeit_recherchieren(bank_name, kontoart)
            with _lock:
                _ergebnisse[schluessel] = ergebnis

        thread = threading.Thread(target=_ausfuehren, daemon=True, name="kwk-recherche")
        _threads[schluessel] = thread
        thread.start()


def ergebnis_abholen(schluessel: str, timeout: float) -> tuple[str | None, bool] | None:
    """Wartet bis zu `timeout` Sekunden auf den mit hintergrund_starten() für
    denselben Schlüssel gestarteten Thread und liefert dessen Ergebnis. None,
    wenn kein passender Thread bekannt ist oder er in der Zeit nicht fertig
    wurde - der Aufrufer (helpers.kwk_ergebnis_anwenden) legt dann statt eines
    Ergebnisses eine einfache Erinnerungs-Aufgabe an, damit "Übernehmen" nie
    auf eine hängende Websuche wartet.

    Räumt den Schlüssel danach auf (auch bei Timeout), damit ein späterer,
    unabhängiger Übernehmen-Vorgang für dieselbe Bank+Kontoart erneut
    recherchiert statt auf einem alten Ergebnis sitzen zu bleiben - bewusst
    kein Cache, siehe Moduldocstring."""
    with _lock:
        thread = _threads.pop(schluessel, None)
    if thread is None:
        return None
    thread.join(timeout)
    with _lock:
        return _ergebnisse.pop(schluessel, None)
