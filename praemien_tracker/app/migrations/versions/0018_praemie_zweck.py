"""praemien.zweck

Neue, optionale Spalte zweck auf den Prämien: wofür es diese (Teil-)Prämie gibt
(z.B. "für den Kontowechselservice"). Rein informativ; macht bei aufgeteilten
Prämien am übernommenen Deal nachvollziehbar, welcher Teilbetrag woran hängt.
NULL, wenn das Angebot keine Aufteilung mit eigenem Zweck nennt.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-10 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("praemien", sa.Column("zweck", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("praemien", "zweck")
