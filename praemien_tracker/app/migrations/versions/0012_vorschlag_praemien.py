"""vorschlag_praemien

Neue Tabelle für die einzelnen Teilprämien eines Vorschlags (Betrag, Geber,
Bedingung) - analog zu vorschlag_bedingungen. Damit wird sichtbar, dass ein
Angebot häufig mehrere Prämien mit unterschiedlichen Voraussetzungen mitbringt
(z.B. 50 EUR von Spartanien für die Kontoeröffnung plus 250 EUR von der Bank
für den Kontowechselservice).

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-07 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vorschlag_praemien",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deal_vorschlag_id", sa.Integer(), nullable=False),
        sa.Column("betrag", sa.Numeric(10, 2), nullable=False),
        sa.Column("geber", sa.String(length=100), nullable=True),
        sa.Column("bedingung", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["deal_vorschlag_id"], ["deal_vorschlaege.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_vorschlag_praemien_deal_vorschlag_id"),
        "vorschlag_praemien",
        ["deal_vorschlag_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vorschlag_praemien_deal_vorschlag_id"), table_name="vorschlag_praemien")
    op.drop_table("vorschlag_praemien")
