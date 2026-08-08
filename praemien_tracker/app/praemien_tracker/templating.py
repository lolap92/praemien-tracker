import datetime
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .derived import quelle_label
from .finder.matching import VERWERFEN_GRUENDE_LABELS

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_STYLE_CSS = STATIC_DIR / "css" / "style.css"
templates.env.globals["asset_v"] = int(_STYLE_CSS.stat().st_mtime) if _STYLE_CSS.exists() else 0


def format_eur(value) -> str:
    if value is None:
        return "–"
    formatted = f"{float(value):,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def format_zeitpunkt(value) -> str:
    """Gespeicherte Zeitpunkte in Ortszeit ausgeben.

    erstellt_am, geaendert_am und protokoll.zeitpunkt werden ueber
    func.now() gefuellt, und SQLite liefert dafuer CURRENT_TIMESTAMP - das
    ist immer UTC, unabhaengig von der Zeitzone des Containers. Gespeichert
    bleibt UTC (eindeutig, monoton, keine Migration), umgerechnet wird erst
    hier bei der Anzeige.
    """
    if value is None:
        return "–"
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone().strftime("%d.%m.%Y %H:%M:%S")


def format_date(value) -> str:
    if value is None:
        return "–"
    return value.strftime("%d.%m.%Y")


def format_eur_ganz(value) -> str:
    """Ganzzahlige Darstellung mit Tausenderpunkt, ohne Nachkommastellen (für große Kennzahlen)."""
    if value is None:
        return "–"
    formatted = f"{float(value):,.0f}"
    return formatted.replace(",", ".")


_VORSCHLAG_STATUS_LABELS = {
    "vorgeschlagen": "vorgeschlagen",
    "zu_pruefen": "zu prüfen",
    "automatisch_abgelehnt": "abgelehnt",
}


def format_vorschlag_status(status: str) -> str:
    """Klartext für den je-Inhaber-Status einer VorschlagGruppe (siehe
    routers/vorschlaege.py) - nur angezeigt, wenn er vom Gruppen-Status
    abweicht, z.B. wenn ein Fund für eine Person schon Bestandskunde ist."""
    return _VORSCHLAG_STATUS_LABELS.get(status, status)


def format_verwerfen_gruende(value: str | None) -> list[str]:
    """Komma-getrennte Grund-Codes (DealVorschlag.verwerfen_gruende) in eine
    Liste von Klartext-Labels für die Chip-Anzeige übersetzen."""
    if not value:
        return []
    return [VERWERFEN_GRUENDE_LABELS.get(code, code) for code in value.split(",") if code]


# Reihenfolge ist relevant: Der erste passende Eintrag gewinnt, deshalb steht
# "deals/new" vor "deals".
_TABS = [
    ("deals/new", "deals/new"),
    ("deals", "deals"),
    ("todos", "todos"),
    ("vorschlaege", "vorschlaege"),
    ("completeness", "completeness"),
    ("sperrfristen", "sperrfristen"),
    ("protokoll", "protokoll"),
    ("overview", "overview"),
]


def nav_tab(request: Request) -> str:
    """Welcher Navigationspunkt hervorgehoben wird.

    Hinter Home-Assistant-Ingress trägt der Pfad ein wechselndes Präfix
    (X-Ingress-Path), das hier zuerst abgeschnitten wird - eine Prüfung auf
    das Pfadende allein trägt nicht, weil Unterseiten wie deals/3/edit
    ebenfalls zum Deals-Tab gehören.
    """
    prefix = request.headers.get("X-Ingress-Path", "")
    pfad = request.url.path
    if prefix and pfad.startswith(prefix):
        pfad = pfad[len(prefix) :]
    pfad = pfad.strip("/")
    if not pfad:
        return "overview"
    for anfang, tab in _TABS:
        if pfad == anfang or pfad.startswith(anfang + "/"):
            return tab
    return ""


templates.env.filters["eur"] = format_eur
templates.env.filters["eur_ganz"] = format_eur_ganz
templates.env.filters["datum"] = format_date
templates.env.filters["zeitpunkt"] = format_zeitpunkt
templates.env.filters["quelle"] = quelle_label
templates.env.filters["vorschlag_status"] = format_vorschlag_status
templates.env.filters["verwerfen_gruende"] = format_verwerfen_gruende
# Bewusst nicht "aktiver_tab": diesen Namen belegt der ToDo-Router schon
# mit dem gewählten ToDo-Reiter, er würde den Helfer hier überschatten.
templates.env.globals["nav_tab"] = nav_tab
