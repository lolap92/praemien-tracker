"""deals.art

Unterscheidet echte Prämien-Deals ("deal") von Konten, die anderweitig
eröffnet wurden und nur bis zur Kündigung mitverfolgt werden ("konto", siehe
models.ART_KONTO). Server-Default "deal", damit alle bestehenden Zeilen
unverändert Deals bleiben.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-13 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("art", sa.String(10), nullable=False, server_default="deal"))


def downgrade() -> None:
    op.drop_column("deals", "art")
