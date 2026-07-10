from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


templates.env.filters["eur"] = format_eur
templates.env.filters["datum"] = format_date
