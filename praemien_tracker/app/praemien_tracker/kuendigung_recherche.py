"""KI-Recherche eines Kündigungswegs per Web-Suche, wenn KUENDIGUNG_HINWEISE
(fest hinterlegt, siehe kuendigung_hinweise.py) keinen Eintrag für Bank+
Kontoart kennt.

Läuft ausschließlich im nächtlichen Batch (naechtlicher_lauf, per
APScheduler-Job in main.py) statt direkt beim Anlegen eines Deals - ein Deal
wartet dadurch nie auf eine KI-Websuche (frühere synchrone Variante konnte
"Übernehmen"/die manuelle Anlage für eine noch nie recherchierte Bank+
Kontoart-Kombination spürbar blockieren). Ein neu angelegter Deal ohne fest
hinterlegten Hinweis (helpers.kuendigung_vorschlag) bekommt seinen
KI-recherchierten Hinweis dadurch typischerweise erst am nächsten Morgen
statt sofort - für einen Kündigungsweg, der sich selten ändert und beim
Anlegen meist noch nicht gebraucht wird, ein vertretbarer Tausch gegen ein
nie blockierendes Anlegen.

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

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import config
from .anthropic_client import anthropic_client
from .database import SessionLocal
from .kuendigung_hinweise import hinweis_fuer
from .models import Deal, KuendigungRecherche

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


def alle_ohne_hinweis_nachtragen(db: Session) -> int:
    """Nächtlicher Batch: trägt für alle offenen Deals ohne Kündigungshinweis
    einen nach - zuerst aus der festen Tabelle (kein API-Aufruf; deckt Fälle
    ab, in denen KUENDIGUNG_HINWEISE nach der Deal-Anlage um einen Eintrag
    ergänzt wurde), sonst per KI-Websuche mit demselben DB-Cache wie bisher
    (hinweis_recherchieren) - eine Bank+Kontoart-Kombination wird dadurch
    über alle betroffenen Deals hinweg nur einmal recherchiert.

    Storniert Deals werden übersprungen - ein Deal, der nie zustande kam,
    braucht keinen Kündigungsweg, das wäre ein unnötiger API-Aufruf. Ein
    schon gesetzter Hinweis wird nie überschrieben (siehe
    helpers.kuendigung_vorschlag) - nur Deals mit kuendigung_hinweis IS NULL
    kommen überhaupt in Frage.

    Liefert die Anzahl der Deals, für die dabei ein Hinweis ergänzt wurde."""
    deals = (
        db.query(Deal)
        .filter(Deal.kuendigung_hinweis.is_(None), Deal.storniert.is_(False))
        .all()
    )
    aktualisiert = 0
    for deal in deals:
        if deal.bank is None:
            continue
        eintrag = hinweis_fuer(deal.bank.name, deal.kontoart)
        ki_recherchiert = False
        if eintrag is None:
            eintrag = hinweis_recherchieren(db, deal.bank.name, deal.kontoart)
            ki_recherchiert = True
        if eintrag is None:
            continue
        deal.kuendigung_hinweis, deal.kuendigung_hinweis_url = eintrag
        deal.kuendigung_hinweis_ki = ki_recherchiert
        aktualisiert += 1
    db.commit()
    return aktualisiert


def naechtlicher_lauf() -> None:
    """Einstiegspunkt für den APScheduler-Job (main.py) - öffnet eine eigene
    Session, da der Job außerhalb eines Requests läuft. Läuft zeitversetzt
    vor dem KI-Deal-Finder (siehe main._scheduler_starten), damit beide
    Jobs nicht gleichzeitig gegen dieselbe SQLite-Datenbank schreiben.
    Fehler werden geloggt statt den Scheduler zum Absturz zu bringen -
    analog zu finder.lauf.geplanter_lauf()."""
    try:
        with SessionLocal() as db:
            anzahl = alle_ohne_hinweis_nachtragen(db)
        logger.info("Nächtlicher Kündigungshinweis-Batch: %d Deal(s) aktualisiert.", anzahl)
    except Exception:
        logger.exception("Nächtlicher Kündigungshinweis-Batch fehlgeschlagen.")
