"""kuendigungsschreiben

Gespeicherte Schreiben aus dem Kündigungs-Assistenten (Brief oder E-Mail),
als Momentaufnahme samt Versanddatum.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-13 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kuendigungsschreiben",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("kanal", sa.String(length=10), nullable=False),
        sa.Column("empfaenger", sa.Text(), nullable=True),
        sa.Column("absender", sa.Text(), nullable=False),
        sa.Column("ort", sa.String(length=100), nullable=True),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("betreff", sa.String(length=300), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("versendet_am", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kuendigungsschreiben_deal_id"), "kuendigungsschreiben", ["deal_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kuendigungsschreiben_deal_id"), table_name="kuendigungsschreiben")
    op.drop_table("kuendigungsschreiben")
