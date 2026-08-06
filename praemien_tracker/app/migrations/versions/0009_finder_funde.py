"""finder_funde, finder_laeufe.aus_cache

Neue Tabelle als Gedächtnis des KI-Deal-Finders je Rohquelle-URL: verhindert,
dass ein unverändertes oder bereits als irrelevant erkanntes Angebot bei
jedem Lauf erneut gegen die Anthropic-API geschickt wird. Dazu eine neue
Spalte auf finder_laeufe, die festhält, wie viele Funde je Lauf dank dieses
Gedächtnisses ganz ohne API-Aufruf erledigt wurden.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-06 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finder_funde",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quelle", sa.String(length=20), nullable=False),
        sa.Column("quelle_url", sa.String(length=500), nullable=False),
        sa.Column("rohtext_hash", sa.String(length=64), nullable=False),
        sa.Column("ist_relevant", sa.Boolean(), nullable=False),
        sa.Column("extraktion_json", sa.Text(), nullable=True),
        sa.Column("erstmals_gesehen_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("zuletzt_gesehen_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_finder_funde_quelle_url"), "finder_funde", ["quelle_url"], unique=True)

    op.add_column("finder_laeufe", sa.Column("aus_cache", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("finder_laeufe", "aus_cache")
    op.drop_index(op.f("ix_finder_funde_quelle_url"), table_name="finder_funde")
    op.drop_table("finder_funde")
