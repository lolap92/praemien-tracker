"""Zentrale Konfiguration: Datenpfade und Port.

Home Assistant mountet das persistente Add-on-Datenverzeichnis unter /data
(automatisch, ohne map-Eintrag, aber nicht per Samba/Datei-Explorer
erreichbar) und - dank map: addon_config in config.yaml - das
Add-on-Konfigurationsverzeichnis unter /config (erscheint auf dem Green
unter addon_configs/<slug> und ist damit z.B. per Samba erreichbar). Lokal
(außerhalb des Containers) werden stattdessen ./data und ./config verwendet.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "./config"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "praemien.db"
DB_BACKUP_PATH = DATA_DIR / "praemien.db.bak"
DATABASE_URL = f"sqlite:///{DB_PATH}"

SEED_PATH = CONFIG_DIR / "seed-data.json"

PORT = int(os.environ.get("PORT", "8000"))
