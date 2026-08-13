"""deal_vorschlaege.deal_id

Neue, optionale Spalte deal_id auf den Vorschlägen: verweist auf den Deal,
der beim Übernehmen daraus entstanden ist (siehe routers/vorschlaege.py:
uebernehmen_bestaetigen). Macht die Übernahme nachvollziehbar - vorher gab es
keine gespeicherte Verbindung zwischen einer übernommenen Vorschlags-Zeile
und "ihrem" Deal.

Für bereits übernommene Alt-Datensätze (status=uebernommen, deal_id noch
leer) versucht diese Migration einmalig eine Best-Effort-Zuordnung anhand
Inhaber + normalisierter Bank + Kontoart, bei Mehrdeutigkeit zusätzlich über
den zeitlich nächstgelegenen noch unverknüpften Deal. Nicht eindeutig
zuordenbare Zeilen bleiben bewusst unverknüpft und werden protokolliert -
eine Migration, die im Zweifel nichts tut, ist einer vorzuziehen, die falsch
zuordnet (vgl. 0005_datenqualitaet).

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-13 00:00:00.000000

"""
import datetime
import logging
import re

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# Eindeutigkeits-Schwelle: liegt der zweitnächste Kandidat weniger als diesen
# Abstand vom besten entfernt, gilt die Zuordnung als nicht mehr eindeutig
# genug und bleibt unverknüpft.
_MEHRDEUTIGKEITS_SCHWELLE = datetime.timedelta(minutes=5)


def _bank_name_normalisieren(name: str) -> str:
    """Dieselbe Normalisierung wie derived.bank_name_normalisieren - hier
    dupliziert, damit die Migration unabhängig vom aktuellen Anwendungscode
    bleibt (der sich künftig ändern könnte, ohne alte Migrationen zu brechen)."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _parse_datetime(wert) -> datetime.datetime | None:
    if wert is None:
        return None
    if isinstance(wert, datetime.datetime):
        return wert
    try:
        return datetime.datetime.fromisoformat(str(wert))
    except ValueError:
        return None


def upgrade() -> None:
    # SQLite kann eine Fremdschlüssel-Constraint nicht per einfachem ALTER
    # TABLE ADD COLUMN ergänzen - batch_alter_table baut die Tabelle dafür
    # per Copy-and-Move-Strategie neu auf (Alembic-Standardvorgehen für
    # SQLite, bislang in diesem Projekt nicht gebraucht, da alle bisherigen
    # Fremdschlüssel schon im ursprünglichen CREATE TABLE steckten).
    with op.batch_alter_table("deal_vorschlaege") as batch_op:
        batch_op.add_column(sa.Column("deal_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_deal_vorschlaege_deal_id", ["deal_id"])
        batch_op.create_foreign_key("fk_deal_vorschlaege_deal_id_deals", "deals", ["deal_id"], ["id"])

    verbindung = op.get_bind()

    banken = {
        bank_id: _bank_name_normalisieren(name)
        for bank_id, name in verbindung.execute(sa.text("SELECT id, name FROM banks"))
    }
    deals = verbindung.execute(sa.text("SELECT id, bank_id, inhaber_id, kontoart, erstellt_am FROM deals")).fetchall()
    vorschlaege = verbindung.execute(
        sa.text(
            "SELECT id, inhaber_id, bank_name, kontoart, gefunden_am "
            "FROM deal_vorschlaege WHERE status = 'uebernommen' AND deal_id IS NULL"
        )
    ).fetchall()

    vergebene_deal_ids: set[int] = set()
    zugeordnet = 0
    unklar = []
    for vorschlag_id, inhaber_id, bank_name, kontoart, gefunden_am in vorschlaege:
        ziel_bank = _bank_name_normalisieren(bank_name)
        ziel_kontoart = (kontoart or "").strip().lower()
        kandidaten = [
            d
            for d in deals
            if d.id not in vergebene_deal_ids
            and d.inhaber_id == inhaber_id
            and (d.kontoart or "").strip().lower() == ziel_kontoart
            and banken.get(d.bank_id) == ziel_bank
        ]

        treffer = None
        if len(kandidaten) == 1:
            treffer = kandidaten[0]
        elif len(kandidaten) > 1:
            gefunden_dt = _parse_datetime(gefunden_am)
            if gefunden_dt is not None:
                bewertet = sorted(
                    (
                        (d, abs((_parse_datetime(d.erstellt_am) or gefunden_dt) - gefunden_dt))
                        for d in kandidaten
                    ),
                    key=lambda paar: paar[1],
                )
                bester, abstand = bewertet[0]
                if len(bewertet) == 1 or bewertet[1][1] - abstand >= _MEHRDEUTIGKEITS_SCHWELLE:
                    treffer = bester

        if treffer is None:
            unklar.append((vorschlag_id, bank_name, kontoart, len(kandidaten)))
            continue

        verbindung.execute(
            sa.text("UPDATE deal_vorschlaege SET deal_id = :deal_id WHERE id = :id"),
            {"deal_id": treffer.id, "id": vorschlag_id},
        )
        vergebene_deal_ids.add(treffer.id)
        zugeordnet += 1

    if zugeordnet:
        logger.info("Übernommene Vorschläge rückwirkend mit ihrem Deal verknüpft: %d.", zugeordnet)
    for vorschlag_id, bank_name, kontoart, anzahl_kandidaten in unklar:
        logger.warning(
            "Vorschlag %s (%s, %s) ließ sich nicht eindeutig einem Deal zuordnen (%d Kandidaten) - "
            "bleibt ohne Verknüpfung.",
            vorschlag_id,
            bank_name,
            kontoart,
            anzahl_kandidaten,
        )


def downgrade() -> None:
    with op.batch_alter_table("deal_vorschlaege") as batch_op:
        batch_op.drop_constraint("fk_deal_vorschlaege_deal_id_deals", type_="foreignkey")
        batch_op.drop_index("ix_deal_vorschlaege_deal_id")
        batch_op.drop_column("deal_id")
