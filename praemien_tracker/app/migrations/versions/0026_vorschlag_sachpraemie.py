"""deal_vorschlaege: praemie_art, praemie_bis, praemie_beschreibung

Prämien ohne festen Geldbetrag (Gratisaktie "bis 100 €", ETF-Anteil,
Gutschein). Bisher kannte die Extraktion nur einen Euro-Betrag - eine
Gratisaktie mit schwankendem Wert landete dadurch als 0 € in der
automatischen Ablehnung (Mindestprämie).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-13 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_vorschlaege", sa.Column("praemie_art", sa.String(20), nullable=False, server_default="geld"))
    op.add_column("deal_vorschlaege", sa.Column("praemie_bis", sa.Numeric(10, 2), nullable=True))
    op.add_column("deal_vorschlaege", sa.Column("praemie_beschreibung", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("deal_vorschlaege", "praemie_beschreibung")
    op.drop_column("deal_vorschlaege", "praemie_bis")
    op.drop_column("deal_vorschlaege", "praemie_art")
