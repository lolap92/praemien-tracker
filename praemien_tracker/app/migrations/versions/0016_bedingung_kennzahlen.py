"""Strukturierte Kennzahlen der Bedingungen

Neue, optionale Spalten anzahl / betrag_euro / frist_wochen auf den
Bedingungen - sowohl auf der übernommenen Bedingung (bedingungen) als auch
auf der KI-Vorschlagsbedingung (vorschlag_bedingungen). Erlauben die kompakte
Anzeige "2× · 50 € · 4 Wochen" auf der Vorschlagskarte und beim späteren Deal;
die beschreibung bleibt die verbindliche Freitextquelle. Jeweils NULL, wenn
die Größe im Angebotstext nicht genannt war (siehe finder/extraktion.py).

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-10 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabelle in ("bedingungen", "vorschlag_bedingungen"):
        op.add_column(tabelle, sa.Column("anzahl", sa.Integer(), nullable=True))
        op.add_column(tabelle, sa.Column("betrag_euro", sa.Numeric(10, 2), nullable=True))
        op.add_column(tabelle, sa.Column("frist_wochen", sa.Integer(), nullable=True))


def downgrade() -> None:
    for tabelle in ("vorschlag_bedingungen", "bedingungen"):
        op.drop_column(tabelle, "frist_wochen")
        op.drop_column(tabelle, "betrag_euro")
        op.drop_column(tabelle, "anzahl")
