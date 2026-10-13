"""Kündigungs-Assistent

Absenderdaten am Inhaber, Empfänger an der Bank, Zusatzangaben am Deal und
die neue Tabelle kuendigung_anforderungen. Alle neuen Spalten sind NULL-fähig
ohne Default - "noch nicht erfasst" ist genau der Zustand, nach dem der
Assistent fragt.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-13 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_INHABER_SPALTEN = (
    ("voller_name", sa.String(length=200)),
    ("strasse", sa.String(length=200)),
    ("plz", sa.String(length=10)),
    ("ort", sa.String(length=100)),
    ("geburtsdatum", sa.Date()),
    ("email", sa.String(length=200)),
    ("iban", sa.String(length=34)),
)


def upgrade() -> None:
    for name, typ in _INHABER_SPALTEN:
        op.add_column("inhaber", sa.Column(name, typ, nullable=True))
    op.add_column("banks", sa.Column("anschrift", sa.Text(), nullable=True))
    op.add_column("banks", sa.Column("kuendigung_email", sa.String(length=200), nullable=True))
    op.add_column("deals", sa.Column("kuendigung_angaben", sa.Text(), nullable=True))

    op.create_table(
        "kuendigung_anforderungen",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("kontoart", sa.String(length=50), nullable=False),
        sa.Column("kanal", sa.String(length=20), nullable=False),
        sa.Column("empfaenger_anschrift", sa.Text(), nullable=True),
        sa.Column("empfaenger_email", sa.String(length=200), nullable=True),
        sa.Column("formular_url", sa.String(length=500), nullable=True),
        sa.Column("besonderheiten", sa.Text(), nullable=True),
        sa.Column("zusatzfelder", sa.Text(), nullable=True),
        sa.Column("betreff_vorlage", sa.String(length=300), nullable=False),
        sa.Column("text_vorlage", sa.Text(), nullable=False),
        sa.Column("quelle_url", sa.String(length=500), nullable=True),
        sa.Column("recherchiert_am", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bank_name", "kontoart", name="uq_kuendigung_anforderung_bank_kontoart"),
    )
    op.create_index(
        op.f("ix_kuendigung_anforderungen_bank_name"), "kuendigung_anforderungen", ["bank_name"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_kuendigung_anforderungen_bank_name"), table_name="kuendigung_anforderungen")
    op.drop_table("kuendigung_anforderungen")
    op.drop_column("deals", "kuendigung_angaben")
    op.drop_column("banks", "kuendigung_email")
    op.drop_column("banks", "anschrift")
    for name, _ in reversed(_INHABER_SPALTEN):
        op.drop_column("inhaber", name)
