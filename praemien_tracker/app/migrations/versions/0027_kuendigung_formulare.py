"""kuendigung_formulare

Bankformulare für den Kündigungs-Assistenten (PDF samt Feldzuordnung je
Bank+Kontoart), dazu das ausgefüllte Formular an kuendigungsschreiben und die
von Hand übersteuerten Feldwerte am Deal.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-13 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kuendigung_formulare",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("kontoart", sa.String(length=50), nullable=False),
        sa.Column("quelle", sa.String(length=500), nullable=False),
        sa.Column("pdf", sa.LargeBinary(), nullable=False),
        sa.Column("felder", sa.Text(), nullable=False),
        sa.Column("zuordnung", sa.Text(), nullable=True),
        sa.Column("zusatzfelder", sa.Text(), nullable=True),
        sa.Column("zuordnung_ki", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("hinweis", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bank_name", "kontoart", name="uq_kuendigung_formular_bank_kontoart"),
    )
    op.create_index(op.f("ix_kuendigung_formulare_bank_name"), "kuendigung_formulare", ["bank_name"], unique=False)
    op.add_column("kuendigungsschreiben", sa.Column("datei", sa.LargeBinary(), nullable=True))
    op.add_column("deals", sa.Column("kuendigung_formular_werte", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "kuendigung_formular_werte")
    op.drop_column("kuendigungsschreiben", "datei")
    op.drop_index(op.f("ix_kuendigung_formulare_bank_name"), table_name="kuendigung_formulare")
    op.drop_table("kuendigung_formulare")
