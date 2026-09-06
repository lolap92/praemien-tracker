"""deals.kontofuehrungsgebuehren

Monatliche Kontoführungsgebühr in Euro. Bewusst NULL-fähig ohne Default:
NULL heißt "noch nicht erfasst" und wird als Lücke angemahnt (siehe
derived.offene_felder), 0 heißt "kostenlos" und ist eine vollwertige Angabe.
Ein Default von 0 würde beides vermischen - bestehende Deals sähen aus, als
wären sie schon geprüft worden.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-06 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("kontofuehrungsgebuehren", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "kontofuehrungsgebuehren")
