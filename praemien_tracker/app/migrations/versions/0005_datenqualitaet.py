"""quelle und gekuendigt_im_monat normalisieren

Reine Datenmigration, kein Schemawechsel.

- praemien.quelle: fachlich gibt es nur "spartanien" und "bank". Abweichende
  Schreibweisen ("Bank", " Spartanien ") wurden bisher unverändert gespeichert
  und beim nächsten Speichern über das Formular stillschweigend zu
  "spartanien" umgedeutet.
- deals.gekuendigt_im_monat: bisher "MM.YY", künftig ISO "YYYY-MM" - dasselbe
  Format, das auszahlung_erwartet schon verwendet.

Werte, die sich nicht sicher zuordnen lassen, bleiben unangetastet und werden
protokolliert. Eine Migration, die im Zweifel nichts tut, ist einer
vorzuziehen, die falsch zuordnet.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-30 00:00:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

QUELLEN = ("spartanien", "bank")


def _monat_nach_iso(wert):
    """'MM.YY' / 'M.YY' / 'MM.YYYY' -> 'YYYY-MM'. Bereits ISO bleibt ISO."""
    if not wert:
        return None
    text = str(wert).strip()
    if "-" in text:
        teile = text.split("-")
        if len(teile) == 2 and teile[0].isdigit() and teile[1].isdigit():
            jahr, monat = int(teile[0]), int(teile[1])
        else:
            return None
    elif "." in text:
        teile = text.split(".")
        if len(teile) == 2 and teile[0].isdigit() and teile[1].isdigit():
            monat, jahr = int(teile[0]), int(teile[1])
        else:
            return None
    else:
        return None
    if not 1 <= monat <= 12:
        return None
    if jahr < 100:
        jahr += 2000
    return f"{jahr:04d}-{monat:02d}"


def upgrade() -> None:
    verbindung = op.get_bind()

    geaendert = 0
    unklar = []
    for praemie_id, quelle in verbindung.execute(sa.text("SELECT id, quelle FROM praemien")):
        normalisiert = (quelle or "").strip().lower()
        if normalisiert == quelle:
            continue
        if normalisiert in QUELLEN:
            verbindung.execute(
                sa.text("UPDATE praemien SET quelle = :neu WHERE id = :id"),
                {"neu": normalisiert, "id": praemie_id},
            )
            geaendert += 1
        else:
            unklar.append((praemie_id, quelle))
    if geaendert:
        logger.info("Prämien-Quelle normalisiert: %d Zeilen.", geaendert)
    for praemie_id, quelle in unklar:
        logger.warning(
            "Prämie %s hat die unbekannte Quelle %r - unverändert gelassen, bitte von Hand prüfen.",
            praemie_id,
            quelle,
        )

    geaendert = 0
    unklar = []
    for deal_id, monat in verbindung.execute(
        sa.text("SELECT id, gekuendigt_im_monat FROM deals WHERE gekuendigt_im_monat IS NOT NULL")
    ):
        iso = _monat_nach_iso(monat)
        if iso is None:
            unklar.append((deal_id, monat))
            continue
        if iso != monat:
            verbindung.execute(
                sa.text("UPDATE deals SET gekuendigt_im_monat = :neu WHERE id = :id"),
                {"neu": iso, "id": deal_id},
            )
            geaendert += 1
    if geaendert:
        logger.info("Kündigungsmonat auf ISO umgestellt: %d Deals.", geaendert)
    for deal_id, monat in unklar:
        logger.warning(
            "Deal %s hat den unlesbaren Kündigungsmonat %r - unverändert gelassen, bitte von Hand prüfen.",
            deal_id,
            monat,
        )


def downgrade() -> None:
    """Zurück auf MM.YY. Die Quellen-Normalisierung wird nicht rückgängig
    gemacht - die ursprünglichen Schreibweisen sind nicht rekonstruierbar und
    waren ohnehin Schreibfehler."""
    verbindung = op.get_bind()
    for deal_id, monat in verbindung.execute(
        sa.text("SELECT id, gekuendigt_im_monat FROM deals WHERE gekuendigt_im_monat IS NOT NULL")
    ):
        text = str(monat).strip()
        teile = text.split("-")
        if len(teile) == 2 and all(teil.isdigit() for teil in teile):
            verbindung.execute(
                sa.text("UPDATE deals SET gekuendigt_im_monat = :neu WHERE id = :id"),
                {"neu": f"{int(teile[1]):02d}.{int(teile[0]) % 100:02d}", "id": deal_id},
            )
