"""deal_vorschlaege: identifikation, identifikation_quelle; ident_recherchen

Ob sich ein Konto per eID (Online-Ausweisfunktion) eröffnen lässt oder nur
per VideoIdent/PostIdent/Filiale. Steht selten im Angebotstext, deshalb
zusätzlich eine KI-Websuche je Bank, gecacht in ident_recherchen.

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
    op.add_column("deal_vorschlaege", sa.Column("identifikation", sa.String(50), nullable=True))
    op.add_column("deal_vorschlaege", sa.Column("identifikation_quelle", sa.String(20), nullable=True))
    op.create_table(
        "ident_recherchen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bank_schluessel", sa.String(100), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("verfahren", sa.String(50), nullable=True),
        sa.Column("quelle_url", sa.String(500), nullable=True),
        sa.Column("fehlgeschlagen", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("recherchiert_am", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ident_recherchen_bank_schluessel", "ident_recherchen", ["bank_schluessel"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ident_recherchen_bank_schluessel", table_name="ident_recherchen")
    op.drop_table("ident_recherchen")
    op.drop_column("deal_vorschlaege", "identifikation_quelle")
    op.drop_column("deal_vorschlaege", "identifikation")
