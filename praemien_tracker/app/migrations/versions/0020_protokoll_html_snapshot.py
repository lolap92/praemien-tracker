"""protokoll.html_snapshot

Neue, optionale Spalte html_snapshot auf dem Änderungsprotokoll: eine
vollständig gerenderte Momentaufnahme der Dealseite (deal_snapshot.html) zum
Zeitpunkt des jeweiligen Eintrags. Der Protokoll-Link auf deals/{id} zeigt
bisher nur auf die *aktuelle* Deal-Seite - wird der Deal später gelöscht,
läuft der Link ins Leere, obwohl der Protokoll-Eintrag selbst (bewusst ohne
Fremdschlüssel, siehe models.ProtokollEintrag) genau dafür bestehen bleibt.
Mit dem gespeicherten HTML bleibt die Dealseite auch dann noch einsehbar.

Alte Einträge bleiben ohne Snapshot (NULL) - eine rückwirkende Rekonstruktion
wäre nur für noch existierende Deals möglich und für die inzwischen
gelöschten ohnehin nicht mehr, deshalb keine Backfill-Logik hier.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-29 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("protokoll", sa.Column("html_snapshot", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("protokoll", "html_snapshot")
