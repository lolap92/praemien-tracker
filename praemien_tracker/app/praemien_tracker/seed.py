"""Einmaliger Seed-Import beim ersten Start (Konzept Abschnitt 8).

Statt einer fertigen praemien.db legt der Nutzer eine seed-data.json ins
Add-on-Datenverzeichnis. Ist die Datenbank beim Start frisch (noch keine
Datei vorhanden) und liegt eine seed-data.json vor, baut die App die
enthaltenen Deals daraus auf. Bei jedem weiteren Start ist die Datenbank
dann bereits vorhanden, sodass dieser Import nicht erneut läuft.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from .config import SEED_PATH
from .helpers import build_deal_from_import
from .schemas import SeedData

logger = logging.getLogger("praemien_tracker")


def import_seed_data(db: Session) -> int:
    if not SEED_PATH.exists():
        return 0

    rohdaten = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    daten = SeedData.model_validate(rohdaten)

    for deal_daten in daten.deals:
        build_deal_from_import(db, deal_daten)
    db.commit()

    logger.info("Seed-Import: %d Deals aus %s angelegt.", len(daten.deals), SEED_PATH)
    return len(daten.deals)
