from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _fremdschluessel_aktivieren(dbapi_connection, connection_record) -> None:
    """SQLite prüft Fremdschlüssel nur bei ausdrücklich gesetztem Pragma, und
    das gilt je Verbindung. Ohne das lassen sich Prämien, Bedingungen usw. mit
    einer deal_id anlegen, zu der es keinen Deal gibt - solche Waisen tauchen
    danach in keiner Ansicht mehr auf."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
