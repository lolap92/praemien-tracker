"""finder_laeufe

Neue Tabelle für das Lauf-Protokoll des KI-Deal-Finders: pro Lauf, ob er
erfolgreich war, wie viele Funde je Quelle geladen wurden, wie viele neu
gefunden wurden und ob dabei Fehler auftraten - Grundlage für die
Statusanzeige im Vorschläge-Tab.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finder_laeufe",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gestartet_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("beendet_am", sa.DateTime(), nullable=True),
        sa.Column("erfolgreich", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mydealz_geladen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spartanien_geladen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("neu_gefunden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uebersprungen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fehler", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("finder_laeufe")
