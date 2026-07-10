"""Zentrale Konfiguration: Datenpfade und Port.

Home Assistant mountet das persistente Add-on-Verzeichnis unter /data.
Lokal (außerhalb des Containers) wird stattdessen ./data verwendet.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "praemien.db"
DB_BACKUP_PATH = DATA_DIR / "praemien.db.bak"
DATABASE_URL = f"sqlite:///{DB_PATH}"

PORT = int(os.environ.get("PORT", "8000"))
