"""finder_laeufe: dritte Quelle dealdoktor

Fünf zusätzliche Zähler pro Lauf für die dritte Finder-Quelle (dealdoktor):
wie viele Funde geladen, davon neu, schon vorhanden, aktualisiert oder
Rauschen (kein Bank-Angebot, Duplikat, Fehler). Analog zu den bestehenden
mydealz_*/spartanien_*-Spalten (Migration 0011); die Summe der vier
Kategorien ergibt wieder dealdoktor_geladen.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-08 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_SPALTEN = (
    "dealdoktor_geladen",
    "dealdoktor_neu",
    "dealdoktor_vorhanden",
    "dealdoktor_aktualisiert",
    "dealdoktor_rauschen",
)


def upgrade() -> None:
    for name in _SPALTEN:
        op.add_column("finder_laeufe", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for name in reversed(_SPALTEN):
        op.drop_column("finder_laeufe", name)
