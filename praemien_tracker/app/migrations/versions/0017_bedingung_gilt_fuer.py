"""Bedingung: Zuordnung zur Teilprämie (gilt_fuer)

Neue, optionale Spalte gilt_fuer auf den Bedingungen (bedingungen und
vorschlag_bedingungen). Hält fest, für welche Teilprämie eine Bedingung
erfüllt werden muss (z.B. "250 € für den Kontowechselservice") - NULL, wenn es
eine Grundvoraussetzung fürs ganze Angebot ist oder es nur eine Prämie gibt.
Macht in der Anzeige sichtbar, welche Auflagen sich weglassen lassen, wenn ein
Teilbetrag bewusst nicht mitgenommen wird (siehe finder/extraktion.py).

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-10 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabelle in ("bedingungen", "vorschlag_bedingungen"):
        op.add_column(tabelle, sa.Column("gilt_fuer", sa.String(length=255), nullable=True))


def downgrade() -> None:
    for tabelle in ("vorschlag_bedingungen", "bedingungen"):
        op.drop_column(tabelle, "gilt_fuer")
