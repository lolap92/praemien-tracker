"""deal_vorschlaege: kontofuehrung, kontofuehrung_euro_monat, kontofuehrung_hinweis

Kontoführungsgebühren eines Fundes aus dem Angebotstext - Grundlage für die
zweite Einstufung auf der Vorschlagskarte (kostenlos / vermeidbar / fest).
NULL heißt "nicht erkannt"; bestehende Vorschläge bekommen die Werte erst bei
"Alle neu analysieren".

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-18 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_vorschlaege", sa.Column("kontofuehrung", sa.String(20), nullable=True))
    op.add_column("deal_vorschlaege", sa.Column("kontofuehrung_euro_monat", sa.Numeric(10, 2), nullable=True))
    op.add_column("deal_vorschlaege", sa.Column("kontofuehrung_hinweis", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("deal_vorschlaege", "kontofuehrung_hinweis")
    op.drop_column("deal_vorschlaege", "kontofuehrung_euro_monat")
    op.drop_column("deal_vorschlaege", "kontofuehrung")
