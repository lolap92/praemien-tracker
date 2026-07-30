"""Gemeinsame Testumgebung.

Wichtig: DATA_DIR und CONFIG_DIR müssen gesetzt sein, *bevor* irgendein
praemien_tracker-Modul importiert wird - config.py legt die Verzeichnisse
beim Import an und database.py baut daraus die Engine. Deshalb steht das
hier auf Modulebene und nicht in einer Fixture.
"""

import os
import tempfile

_TESTVERZEICHNIS = tempfile.mkdtemp(prefix="praemien-tracker-tests-")
os.environ["DATA_DIR"] = _TESTVERZEICHNIS
os.environ["CONFIG_DIR"] = _TESTVERZEICHNIS

import pytest  # noqa: E402

from praemien_tracker.database import SessionLocal, engine  # noqa: E402
from praemien_tracker.models import Base  # noqa: E402

Base.metadata.create_all(engine)


@pytest.fixture()
def db():
    """Leere Datenbank je Test - die Tabellen werden zwischen den Tests
    geleert, damit sich Tests nicht über die Reihenfolge beeinflussen."""
    with SessionLocal() as sitzung:
        yield sitzung
        sitzung.rollback()
    with engine.begin() as verbindung:
        for tabelle in reversed(Base.metadata.sorted_tables):
            verbindung.exec_driver_sql(f"DELETE FROM {tabelle.name}")
