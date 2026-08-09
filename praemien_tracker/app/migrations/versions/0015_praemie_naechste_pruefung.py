"""praemien.naechste_pruefung_am

Neue Spalte für das Datum, bis zu dem eine offene Prämie zuletzt/als
nächstes auf Eingang geprüft wurde - reiner Merkposten für die
Todo-Ansicht ("Auf Prämie warten"), per Button um 2 Wochen verschiebbar.
Solange leer, zeigt die Oberfläche einen berechneten Vorschlag an (siehe
derived.praemie_naechste_pruefung).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-09 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("praemien", sa.Column("naechste_pruefung_am", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("praemien", "naechste_pruefung_am")
