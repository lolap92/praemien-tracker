"""deal_vorschlaege.verwerfen_gruende

Neue Spalte für die Begründung(en) beim manuellen Verwerfen eines Vorschlags
(Mehrfachauswahl aus einem festen Enum: Duplikat, Bedingungen zu aufwendig,
Noch nicht wieder Neukunde) - komma-getrennte Codes, siehe
finder/matching.VERWERFEN_GRUENDE_LABELS.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-08 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_vorschlaege", sa.Column("verwerfen_gruende", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("deal_vorschlaege", "verwerfen_gruende")
