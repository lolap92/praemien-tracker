"""finder_laeufe: Aufschlüsselung je Quelle

Acht zusätzliche Zähler pro Lauf, für die Tabelle im Vorschläge-Tab: je Quelle
(mydealz, spartanien) wie viele Funde neu, schon vorhanden, aktualisiert oder
Rauschen (kein Bank-Angebot, Duplikat, Fehler) waren. Jeder geladene Fund
landet in genau einer Kategorie, die Summe je Quelle ergibt <quelle>_geladen.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-07 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_SPALTEN = (
    "mydealz_neu",
    "mydealz_vorhanden",
    "mydealz_aktualisiert",
    "mydealz_rauschen",
    "spartanien_neu",
    "spartanien_vorhanden",
    "spartanien_aktualisiert",
    "spartanien_rauschen",
)


def upgrade() -> None:
    for name in _SPALTEN:
        op.add_column("finder_laeufe", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for name in reversed(_SPALTEN):
        op.drop_column("finder_laeufe", name)
