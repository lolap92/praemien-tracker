"""Einstiegspunkt: FastAPI-App inkl. automatischer Alembic-Migrationen.

Ablauf beim Start (Konzept Abschnitt 7):
- Existiert noch keine Datenbank, wird sie über die Migrationen frisch angelegt.
- Existiert bereits eine Datenbank ohne Versionsstand (z. B. eine einmalig
  hochgeladene Start-DB), wird sie als Baseline auf den aktuellen Stand
  gestempelt, statt die Tabellen erneut anzulegen.
- Andernfalls werden ausstehende Migrationen angewendet.
- Vor jeder Migration wird die Datenbankdatei als Sicherheitsnetz kopiert.
"""

from __future__ import annotations

import datetime
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect

from . import protokoll  # noqa: F401  (registriert die Änderungsprotokoll-Events)
from .config import DATABASE_URL, DB_BACKUP_PATH, DB_PATH
from .database import SessionLocal, engine
from .routers import completeness, deals, overview, protokoll as protokoll_router, sperrfristen, todos
from .seed import import_seed_data
from .templating import STATIC_DIR, templates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("praemien_tracker")
logger.setLevel(logging.INFO)

APP_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = APP_DIR.parent / "migrations"
ALEMBIC_INI = APP_DIR.parent / "alembic.ini"


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def _ausstehende_migration(cfg: AlembicConfig) -> str | None:
    """Ziel-Revision, falls eine Migration ansteht - sonst None.

    Ohne diese Prüfung würde bei *jedem* Start kopiert. Die Sicherung wäre
    damit eine Momentaufnahme des letzten Starts statt des Zustands vor der
    Migration: Ein einziger Neustart nach einem Datenverlust genügt, und die
    Kopie enthält den kaputten Stand.
    """
    kopf = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as verbindung:
        stand = MigrationContext.configure(verbindung).get_current_revision()
    return kopf if stand != kopf else None


def _sicherheitskopie(ziel_revision: str) -> None:
    """Die Ziel-Revision steht im Dateinamen, damit eine spätere Migration die
    vorige Sicherung nicht verdrängt und man der Datei ansieht, wovor sie
    schützt."""
    pfad = DB_BACKUP_PATH.with_name(f"{DB_PATH.name}.vor-{ziel_revision}.bak")
    shutil.copy2(DB_PATH, pfad)
    logger.info("Sicherheitskopie vor Migration %s erstellt: %s", ziel_revision, pfad)


def run_migrations() -> None:
    db_existed = DB_PATH.exists()
    cfg = _alembic_config()

    if db_existed:
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            logger.info("Bestehende Datenbank ohne Versionsstand - markiere als Baseline (head).")
            _sicherheitskopie("baseline")
            command.stamp(cfg, "head")
            return

        ziel = _ausstehende_migration(cfg)
        if ziel is None:
            logger.info("Keine Migration ausstehend, Datenbank auf aktuellem Stand.")
            return

        _sicherheitskopie(ziel)
        command.upgrade(cfg, "head")
        logger.info("Migrationen angewendet, Datenbank auf Stand %s.", ziel)
        return

    command.upgrade(cfg, "head")
    logger.info("Neue Datenbank angelegt, Schema auf aktuellem Stand.")

    with SessionLocal() as db:
        import_seed_data(db)


def _zeitzone_protokollieren() -> None:
    """Erkannte Zeitzone ins Log schreiben.

    Zeitpunkte werden in UTC gespeichert und erst bei der Anzeige umgerechnet.
    Kennt der Container keine Zeitzone, ist "Ortszeit" gleich UTC - das fällt
    sonst nur als still falsche Uhrzeit im Protokoll auf. Betroffen ist nur
    die Darstellung, die gespeicherten Daten bleiben korrekt.
    """
    jetzt = datetime.datetime.now().astimezone()
    versatz = jetzt.utcoffset() or datetime.timedelta()
    stunden = versatz.total_seconds() / 3600
    name = os.environ.get("TZ") or jetzt.tzname() or "unbekannt"
    if versatz:
        logger.info("Zeitzone: %s (UTC%+g h) - Anzeige in Ortszeit, gespeichert wird UTC.", name, stunden)
    else:
        logger.warning(
            "Zeitzone: %s, kein Versatz zu UTC. Falls die Uhrzeiten im Protokoll "
            "abweichen, ist im Container keine Zeitzone gesetzt (TZ).",
            name,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _zeitzone_protokollieren()
    run_migrations()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Prämien-Tracker", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_fehler(request: Request, exc: HTTPException):
        """Fehler als normale Seite ausliefern statt als JSON-Rumpf - die App
        wird ausschließlich im Browser benutzt."""
        return templates.TemplateResponse(
            "fehler.html",
            {"request": request, "code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    @app.middleware("http")
    async def no_cache(request, call_next):
        """Verhindert, dass die HA-Companion-App (oder andere Webviews) HTML-Seiten
        zwischenspeichert - sonst bleibt nach einem Add-on-Update die alte Seite
        (mit veraltetem CSS-Link) sichtbar, obwohl der Server bereits die neue
        Version ausliefert."""
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(overview.router)
    app.include_router(todos.router)
    app.include_router(deals.router)
    app.include_router(completeness.router)
    app.include_router(sperrfristen.router)
    app.include_router(protokoll_router.router)

    return app


app = create_app()
