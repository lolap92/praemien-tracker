"""kuendigung_recherchen, deals.kuendigung_hinweis_ki

Neue Tabelle als Cache für KI-recherchierte Kündigungswege (Bank+Kontoart),
für die es keinen fest hinterlegten Eintrag in kuendigung_hinweise.py gibt -
verhindert wiederholte API-Aufrufe für dieselbe Kombination. Dazu eine neue
Spalte auf deals, die festhält, ob der aktuelle Kündigungshinweis unverändert
aus dieser Recherche stammt (zur Kennzeichnung in der Oberfläche).

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-07 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kuendigung_recherchen",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("kontoart", sa.String(length=50), nullable=False),
        sa.Column("hinweis", sa.Text(), nullable=False),
        sa.Column("hinweis_url", sa.String(length=500), nullable=False),
        sa.Column("recherchiert_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bank_name", "kontoart", name="uq_kuendigung_recherche_bank_kontoart"),
    )
    op.create_index(
        op.f("ix_kuendigung_recherchen_bank_name"), "kuendigung_recherchen", ["bank_name"], unique=False
    )

    op.add_column("deals", sa.Column("kuendigung_hinweis_ki", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("deals", "kuendigung_hinweis_ki")
    op.drop_index(op.f("ix_kuendigung_recherchen_bank_name"), table_name="kuendigung_recherchen")
    op.drop_table("kuendigung_recherchen")
