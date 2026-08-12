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
    assert derived.status(deal, HEUTE) == derived.STATUS_PRAEMIE_WARTEN


def test_status_pruefen_wenn_naechste_pruefung_erreicht():
    # Next check is today (HEUTE), so we should be in STATUS_PRAEMIE_PRUEFEN
    deal = mache_deal(praemien=[("bank", "100", False)])
    deal.praemien[0].auszahlung_erwartet = "2026-07"  # First day of July 2026, which is <= HEUTE (2026-07-30)
    assert derived.status(deal, HEUTE) == derived.STATUS_PRAEMIE_PRUEFEN


def test_status_warten_wenn_naechste_pruefung_in_zukunft():
    # Next check is in the future (August 2026), so we should be in STATUS_PRAEMIE_WARTEN
    deal = mache_deal(praemien=[("bank", "100", False)])
    deal.praemien[0].auszahlung_erwartet = "2026-08"  # August 2026, which is in the future relative to HEUTE
    assert derived.status(deal, HEUTE) == derived.STATUS_PRAEMIE_WARTEN


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
        ("2026-05", datetime.date(2026, 5, 1)),  # seit B12 kanonisch
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


def test_zugangsdaten_erzeugt_deal_pflegen_todo_nur_wenn_nicht_gesichert():
    ohne = mache_deal(zugangsdaten_gespeichert=False)
    mit = mache_deal(zugangsdaten_gespeichert=True)
    assert any(t.kategorie == "Deal pflegen" for t in derived.deal_todos(ohne, HEUTE))
    assert not any(t.kategorie == "Deal pflegen" for t in derived.deal_todos(mit, HEUTE))


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
    deal = mache_deal(kontonummer=None, zugangsdaten_gespeichert=False)
    assert {f.feld for f in derived.offene_felder(deal)} == set(derived.WUENSCHENSWERTE_FELDER)


def test_uebersprungene_felder_gelten_nicht_als_offen():
    deal = mache_deal(kontonummer=None, zugangsdaten_gespeichert=False)
    derived.uebersprungene_felder_speichern(deal, ["kontonummer"])
    offen = {f.feld for f in derived.offene_felder(deal)}
    assert "kontonummer" not in offen
    assert "zugangsdaten_gespeichert" in offen


def test_zugangsdaten_gelten_bei_gekuendigtem_oder_storniertem_deal_nicht_als_offen():
    """Anders als Kontonummer/Auszahlung ist ein leerer Wert hier nur solange
    eine Lücke, wie das Konto noch läuft."""
    gekuendigt = mache_deal(zugangsdaten_gespeichert=False, gekuendigt=True)
    storniert = mache_deal(zugangsdaten_gespeichert=False)
    storniert.storniert = True
    assert "zugangsdaten_gespeichert" not in {f.feld for f in derived.offene_felder(gekuendigt)}
    assert "zugangsdaten_gespeichert" not in {f.feld for f in derived.offene_felder(storniert)}


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


def test_praemie_naechste_pruefung_korrigiert_mismatch():
    p = Praemie(quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-12")
    # Set a manual check date in August (which is earlier than December)
    p.naechste_pruefung_am = datetime.date(2026, 8, 24)
    naechste = derived.praemie_naechste_pruefung(p, datetime.date(2026, 8, 11))
    # It should correct it to 2026-12-01 (first day of December)
    assert naechste == datetime.date(2026, 12, 1)


def test_deal_todos_creates_separate_todos_for_each_open_reward():
    deal = mache_deal(
        praemien=[("spartanien", "60", False), ("bank", "95", False)]
    )
    deal.praemien[0].auszahlung_erwartet = "2026-12"
    deal.praemien[1].auszahlung_erwartet = "2026-12"

    todos = derived.deal_todos(deal, HEUTE)
    praemie_todos = [t for t in todos if t.kategorie == "Auf Prämie warten"]

    # We should have exactly 2 independent Todos for "Auf Prämie warten"
    assert len(praemie_todos) == 2
    assert "Spartanien" in praemie_todos[0].text
    assert "Bank" in praemie_todos[1].text
    assert praemie_todos[0].elemente == [deal.praemien[0]]
    assert praemie_todos[1].elemente == [deal.praemien[1]]


def test_deal_todos_sortiert_gemischte_praemien_je_nach_eigenem_pruefdatum():
    """Ein Deal mit zwei offenen Prämien, von denen nur eine fällig ist, muss
    beide ToDo-Kategorien bedienen - je Prämie nach ihrem eigenen Prüfdatum,
    nicht pauschal nach dem (auf 'prüfen' stehenden) Deal-Status. Sonst würde
    die noch nicht fällige Prämie fälschlich unter 'Prämienauszahlung
    prüfen' auftauchen."""
    deal = mache_deal(praemien=[("spartanien", "60", False), ("bank", "95", False)])
    deal.praemien[0].auszahlung_erwartet = "2026-07"  # fällig (<= HEUTE)
    deal.praemien[1].auszahlung_erwartet = "2026-08"  # noch in der Zukunft

    # Der Deal-Status schlägt "prüfen" an, sobald irgendeine Prämie fällig ist.
    assert derived.status(deal, HEUTE) == derived.STATUS_PRAEMIE_PRUEFEN

    todos = derived.deal_todos(deal, HEUTE)
    pruefen = [t for t in todos if t.kategorie == "Prämienauszahlung prüfen"]
    warten = [t for t in todos if t.kategorie == "Auf Prämie warten"]

    assert len(pruefen) == 1
    assert pruefen[0].elemente == [deal.praemien[0]]
    assert len(warten) == 1
    assert warten[0].elemente == [deal.praemien[1]]


def test_deal_todos_and_alle_todos_contain_kontoart():
    # Setup a deal with conditions and an open task
    deal = mache_deal(
        bedingungen=[("3 Trades", False)],
        kontonummer="DE123",
        freibetrag=Decimal("100"),
    )
    # The default kontoart in mache_deal is "Depot"
    assert deal.kontoart == "Depot"

    # Verify that the deal todo text contains the kontoart "Depot"
    todos = derived.deal_todos(deal, HEUTE)
    assert len(todos) > 0
    for t in todos:
        if t.kategorie != "Zu prüfen":
            assert "Depot" in t.text
            assert f"{deal.bank.name} · {deal.kontoart} · {deal.inhaber.name}" in t.text

    # Verify that manual task prefix contains the kontoart "Depot"
    aufgabe = Aufgabe(beschreibung="Manuelle Aktion", erledigt=False, deal=deal)
    all_t = derived.alle_todos([deal], [aufgabe], HEUTE)
    manuelle_todos = [t for t in all_t if t.kategorie == "Manuelle Aufgaben"]
    assert len(manuelle_todos) == 1
    assert "Depot" in manuelle_todos[0].text
    assert f"{deal.bank.name} · {deal.kontoart} · {deal.inhaber.name}" in manuelle_todos[0].text
