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

import logging
import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect

from .config import DATABASE_URL, DB_BACKUP_PATH, DB_PATH
from .database import SessionLocal, engine
from .kuendigung_hinweise import backfill_kuendigung_hinweise
from .routers import completeness, deals, overview, sperrfristen, todos
from .seed import import_seed_data
from .templating import STATIC_DIR

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


def run_migrations() -> None:
    db_existed = DB_PATH.exists()
    cfg = _alembic_config()

    if db_existed:
        shutil.copy2(DB_PATH, DB_BACKUP_PATH)
        logger.info("Sicherheitskopie erstellt: %s", DB_BACKUP_PATH)

        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            logger.info("Bestehende Datenbank ohne Versionsstand - markiere als Baseline (head).")
            command.stamp(cfg, "head")
            return

        command.upgrade(cfg, "head")
        logger.info("Migrationen angewendet, Datenbank auf aktuellem Stand.")
        with SessionLocal() as db:
            anzahl = backfill_kuendigung_hinweise(db)
            if anzahl:
                logger.info("Kündigung-Anweisungen für %d Deals vorgeschlagen.", anzahl)
        return

    command.upgrade(cfg, "head")
    logger.info("Neue Datenbank angelegt, Schema auf aktuellem Stand.")

    with SessionLocal() as db:
        import_seed_data(db)
        backfill_kuendigung_hinweise(db)


def create_app() -> FastAPI:
    app = FastAPI(title="Prämien-Tracker")

    @app.on_event("startup")
    def on_startup() -> None:
        run_migrations()

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

    return app


app = create_app()
