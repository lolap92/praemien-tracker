"""storniert, freibetrag_jahr, pruefung_geprueft, bedingungen.erfuellt_am

Vier neue Spalten für die Fachlogik-Änderungen aus dem Review:

- deals.storniert: trennt "nie zustande gekommen" von "gekündigt". Bisher
  setzte das Stornieren gekuendigt=True, wodurch stornierte Deals dauerhaft in
  der Sperrfristen-Auswertung standen.
- deals.freibetrag_jahr: der Sparer-Pauschbetrag gilt pro Kalenderjahr, eine
  jahresübergreifende Summe beantwortet keine sinnvolle Frage. Bestehende
  Freibeträge werden dem Jahr 2026 zugerechnet.
- deals.pruefung_geprueft: welche Auffälligkeit in welchem Zustand als
  angesehen abgehakt wurde (siehe derived.pruefpunkte).
- bedingungen.erfuellt_am: Bezugspunkt für die Überfälligkeit einer Prämie
  ohne hinterlegten Auszahlungsmonat. Für bereits erfüllte Bedingungen wird
  das Datum aus dem Änderungsprotokoll übernommen, soweit vorhanden - dessen
  Zeitstempel sind UTC und werden dabei in Ortszeit umgerechnet. Wo es keinen
  Eintrag gibt (erfüllt vor Version 1.6.0), bleibt die Spalte leer und löst
  damit keine Überfälligkeit aus: bewusst konservativ, lieber eine Meldung zu
  wenig als eine falsche.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30 00:00:00.000000

"""
import datetime
import logging

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# Vorgabe: bestehende Freibeträge zählen zum Jahr 2026.
FREIBETRAG_JAHR_BESTAND = 2026


def upgrade() -> None:
    op.add_column("deals", sa.Column("storniert", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("deals", sa.Column("freibetrag_jahr", sa.Integer(), nullable=True))
    op.add_column("deals", sa.Column("pruefung_geprueft", sa.Text(), nullable=True))
    op.add_column("bedingungen", sa.Column("erfuellt_am", sa.Date(), nullable=True))

    verbindung = op.get_bind()

    ergebnis = verbindung.execute(
        sa.text("UPDATE deals SET freibetrag_jahr = :jahr WHERE freibetrag IS NOT NULL"),
        {"jahr": FREIBETRAG_JAHR_BESTAND},
    )
    if ergebnis.rowcount:
        logger.info(
            "Freibetrag von %d Deals dem Jahr %d zugeordnet.", ergebnis.rowcount, FREIBETRAG_JAHR_BESTAND
        )

    # Erfüllungsdatum aus dem Protokoll nachtragen: je Bedingung der jüngste
    # Eintrag, der erfuellt auf True gesetzt hat.
    if "protokoll" not in sa.inspect(verbindung).get_table_names():
        return
    zeilen = verbindung.execute(
        sa.text(
            "SELECT objekt_id, MAX(zeitpunkt) FROM protokoll "
            "WHERE tabelle = 'Bedingung' AND feld = 'erfuellt' AND neuer_wert = 'True' "
            "GROUP BY objekt_id"
        )
    ).all()
    nachgetragen = 0
    for bedingung_id, zeitpunkt in zeilen:
        if not zeitpunkt:
            continue
        if isinstance(zeitpunkt, str):
            try:
                zeitpunkt = datetime.datetime.fromisoformat(zeitpunkt)
            except ValueError:
                continue
        # Protokoll-Zeitstempel sind UTC; für ein Kalenderdatum zählt die Ortszeit.
        lokal = zeitpunkt.replace(tzinfo=datetime.timezone.utc).astimezone()
        ergebnis = verbindung.execute(
            sa.text(
                "UPDATE bedingungen SET erfuellt_am = :datum WHERE id = :id AND erfuellt = 1"
            ),
            {"datum": lokal.date(), "id": bedingung_id},
        )
        nachgetragen += ergebnis.rowcount
    if nachgetragen:
        logger.info("Erfüllungsdatum für %d Bedingungen aus dem Protokoll übernommen.", nachgetragen)


def downgrade() -> None:
    op.drop_column("bedingungen", "erfuellt_am")
    op.drop_column("deals", "pruefung_geprueft")
    op.drop_column("deals", "freibetrag_jahr")
    op.drop_column("deals", "storniert")
