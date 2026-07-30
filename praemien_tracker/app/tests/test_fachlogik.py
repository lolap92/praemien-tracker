"""Tests für die Fachlogik-Änderungen: Status, Zu prüfen, Überfälligkeit."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from praemien_tracker import derived
from praemien_tracker.models import Bank, Bedingung, Deal, Inhaber, Praemie

HEUTE = datetime.date(2026, 7, 30)


def mache_deal(
    *,
    gekuendigt: bool = False,
    kuendigung_bestaetigt: bool = False,
    storniert: bool = False,
    gekuendigt_im_monat: str | None = None,
    zugangsdaten_gespeichert: bool = True,
    praemien: list[dict] | None = None,
    bedingungen: list[dict] | None = None,
    erstellt_am: datetime.datetime | None = None,
) -> Deal:
    deal = Deal(
        kontoart="Depot",
        gekuendigt=gekuendigt,
        kuendigung_bestaetigt=kuendigung_bestaetigt,
        storniert=storniert,
        gekuendigt_im_monat=gekuendigt_im_monat,
        zugangsdaten_gespeichert=zugangsdaten_gespeichert,
        bank=Bank(name="Testbank"),
        inhaber=Inhaber(name="Max"),
    )
    # Ohne Datenbank ist erstellt_am None; die 72-Stunden-Schonfrist greift dann
    # nicht, was für die meisten Tests gewünscht ist.
    deal.erstellt_am = erstellt_am
    for i, angabe in enumerate(praemien or [], start=1):
        p = Praemie(
            quelle=angabe.get("quelle", "bank"),
            betrag=Decimal(angabe.get("betrag", "100")),
            erhalten=angabe.get("erhalten", False),
            auszahlung_erwartet=angabe.get("auszahlung_erwartet"),
        )
        p.id = i
        deal.praemien.append(p)
    for i, angabe in enumerate(bedingungen or [], start=1):
        b = Bedingung(
            beschreibung=angabe.get("beschreibung", f"b{i}"),
            erfuellt=angabe.get("erfuellt", False),
            erfuellt_am=angabe.get("erfuellt_am"),
        )
        b.id = i
        deal.bedingungen.append(b)
    return deal


# --- B2: bestätigte Kündigung ist terminal --------------------------------


def test_bestaetigte_kuendigung_schlaegt_offene_bedingung():
    """Vorher galt so ein Deal wegen der offenen Bedingung als 'Bedingungen' -
    er stand gleichzeitig in der ToDo-Liste und in den Sperrfristen."""
    deal = mache_deal(
        gekuendigt=True,
        kuendigung_bestaetigt=True,
        gekuendigt_im_monat="2026-01",
        bedingungen=[{"erfuellt": False}],
        praemien=[{"erhalten": True}],
    )
    assert derived.status(deal) == derived.STATUS_ABGESCHLOSSEN


def test_offene_bedingung_wird_nicht_still_abgehakt():
    deal = mache_deal(gekuendigt=True, kuendigung_bestaetigt=True, bedingungen=[{"erfuellt": False}])
    assert deal.bedingungen[0].erfuellt is False


def test_abgeschlossener_deal_erzeugt_kein_bedingungs_todo():
    deal = mache_deal(
        gekuendigt=True,
        kuendigung_bestaetigt=True,
        gekuendigt_im_monat="2026-01",
        bedingungen=[{"erfuellt": False}],
        praemien=[{"erhalten": True}],
    )
    kategorien = {t.kategorie for t in derived.deal_todos(deal, HEUTE)}
    assert "Bedingungen" not in kategorien
    assert "Zu prüfen" in kategorien


# --- B6: storniert ist von gekündigt getrennt ----------------------------


def test_stornierter_deal_ist_abgeschlossen():
    assert derived.status(mache_deal(storniert=True)) == derived.STATUS_ABGESCHLOSSEN


def test_stornierter_deal_erzeugt_keine_pruefpunkte():
    """Ein stornierter Deal ist erledigt - da gibt es nichts nachzusehen."""
    deal = mache_deal(storniert=True, gekuendigt=False)
    assert derived.pruefpunkte(deal, HEUTE) == []


# --- B7: Zugangsdaten nur solange das Konto lebt ------------------------


def test_zugangsdaten_todo_entfaellt_ab_gekuendigt():
    laufend = mache_deal(zugangsdaten_gespeichert=False)
    gekuendigt = mache_deal(zugangsdaten_gespeichert=False, gekuendigt=True, gekuendigt_im_monat="2026-01")
    assert any(t.kategorie == "Zugangsdaten" for t in derived.deal_todos(laufend, HEUTE))
    assert not any(t.kategorie == "Zugangsdaten" for t in derived.deal_todos(gekuendigt, HEUTE))


# --- B3/B2: Zu prüfen ---------------------------------------------------


def test_offene_bedingungen_nach_kuendigung():
    deal = mache_deal(gekuendigt=True, gekuendigt_im_monat="2026-01", bedingungen=[{"erfuellt": False}])
    regeln = {p.regel for p in derived.pruefpunkte(deal, HEUTE)}
    assert derived.PRUEF_BEDINGUNGEN_OFFEN in regeln


def test_offene_praemien_nach_kuendigung():
    deal = mache_deal(gekuendigt=True, gekuendigt_im_monat="2026-01", praemien=[{"erhalten": False}])
    regeln = {p.regel for p in derived.pruefpunkte(deal, HEUTE)}
    assert derived.PRUEF_PRAEMIEN_OFFEN in regeln


def test_fehlender_kuendigungsmonat():
    deal = mache_deal(gekuendigt=True, gekuendigt_im_monat=None, praemien=[{"erhalten": True}])
    regeln = {p.regel for p in derived.pruefpunkte(deal, HEUTE)}
    assert derived.PRUEF_KUENDIGUNGSMONAT_FEHLT in regeln


def test_unlesbarer_kuendigungsmonat_zaehlt_als_fehlend():
    deal = mache_deal(gekuendigt=True, gekuendigt_im_monat="quatsch", praemien=[{"erhalten": True}])
    regeln = {p.regel for p in derived.pruefpunkte(deal, HEUTE)}
    assert derived.PRUEF_KUENDIGUNGSMONAT_FEHLT in regeln


def test_keine_praemie_erfasst():
    deal = mache_deal()
    regeln = {p.regel for p in derived.pruefpunkte(deal, HEUTE)}
    assert derived.PRUEF_KEINE_PRAEMIE in regeln


def test_frisch_angelegter_deal_wird_72_stunden_geschont():
    """Prämien trägt man erst nach dem Anlegen ein - ohne Schonfrist landet
    jeder neue Deal sofort in der Liste."""
    jetzt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    frisch = mache_deal(erstellt_am=jetzt - datetime.timedelta(hours=1))
    alt = mache_deal(erstellt_am=jetzt - datetime.timedelta(hours=80))
    assert derived.PRUEF_KEINE_PRAEMIE not in {p.regel for p in derived.pruefpunkte(frisch, HEUTE)}
    assert derived.PRUEF_KEINE_PRAEMIE in {p.regel for p in derived.pruefpunkte(alt, HEUTE)}


def test_abgehakte_auffaelligkeit_verschwindet():
    deal = mache_deal(gekuendigt=True, gekuendigt_im_monat="2026-01", praemien=[{"erhalten": False}])
    punkt = next(p for p in derived.pruefpunkte(deal, HEUTE) if p.regel == derived.PRUEF_PRAEMIEN_OFFEN)
    derived.pruefung_abhaken(deal, punkt.regel, punkt.signatur)
    assert derived.PRUEF_PRAEMIEN_OFFEN not in {p.regel for p in derived.pruefpunkte(deal, HEUTE)}


def test_abgehakte_auffaelligkeit_kommt_bei_neuen_fakten_zurueck():
    """Genau dafür wird die Signatur gespeichert und nicht bloß ein Häkchen."""
    deal = mache_deal(gekuendigt=True, gekuendigt_im_monat="2026-01", praemien=[{"erhalten": False}])
    punkt = next(p for p in derived.pruefpunkte(deal, HEUTE) if p.regel == derived.PRUEF_PRAEMIEN_OFFEN)
    derived.pruefung_abhaken(deal, punkt.regel, punkt.signatur)

    weitere = Praemie(quelle="bank", betrag=Decimal("50"), erhalten=False)
    weitere.id = 99
    deal.praemien.append(weitere)

    assert derived.PRUEF_PRAEMIEN_OFFEN in {p.regel for p in derived.pruefpunkte(deal, HEUTE)}


def test_kaputter_pruefmarker_wird_ignoriert():
    deal = mache_deal()
    deal.pruefung_geprueft = "kein json"
    assert derived.PRUEF_KEINE_PRAEMIE in {p.regel for p in derived.pruefpunkte(deal, HEUTE)}


# --- B4: überfällige Prämien -------------------------------------------


def test_monat_plus_begrenzt_den_tag():
    assert derived.monat_plus(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)
    assert derived.monat_plus(datetime.date(2026, 12, 15), 1) == datetime.date(2027, 1, 15)


@pytest.mark.parametrize(
    "erwartet, heute, ueberfaellig",
    [
        # erwartet 03/2026: Monatsende plus ein Monat Karenz -> ab 01.05.2026
        ("2026-03", datetime.date(2026, 4, 30), False),
        ("2026-03", datetime.date(2026, 5, 1), True),
        ("2026-12", datetime.date(2026, 7, 30), False),
    ],
)
def test_ueberfaellig_mit_auszahlungsmonat(erwartet, heute, ueberfaellig):
    deal = mache_deal(praemien=[{"erhalten": False, "auszahlung_erwartet": erwartet}])
    assert derived.praemie_ueberfaellig(deal, deal.praemien[0], heute) is ueberfaellig


def test_erhaltene_praemie_ist_nie_ueberfaellig():
    deal = mache_deal(praemien=[{"erhalten": True, "auszahlung_erwartet": "2020-01"}])
    assert derived.praemie_ueberfaellig(deal, deal.praemien[0], HEUTE) is False


def test_ohne_datum_zaehlt_die_zuletzt_erfuellte_bedingung():
    deal = mache_deal(
        praemien=[{"erhalten": False}],
        bedingungen=[
            {"erfuellt": True, "erfuellt_am": datetime.date(2026, 1, 10)},
            {"erfuellt": True, "erfuellt_am": datetime.date(2026, 5, 20)},
        ],
    )
    # zuletzt erfüllt am 20.05., plus zwei Monate -> ab 20.07. überfällig
    assert derived.praemie_ueberfaellig(deal, deal.praemien[0], datetime.date(2026, 7, 19)) is False
    assert derived.praemie_ueberfaellig(deal, deal.praemien[0], datetime.date(2026, 7, 20)) is True


def test_ohne_datum_und_ohne_bedingungen_keine_ueberfaelligkeit():
    """Es gibt keinen Bezugspunkt - die Vollständigkeit mahnt das fehlende
    Auszahlungsdatum ohnehin an."""
    deal = mache_deal(praemien=[{"erhalten": False}])
    assert derived.praemie_faellig_ab(deal, deal.praemien[0]) is None


def test_offene_bedingung_verhindert_die_karenzrechnung():
    deal = mache_deal(
        praemien=[{"erhalten": False}],
        bedingungen=[
            {"erfuellt": True, "erfuellt_am": datetime.date(2025, 1, 1)},
            {"erfuellt": False},
        ],
    )
    assert derived.praemie_faellig_ab(deal, deal.praemien[0]) is None


def test_ueberfaellige_praemie_wird_im_todo_markiert():
    deal = mache_deal(praemien=[{"erhalten": False, "auszahlung_erwartet": "2025-01"}])
    todo = next(t for t in derived.deal_todos(deal, HEUTE) if t.kategorie == "Auf Prämie warten")
    assert todo.ueberfaellig is True
    assert "überfällig" in todo.text
