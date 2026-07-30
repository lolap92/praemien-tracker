"""Tests für die abgeleiteten Sichten (derived.py).

Der Kern der App ist bewusst frei von gespeicherten Zuständen: Status,
Sperrfristen, ToDos und Vollständigkeit werden aus den Fakten berechnet.
Genau das lässt sich ohne Datenbank prüfen - die Modelle werden hier nur
als Träger der Fakten instanziiert, nichts wird committet.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from praemien_tracker import derived
from praemien_tracker.models import Aufgabe, Bank, Bedingung, Deal, Inhaber, Praemie

HEUTE = datetime.date(2026, 7, 30)


def mache_deal(
    *,
    kuendbar_ab: datetime.date | None = None,
    gekuendigt: bool = False,
    gekuendigt_im_monat: str | None = None,
    kuendigung_bestaetigt: bool = False,
    zugangsdaten_gespeichert: bool = True,
    praemien: list[tuple[str, str, bool]] | None = None,
    bedingungen: list[tuple[str, bool]] | None = None,
    kontonummer: str | None = "DE123",
    freibetrag: Decimal | None = Decimal("100"),
) -> Deal:
    deal = Deal(
        kontoart="Depot",
        kuendbar_ab=kuendbar_ab,
        gekuendigt=gekuendigt,
        gekuendigt_im_monat=gekuendigt_im_monat,
        kuendigung_bestaetigt=kuendigung_bestaetigt,
        zugangsdaten_gespeichert=zugangsdaten_gespeichert,
        kontonummer=kontonummer,
        freibetrag=freibetrag,
        bank=Bank(name="Testbank"),
        inhaber=Inhaber(name="Max"),
    )
    for i, (quelle, betrag, erhalten) in enumerate(praemien or [], start=1):
        p = Praemie(quelle=quelle, betrag=Decimal(betrag), erhalten=erhalten, auszahlung_erwartet="2026-08")
        p.id = i
        deal.praemien.append(p)
    for i, (beschreibung, erfuellt) in enumerate(bedingungen or [], start=1):
        b = Bedingung(beschreibung=beschreibung, erfuellt=erfuellt)
        b.id = i
        deal.bedingungen.append(b)
    return deal


# --- Status ---------------------------------------------------------------


def test_offene_bedingung_haelt_den_deal_in_stufe_eins():
    deal = mache_deal(bedingungen=[("3 Trades", False)], praemien=[("bank", "100", True)])
    assert derived.status(deal) == derived.STATUS_BEDINGUNGEN


def test_ohne_bedingungen_gilt_als_erfuellt():
    deal = mache_deal(praemien=[("bank", "100", False)])
    assert derived.status(deal) == derived.STATUS_PRAEMIE_WARTEN


def test_deal_ohne_praemien_bleibt_in_praemie_warten():
    """Bewusst so: ohne hinterlegte Prämie gibt es nichts zu erhalten."""
    assert derived.status(mache_deal()) == derived.STATUS_PRAEMIE_WARTEN


def test_leeres_kuendbar_ab_heisst_sofort_kuendbar():
    """Fachliche Regel: kein Datum bedeutet keine Sperrfrist."""
    deal = mache_deal(praemien=[("bank", "100", True)])
    assert derived.ist_kuendbar(deal, HEUTE) is True
    assert derived.status(deal) == derived.STATUS_KUENDIGEN


def test_kuendbar_ab_in_der_zukunft_wartet():
    deal = mache_deal(kuendbar_ab=datetime.date(2027, 1, 1), praemien=[("bank", "100", True)])
    assert derived.status(deal) == derived.STATUS_WARTET_AUF_KUENDIGUNG


def test_gekuendigt_und_bestaetigt_ist_abgeschlossen():
    deal = mache_deal(praemien=[("bank", "100", True)], gekuendigt=True, kuendigung_bestaetigt=True)
    assert derived.status(deal) == derived.STATUS_ABGESCHLOSSEN


def test_jeder_status_hat_ein_label_und_einen_index():
    for s in derived.STATUS_ORDER:
        assert s in derived.STATUS_LABELS
        assert s in derived.STATUS_INDEX


# --- Sperrfristen ---------------------------------------------------------


@pytest.mark.parametrize(
    "wert, erwartet",
    [
        ("07.26", datetime.date(2026, 7, 1)),
        ("5.26", datetime.date(2026, 5, 1)),
        ("03.2025", datetime.date(2025, 3, 1)),
        ("2026-05", None),
        ("13.26", None),
        ("quatsch", None),
        ("", None),
        (None, None),
    ],
)
def test_kuendigungsmonat_parsen(wert, erwartet):
    assert derived.parse_gekuendigt_monat(wert) == erwartet


def test_monate_seit_kuendigung_wird_nicht_negativ():
    zukunft = datetime.date(2027, 1, 1)
    assert derived.monate_seit_kuendigung(zukunft, HEUTE) == 0


def test_monate_seit_kuendigung_zaehlt_ueber_den_jahreswechsel():
    assert derived.monate_seit_kuendigung(datetime.date(2025, 3, 1), HEUTE) == 16


@pytest.mark.parametrize(
    "monate, stufe",
    [(0, derived.SPERRFRIST_ROT), (5, derived.SPERRFRIST_ROT), (6, derived.SPERRFRIST_ORANGE),
     (12, derived.SPERRFRIST_ORANGE), (13, derived.SPERRFRIST_GRUEN)],
)
def test_sperrfrist_stufen_an_den_grenzen(monate, stufe):
    assert derived.sperrfrist_stufe(monate) == stufe


# --- Kennzahlen ----------------------------------------------------------


def test_kennzahlen_summieren_erhalten_und_offen():
    deal = mache_deal(praemien=[("bank", "100.50", True), ("spartanien", "49.50", False)])
    kz = derived.kennzahlen(deal.praemien)
    assert kz.gesamt == Decimal("150.00")
    assert kz.erhalten == Decimal("100.50")
    assert kz.offen == Decimal("49.50")


def test_kennzahlen_ohne_praemien_sind_null():
    kz = derived.kennzahlen([])
    assert (kz.gesamt, kz.erhalten, kz.offen) == (Decimal("0"), Decimal("0"), Decimal("0"))


# --- ToDos ---------------------------------------------------------------


def test_mehrere_offene_bedingungen_werden_zu_einem_todo_zusammengefasst():
    deal = mache_deal(bedingungen=[("a", False), ("b", False)])
    todos = [t for t in derived.deal_todos(deal, HEUTE) if t.kategorie == "Bedingungen"]
    assert len(todos) == 1
    assert len(todos[0].elemente) == 2


def test_ueberfaellige_bedingung_wird_markiert():
    deal = mache_deal(bedingungen=[("a", False)])
    deal.bedingungen[0].faellig_bis = datetime.date(2026, 1, 1)
    todo = next(t for t in derived.deal_todos(deal, HEUTE) if t.kategorie == "Bedingungen")
    assert todo.ueberfaellig is True


def test_zugangsdaten_todo_nur_wenn_nicht_gesichert():
    ohne = mache_deal(zugangsdaten_gespeichert=False)
    mit = mache_deal(zugangsdaten_gespeichert=True)
    assert any(t.kategorie == "Zugangsdaten" for t in derived.deal_todos(ohne, HEUTE))
    assert not any(t.kategorie == "Zugangsdaten" for t in derived.deal_todos(mit, HEUTE))


def test_erledigte_aufgaben_erscheinen_nicht_in_der_liste():
    aufgaben = [Aufgabe(beschreibung="offen", erledigt=False), Aufgabe(beschreibung="fertig", erledigt=True)]
    todos = derived.alle_todos([], aufgaben, HEUTE)
    assert [t.text for t in todos] == ["offen"]


def test_quelle_label_uebersetzt_bekannte_werte():
    assert derived.quelle_label("spartanien") == "Spartanien"
    assert derived.quelle_label("bank") == "Bank"
    assert derived.quelle_label("unbekannt") == "unbekannt"


# --- Vollständigkeit -----------------------------------------------------


def test_offene_felder_meldet_fehlende_angaben():
    deal = mache_deal(kontonummer=None, freibetrag=None)
    assert {f.feld for f in derived.offene_felder(deal)} == set(derived.WUENSCHENSWERTE_FELDER)


def test_uebersprungene_felder_gelten_nicht_als_offen():
    deal = mache_deal(kontonummer=None, freibetrag=None)
    derived.uebersprungene_felder_speichern(deal, ["kontonummer"])
    offen = {f.feld for f in derived.offene_felder(deal)}
    assert "kontonummer" not in offen
    assert "freibetrag" in offen


def test_kaputte_uebersprungene_felder_werden_ignoriert():
    deal = mache_deal()
    deal.uebersprungene_felder = "kein json"
    assert derived.uebersprungene_felder_liste(deal) == []


def test_offene_praemie_ohne_erwartungsdatum_ist_ein_offenes_feld():
    deal = mache_deal(praemien=[("bank", "100", False)])
    deal.praemien[0].auszahlung_erwartet = None
    felder = {f.feld for f in derived.offene_felder(deal)}
    assert "praemie_1_auszahlung_erwartet" in felder


def test_vollstaendig_wenn_nichts_offen_ist():
    deal = mache_deal(kuendbar_ab=datetime.date(2026, 12, 1))
    assert derived.ist_vollstaendig(deal) is True
