"""deal_vorschlaege, vorschlag_bedingungen

Neue Tabellen für die Erweiterung "KI-Deal-Finder": Funde aus mydealz/spartanien
landen als DealVorschlag, bis der Nutzer sie übernimmt oder verwirft - getrennt
von DEAL, damit im Kern nur Fakten stehen.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-06 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deal_vorschlaege",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inhaber_id", sa.Integer(), nullable=False),
        sa.Column("quelle", sa.String(length=20), nullable=False),
        sa.Column("quelle_url", sa.String(length=500), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("kontoart", sa.String(length=50), nullable=False),
        sa.Column("praemie_betrag", sa.Numeric(10, 2), nullable=False),
        sa.Column("sperrfrist_monate", sa.Integer(), nullable=True),
        sa.Column("ablehnungsgruende", sa.Text(), nullable=True),
        sa.Column("roh_json", sa.Text(), nullable=False),
        sa.Column("inhalt_hash", sa.String(length=64), nullable=False),
        sa.Column("gefunden_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["inhaber_id"], ["inhaber.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deal_vorschlaege_inhaber_id"), "deal_vorschlaege", ["inhaber_id"], unique=False)
    op.create_index(op.f("ix_deal_vorschlaege_quelle_url"), "deal_vorschlaege", ["quelle_url"], unique=False)
    op.create_index(op.f("ix_deal_vorschlaege_inhalt_hash"), "deal_vorschlaege", ["inhalt_hash"], unique=False)
    op.create_index(op.f("ix_deal_vorschlaege_status"), "deal_vorschlaege", ["status"], unique=False)

    op.create_table(
        "vorschlag_bedingungen",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deal_vorschlag_id", sa.Integer(), nullable=False),
        sa.Column("beschreibung", sa.String(length=255), nullable=False),
        sa.Column("einschaetzung", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["deal_vorschlag_id"], ["deal_vorschlaege.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_vorschlag_bedingungen_deal_vorschlag_id"),
        "vorschlag_bedingungen",
        ["deal_vorschlag_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vorschlag_bedingungen_deal_vorschlag_id"), table_name="vorschlag_bedingungen")
    op.drop_table("vorschlag_bedingungen")
    op.drop_index(op.f("ix_deal_vorschlaege_status"), table_name="deal_vorschlaege")
    op.drop_index(op.f("ix_deal_vorschlaege_inhalt_hash"), table_name="deal_vorschlaege")
    op.drop_index(op.f("ix_deal_vorschlaege_quelle_url"), table_name="deal_vorschlaege")
    op.drop_index(op.f("ix_deal_vorschlaege_inhaber_id"), table_name="deal_vorschlaege")
    op.drop_table("deal_vorschlaege")
