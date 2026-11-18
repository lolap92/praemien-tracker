"""KI-Recherche per Web-Suche, mit welchen Verfahren man sich bei einer Bank
zur Kontoeröffnung identifizieren kann - vor allem, ob eID (Online-
Ausweisfunktion des Personalausweises) angeboten wird oder nur VideoIdent,
PostIdent bzw. der Gang in eine Filiale.

Das steht in Deal-Beschreibungen (mydealz, Spartanien, DealDoktor) fast nie,
deshalb wird es je Bank einmal über die Websuche recherchiert und in
IdentRecherche gecacht - analog zur Kündigungsweg-Recherche
(kuendigung_recherche.py). Ein Treffer wird für 180 Tage wiederverwendet
(Banken stellen ihr Verfahren selten um), ein fehlgeschlagener Versuch nach
7 Tagen wiederholt. Pro Lauf höchstens _MAX_JE_LAUF neue Recherchen, damit
ein Lauf mit vielen neuen Banken die API-Kosten nicht sprengt - der Rest
folgt beim nächsten Lauf.

Läuft im Anschluss an den KI-Deal-Finder-Lauf (finder/lauf.py) für alle
offenen Vorschläge, deren Bank noch kein Ergebnis hat. Nennt der
Angebotstext selbst ein Verfahren, hat das Vorrang (identifikation_quelle
"angebot") und wird nicht überschrieben.

Rein informativ: das Ergebnis ändert keinen Status, es erscheint als
Etikett auf der Vorschlagskarte. Ohne API-Key oder im Demo-Modus passiert
nichts.
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import config, derived
from .anthropic_client import anthropic_client
from .finder import matching
from .models import DealVorschlag, IdentRecherche

logger = logging.getLogger("praemien_tracker")

QUELLE_ANGEBOT = "angebot"
QUELLE_RECHERCHE = "recherche"

_GUELTIG_TREFFER = datetime.timedelta(days=180)
_GUELTIG_FEHLGESCHLAGEN = datetime.timedelta(days=7)
_MAX_JE_LAUF = 10

IDENT_PROMPT = (
    "Mit welchen Verfahren kann man sich in Deutschland bei der Bank \"{bank}\" "
    "aktuell zur Eröffnung eines Kontos für Privatkunden identifizieren? "
    "Recherchiere über die Websuche, bevorzugt auf der offiziellen Bank-Website "
    "(FAQ, Hilfe- oder Kontoeröffnungsseite). Mögliche Verfahren: \"eid\" = "
    "Online-Ausweisfunktion des Personalausweises (eID, AusweisApp, Ausweis per "
    "Smartphone-NFC auslesen, auch über Dienste wie Nect, sofern dabei der "
    "Ausweis-Chip genutzt wird), \"video\" = VideoIdent/Video-Chat, \"post\" = "
    "PostIdent in einer Postfiliale, \"filiale\" = Identifikation in einer "
    "Bankfiliale. Führe alle Verfahren auf, die die Bank derzeit anbietet, und "
    "gib die URL der Quelle an. Wenn du keine verlässliche, auf diese Bank "
    "bezogene Information findest, setze gefunden auf false und lass "
    "verfahren leer."
)


class _IdentErgebnis(BaseModel):
    gefunden: bool
    verfahren: list[Literal["eid", "video", "post", "filiale"]] = []
    quelle_url: str = ""


def recherchieren(client, bank_name: str) -> tuple[str | None, str | None, bool]:
    """Liefert (verfahren, quelle_url, fehlgeschlagen). verfahren None ohne
    verlässlichen Treffer; fehlgeschlagen True bei API-Fehler oder
    unbrauchbarer Antwort."""
    try:
        antwort = client.messages.parse(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": IDENT_PROMPT.format(bank=bank_name)}],
            output_format=_IdentErgebnis,
        )
    except Exception:
        logger.exception("Identifikations-Recherche für %s fehlgeschlagen.", bank_name)
        return None, None, True

    ergebnis = getattr(antwort, "parsed_output", None)
    if not isinstance(ergebnis, _IdentErgebnis):
        return None, None, True
    if not ergebnis.gefunden:
        return None, None, False
    verfahren = matching.identifikation_normalisieren(ergebnis.verfahren)
    return verfahren, (ergebnis.quelle_url.strip() or None), False


def _abgelaufen(eintrag: IdentRecherche, jetzt: datetime.datetime) -> bool:
    gueltig = _GUELTIG_FEHLGESCHLAGEN if eintrag.fehlgeschlagen else _GUELTIG_TREFFER
    return eintrag.recherchiert_am is None or jetzt - eintrag.recherchiert_am > gueltig


def offene_vorschlaege_nachtragen(db: Session, *, client=None) -> int:
    """Trägt für alle offenen Vorschläge ohne Angabe aus dem Angebotstext das
    recherchierte Identifikationsverfahren ihrer Bank ein - aus dem Cache,
    sonst per Websuche (höchstens _MAX_JE_LAUF neue Recherchen). Liefert die
    Anzahl neuer Recherchen."""
    if config.DEMO_MODUS:
        return 0
    vorschlaege = (
        db.query(DealVorschlag)
        .filter(DealVorschlag.status.in_(matching.STATUS_OFFEN))
        .all()
    )
    zu_fuellen = [v for v in vorschlaege if v.identifikation_quelle != QUELLE_ANGEBOT]
    if not zu_fuellen:
        return 0

    jetzt = datetime.datetime.utcnow()
    cache = {e.bank_schluessel: e for e in db.query(IdentRecherche).all()}
    aktiver_client = client
    recherchen = 0

    for v in zu_fuellen:
        schluessel = derived.bank_name_normalisieren(v.bank_name)
        if not schluessel:
            continue
        eintrag = cache.get(schluessel)
        if (eintrag is None or _abgelaufen(eintrag, jetzt)) and recherchen < _MAX_JE_LAUF:
            if aktiver_client is None:
                aktiver_client = anthropic_client()
                if aktiver_client is None:
                    break
            verfahren, url, fehlgeschlagen = recherchieren(aktiver_client, v.bank_name)
            recherchen += 1
            if eintrag is None:
                eintrag = IdentRecherche(bank_schluessel=schluessel, bank_name=v.bank_name.strip())
                db.add(eintrag)
                cache[schluessel] = eintrag
            # Ein früherer Treffer bleibt bei einem fehlgeschlagenen
            # Wiederholungsversuch erhalten - besser leicht veraltet als weg.
            if not (fehlgeschlagen and eintrag.verfahren):
                eintrag.verfahren = verfahren
                eintrag.quelle_url = url
            eintrag.fehlgeschlagen = fehlgeschlagen
            eintrag.recherchiert_am = jetzt
        if eintrag is not None and eintrag.verfahren:
            v.identifikation = eintrag.verfahren
            v.identifikation_quelle = QUELLE_RECHERCHE

    db.commit()
    if recherchen:
        logger.info("Identifikations-Recherche: %d Bank/Banken neu recherchiert.", recherchen)
    return recherchen

