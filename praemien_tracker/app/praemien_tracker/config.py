"""Zentrale Konfiguration: Datenpfade und Port.

Home Assistant mountet das persistente Add-on-Datenverzeichnis unter /data
(automatisch, ohne map-Eintrag, aber nicht per Samba/Datei-Explorer
erreichbar) und - dank map: addon_config in config.yaml - das
Add-on-Konfigurationsverzeichnis unter /config (erscheint auf dem Green
unter addon_configs/<slug> und ist damit z.B. per Samba erreichbar). Lokal
(außerhalb des Containers) werden stattdessen ./data und ./config verwendet.
"""

import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "./config"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

SEED_PATH = CONFIG_DIR / "seed-data.json"

PORT = int(os.environ.get("PORT", "8000"))

# Add-on-Optionen. Home Assistant schreibt die vom Nutzer in der
# Konfiguration-Registerkarte gesetzten Werte automatisch nach
# /data/options.json (also innerhalb von DATA_DIR) - kein map-Eintrag nötig,
# anders als bei seed-data.json. Lokal/in Tests existiert die Datei schlicht
# nicht, dann gelten die Vorgaben unten.
OPTIONS_PATH = Path(os.environ.get("OPTIONS_PATH", str(DATA_DIR / "options.json")))


def _lade_optionen() -> dict:
    if not OPTIONS_PATH.exists():
        return {}
    try:
        return json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _mindestpraemie(wert) -> Decimal:
    try:
        return Decimal(str(wert))
    except (InvalidOperation, TypeError):
        return Decimal("50")


def _benachrichtigungsgeraete(wert) -> list[str]:
    """Kommagetrennte Liste von Home-Assistant-Notify-Diensten (ohne
    "notify."-Präfix) in eine bereinigte Liste übersetzen - erlaubt mehrere
    Geräte in einem einzigen Textfeld. Leer oder "notify" adressiert weiterhin
    alle Geräte."""
    if not wert or not str(wert).strip():
        return ["notify"]
    geraete = [g.strip() for g in str(wert).split(",") if g.strip()]
    return geraete or ["notify"]


_OPTIONEN = _lade_optionen()

# Demo-Modus: zeigt ausschließlich frei erfundene Testdaten, um die App
# vorführen zu können, ohne echte Daten offenzulegen. Läuft dafür auf einer
# komplett eigenen Datenbankdatei (demo.db statt praemien.db) - dieselbe
# DATABASE_URL, mit der die ganze App arbeitet, zeigt dann durchgängig auf
# die Demo-Datei. Es gibt keinen Codepfad, der beide Dateien gleichzeitig
# anfasst, ein Durchsickern echter Daten in den Demo-Modus (oder umgekehrt)
# ist dadurch strukturell ausgeschlossen, nicht nur per Konvention.
DEMO_MODUS: bool = bool(_OPTIONEN.get("demo_modus", False))

DB_PATH = DATA_DIR / ("demo.db" if DEMO_MODUS else "praemien.db")
DB_BACKUP_PATH = DATA_DIR / ("demo.db.bak" if DEMO_MODUS else "praemien.db.bak")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# API-Key bewusst zusätzlich über eine Umgebungsvariable überschreibbar (z.B.
# für lokale Entwicklung ohne Add-on-Optionen) - options.json gewinnt, wenn
# beide gesetzt sind, da sie der offizielle Weg im Add-on ist.
ANTHROPIC_API_KEY: str | None = _OPTIONEN.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or None
ANTHROPIC_MODEL: str = _OPTIONEN.get("anthropic_model") or "claude-haiku-4-5"
MINDESTPRAEMIE: Decimal = _mindestpraemie(_OPTIONEN.get("mindestpraemie", 50))
MYDEALZ_GRUPPE: str = _OPTIONEN.get("mydealz_gruppe") or "vertraege-finanzen"
SPARTANIEN_URL: str = _OPTIONEN.get("spartanien_url") or "https://www.spartanien.de/"

# Benachrichtigung bei neuen Vorschlägen (Konzept Abschnitt 6).
# "benachrichtigungsgeraete" ist eine kommagetrennte Liste von Home-
# Assistant-Dienstnamen ohne "notify."-Präfix - z.B. "mobile_app_pixel_8",
# um gezielt ein oder mehrere Smartphones statt aller Geräte zu erreichen
# (siehe Einstellungen > Personen > Gerät in HA für den genauen Namen).
# Leer/"notify" adressiert weiterhin alle Geräte (notify.notify).
BENACHRICHTIGUNGEN_AKTIV: bool = bool(_OPTIONEN.get("benachrichtigungen_aktiv", True))
NOTIFY_GERAETE: list[str] = _benachrichtigungsgeraete(_OPTIONEN.get("benachrichtigungsgeraete"))
