"""KI-Recherche eines Kündigungswegs per Web-Suche, wenn KUENDIGUNG_HINWEISE
(fest hinterlegt, siehe kuendigung_hinweise.py) keinen Eintrag für Bank+
Kontoart kennt.

Das Ergebnis wird in der Datenbank gecacht (KuendigungRecherche), damit
dieselbe Bank+Kontoart-Kombination nicht wiederholt gegen die API geschickt
wird - dieselbe Kostenersparnis-Idee wie beim KI-Deal-Finder (finder/lauf.py).
Nutzt bewusst web_search_20250305 statt einer neueren Variante, weil das
konfigurierte Modell (config.ANTHROPIC_MODEL) auch ein älteres/kleineres wie
Haiku sein kann.

Ohne hinterlegten API-Key bleibt der Kündigungshinweis wie bisher leer -
diese Recherche ist eine reine Ergänzung, kein Ersatz für die feste Tabelle.
"""

from __future__ import annotations

import logging
import threading

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import config
from .anthropic_client import anthropic_client
from .database import SessionLocal
from .models import KuendigungRecherche

logger = logging.getLogger("praemien_tracker")

RECHERCHE_PROMPT = (
    "Wie kündigt man in Deutschland ein {kontoart} bei der Bank \"{bank}\"? "
    "Recherchiere über die Websuche den aktuellen, offiziellen Kündigungsweg "
    "(z. B. Online-Kündigung im Kundenportal, Kündigungsformular, schriftliche "
    "Kündigung per Post) und fasse die konkreten Schritte in 2-4 Sätzen auf "
    "Deutsch zusammen. Gib außerdem die URL der Quelle an, auf der du die "
    "Information gefunden hast. Wenn du keine verlässliche, auf diese Bank "
    "bezogene Information findest, setze gefunden auf false und lass "
    "anleitung sowie quelle_url leer."
)


class _KuendigungswegErgebnis(BaseModel):
    gefunden: bool
    anleitung: str = ""
    quelle_url: str = ""


def _recherchieren(client: anthropic.Anthropic, bank_name: str, kontoart: str) -> tuple[str, str] | None:
    try:
        antwort = client.messages.parse(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[
                {"role": "user", "content": RECHERCHE_PROMPT.format(bank=bank_name, kontoart=kontoart)}
            ],
            output_format=_KuendigungswegErgebnis,
        )
    except Exception:
        logger.exception("Kündigungsweg-Recherche für %s (%s) fehlgeschlagen.", bank_name, kontoart)
        return None

    ergebnis = antwort.parsed_output
    if ergebnis is None or not ergebnis.gefunden or not ergebnis.anleitung.strip():
        return None
    return ergebnis.anleitung.strip(), ergebnis.quelle_url.strip()


def hinweis_recherchieren(db: Session, bank_name: str, kontoart: str) -> tuple[str, str] | None:
    """Liefert einen KI-recherchierten Kündigungsweg für Bank+Kontoart - aus
    dem Cache, falls schon einmal recherchiert, sonst frisch über die API.
    None, wenn kein API-Key hinterlegt ist oder die Recherche nichts
    Verlässliches findet - dann bleibt der Kündigungshinweis wie bisher leer.
    """
    gecacht = (
        db.query(KuendigungRecherche)
        .filter(KuendigungRecherche.bank_name == bank_name, KuendigungRecherche.kontoart == kontoart)
        .one_or_none()
    )
    if gecacht is not None:
        return gecacht.hinweis, gecacht.hinweis_url

    client = anthropic_client()
    if client is None:
        return None

    ergebnis = _recherchieren(client, bank_name, kontoart)
    if ergebnis is None:
        return None

    hinweis, hinweis_url = ergebnis
    db.add(KuendigungRecherche(bank_name=bank_name, kontoart=kontoart, hinweis=hinweis, hinweis_url=hinweis_url))
    db.commit()
    return hinweis, hinweis_url


# Hintergrund-Recherche für den Übernehmen-Vorschau-Schritt (siehe
# routers/vorschlaege.uebernehmen_vorschau und
# helpers.kuendigung_hinweis_vorab_starten): hinweis_recherchieren() lief
# bisher synchron beim Anlegen jedes einzelnen Deals und konnte "Übernehmen"
# für eine noch nie recherchierte Bank+Kontoart-Kombination spürbar blockieren
# (Cache greift erst ab dem zweiten Mal) - analog zu kwk_recherche.py läuft
# sie jetzt stattdessen einmal je Bank+Kontoart im Hintergrund, während der
# Nutzer die Vorschau sieht/bearbeitet. Eigene DB-Session (SessionLocal), da
# der Thread außerhalb des Requests läuft und dessen Session zu diesem
# Zeitpunkt schon geschlossen sein kann.
_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_ergebnisse: dict[str, tuple[str, str] | None] = {}


def hintergrund_starten(schluessel: str, bank_name: str, kontoart: str) -> None:
    """Startet hinweis_recherchieren() in einem eigenen Thread mit eigener
    Session, dedupliziert über `schluessel` - ein zweiter Aufruf für denselben
    Schlüssel, während der erste Thread noch läuft, startet keinen zweiten.
    Ist der vorherige Thread für denselben Schlüssel dagegen schon fertig,
    aber sein Ergebnis nie abgeholt worden, wird trotzdem neu recherchiert
    statt für immer auf dem alten, nie abgeholten Ergebnis sitzen zu bleiben -
    siehe kwk_recherche.hintergrund_starten für dieselbe Überlegung."""
    with _lock:
        bestehend = _threads.get(schluessel)
        if bestehend is not None and bestehend.is_alive():
            return
        _ergebnisse.pop(schluessel, None)

        def _ausfuehren() -> None:
            try:
                with SessionLocal() as eigene_db:
                    ergebnis = hinweis_recherchieren(eigene_db, bank_name, kontoart)
            except Exception:
                logger.exception("Hintergrund-Kündigungsweg-Recherche für %s (%s) fehlgeschlagen.", bank_name, kontoart)
                ergebnis = None
            with _lock:
                _ergebnisse[schluessel] = ergebnis

        thread = threading.Thread(target=_ausfuehren, daemon=True, name="kuendigung-recherche")
        _threads[schluessel] = thread
        thread.start()


def ergebnis_abholen(schluessel: str, timeout: float) -> tuple[str, str] | None:
    """Wartet bis zu `timeout` Sekunden auf den mit hintergrund_starten() für
    denselben Schlüssel gestarteten Thread und liefert dessen Ergebnis - None
    sowohl bei Timeout als auch bei einer legitim erfolglosen Recherche
    (beides führt beim Aufrufer zum selben Verhalten: das Feld bleibt leer,
    siehe helpers.kuendigung_ergebnis_anwenden)."""
    with _lock:
        thread = _threads.pop(schluessel, None)
    if thread is None:
        return None
    thread.join(timeout)
    with _lock:
        return _ergebnisse.pop(schluessel, None)
