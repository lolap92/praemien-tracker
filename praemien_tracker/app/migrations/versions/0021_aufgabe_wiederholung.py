"""aufgaben.wiederholung, aufgaben.vorgaenger_id

Monatlich wiederkehrende manuelle Aufgaben. `wiederholung` ist "einmalig"
(wie bisher, Default für alle bestehenden Zeilen) oder "monatlich".
`vorgaenger_id` verweist auf die Aufgabe, aus deren Abhaken diese hier
hervorgegangen ist - gebraucht wird der Verweis nur für den Rückweg: wird
eine erledigte Aufgabe wieder geöffnet, verschwindet ihr eben erzeugter
Nachfolger wieder, statt als Dublette offen stehen zu bleiben.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-05 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default, nicht nur ein Python-Default: bestehende Zeilen brauchen
    # beim Hinzufügen der NOT-NULL-Spalte einen Wert.
    op.add_column(
        "aufgaben",
        sa.Column("wiederholung", sa.String(length=20), nullable=False, server_default="einmalig"),
    )
    op.add_column("aufgaben", sa.Column("vorgaenger_id", sa.Integer(), nullable=True))
    op.create_index("ix_aufgaben_vorgaenger_id", "aufgaben", ["vorgaenger_id"])
    # Kein benannter Fremdschlüssel: SQLite kann ihn nachträglich nur über ein
    # Tabellen-Neuschreiben (batch_alter_table) anlegen, und der Verweis wird
    # ausschließlich innerhalb der Anwendung aufgelöst (siehe models.Aufgabe).


def downgrade() -> None:
    op.drop_index("ix_aufgaben_vorgaenger_id", table_name="aufgaben")
    op.drop_column("aufgaben", "vorgaenger_id")
    op.drop_column("aufgaben", "wiederholung")
