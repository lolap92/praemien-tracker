from pathlib import Path

from fastapi.templating import Jinja2Templates

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


templates.env.filters["eur"] = format_eur
templates.env.filters["eur_ganz"] = format_eur_ganz
templates.env.filters["datum"] = format_date
