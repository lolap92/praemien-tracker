from __future__ import annotations

import datetime
from decimal import Decimal
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Aufgabe, Bank, Bedingung, Deal, Inhaber, Praemie

client = TestClient(app)

def test_todos_sorting_and_filtering(db):
    # Setup test data
    bank = Bank(name="Test Bank")
    inhaber = Inhaber(name="Max Mustermann")
    db.add_all([bank, inhaber])
    db.commit()

    # Deal 1: Spartanien Deal with a premium waiting
    deal_spartanien = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Giro",
        kontonummer="DE1111",
        zugangsdaten_gespeichert=True
    )
    # This premium is from Spartanien, next check in 5 days
    p_spartanien = Praemie(
        quelle="spartanien",
        betrag=Decimal("50.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=5)
    )
    deal_spartanien.praemien.append(p_spartanien)

    # Deal 2: Bank Deal with a premium waiting (earlier check date)
    deal_bank = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Depot",
        kontonummer="DE2222",
        zugangsdaten_gespeichert=True
    )
    # This premium is from Bank, next check in 2 days
    p_bank = Praemie(
        quelle="bank",
        betrag=Decimal("100.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=2)
    )
    deal_bank.praemien.append(p_bank)

    db.add_all([deal_spartanien, deal_bank])
    db.commit()

    # 1. Test Sorting: Earlier check date should come first
    antwort = client.get("/todos")
    assert antwort.status_code == 200
    html = antwort.text

    # "Bank" premium is 2 days out, "Spartanien" is 5 days out.
    # Therefore, "Bank" should appear before "Spartanien" in the HTML.
    idx_bank = html.find("Prämie prüfen (Bank, 100.00 €)")
    idx_spartanien = html.find("Prämie prüfen (Spartanien, 50.00 €)")
    assert idx_bank != -1
    assert idx_spartanien != -1
    assert idx_bank < idx_spartanien, "Bank (2 days) should be listed before Spartanien (5 days)"

    # 2. Test Filtering by "spartanien"
    antwort_spartanien = client.get("/todos?quelle=spartanien")
    assert antwort_spartanien.status_code == 200
    html_spartanien = antwort_spartanien.text
    assert "Prämie prüfen (Spartanien, 50.00 €)" in html_spartanien
    assert "Prämie prüfen (Bank, 100.00 €)" not in html_spartanien

    # 3. Test Filtering by "bank"
    antwort_bank = client.get("/todos?quelle=bank")
    assert antwort_bank.status_code == 200
    html_bank = antwort_bank.text
    assert "Prämie prüfen (Spartanien, 50.00 €)" not in html_bank
    assert "Prämie prüfen (Bank, 100.00 €)" in html_bank


def test_todos_filtering_by_new_statuses(db):
    # Setup test data
    bank = Bank(name="Test Bank 2")
    inhaber = Inhaber(name="Max Mustermann 2")
    db.add_all([bank, inhaber])
    db.commit()

    # Deal 1: "Prämienauszahlung prüfen" because check date is reached
    deal_pruefen = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Giro",
        kontonummer="DE3333",
        zugangsdaten_gespeichert=True
    )
    p_pruefen = Praemie(
        quelle="spartanien",
        betrag=Decimal("150.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() - datetime.timedelta(days=1)  # reached (yesterday)
    )
    deal_pruefen.praemien.append(p_pruefen)

    # Deal 2: "Auf Prämie warten" because check date is in the future
    deal_warten = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Depot",
        kontonummer="DE4444",
        zugangsdaten_gespeichert=True
    )
    p_warten = Praemie(
        quelle="bank",
        betrag=Decimal("200.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=10)  # in future
    )
    deal_warten.praemien.append(p_warten)

    db.add_all([deal_pruefen, deal_warten])
    db.commit()

    # Get /todos
    antwort = client.get("/todos")
    assert antwort.status_code == 200
    html = antwort.text

    # Verify both categories show up as tabs / panels
    assert "Prämienauszahlung prüfen" in html
    assert "Auf Prämie warten" in html

    # Verify the specific texts are present in the HTML response
    assert "Prämie prüfen (Spartanien, 150.00 €)" in html
    assert "Prämie prüfen (Bank, 200.00 €)" in html

    # Test filtering by source: Spartanien
    antwort_spartanien = client.get("/todos?quelle=spartanien")
    html_spartanien = antwort_spartanien.text
    assert "Prämie prüfen (Spartanien, 150.00 €)" in html_spartanien
    assert "Prämie prüfen (Bank, 200.00 €)" not in html_spartanien

    # Test filtering by source: Bank
    antwort_bank = client.get("/todos?quelle=bank")
    html_bank = antwort_bank.text
    assert "Prämie prüfen (Spartanien, 150.00 €)" not in html_bank
    assert "Prämie prüfen (Bank, 200.00 €)" in html_bank


def test_manuelle_aufgaben_tab_bleibt_ohne_offene_aufgabe_erreichbar(db):
    """Ohne jede offene manuelle Aufgabe (und ohne Deals) muss der Tab
    trotzdem existieren - er ist die einzige Stelle, an der sich die erste
    Aufgabe anlegen lässt (siehe todos.py: gruppen.setdefault)."""
    antwort = client.get("/todos")
    assert antwort.status_code == 200
    assert 'id="todotab-manuell"' in antwort.text
    assert 'id="panel-manuell"' in antwort.text
    # Ohne echten Inhalt sonst nirgendwo ist "Manuelle Aufgaben" der Default-Tab.
    assert 'id="todotab-manuell" checked' in antwort.text


def test_default_tab_ist_erste_kategorie_mit_inhalt_nicht_manuelle_aufgaben(db):
    """Gibt es woanders echten Inhalt, gewinnt der (in der Reihenfolge erste)
    damit - nicht die leere 'Manuelle Aufgaben'-Kachel, obwohl sie zuerst in
    KATEGORIE_REIHENFOLGE steht und jetzt immer sichtbar ist."""
    bank = Bank(name="Default-Tab-Testbank")
    inhaber = Inhaber(name="Default-Tab-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", zugangsdaten_gespeichert=True)
    deal.bedingungen.append(Bedingung(beschreibung="offen", erfuellt=False))
    db.add(deal)
    db.commit()

    antwort = client.get("/todos")
    assert 'id="todotab-bedingungen" checked' in antwort.text
    assert 'id="todotab-manuell" checked' not in antwort.text


def test_neue_aufgabe_und_erledigte_aufgaben_stecken_im_manuell_tab(db):
    """Beide Blöcke tragen die CSS-Klasse, die sie an den 'manuell'-Tab
    bindet (siehe body:has(#todotab-manuell:checked) in style.css) - das
    HTML selbst liefert der Server immer, die Sichtbarkeit regelt reines CSS.
    "Neue Aufgabe" ist zusätzlich ein <details> hinter einem Button-Umschalter
    (per default eingeklappt, kein dauerhaft offenes Formular mehr)."""
    db.add(Aufgabe(beschreibung="Erledigt", erledigt=True))
    db.commit()

    antwort = client.get("/todos")
    assert '<details class="neue-aufgabe-card">' in antwort.text
    assert "+ Neue Aufgabe" in antwort.text
    assert 'class="card erledigte-aufgaben-card"' in antwort.text
    assert "Erledigte Aufgaben" in antwort.text


def test_quelle_filter_traegt_css_klasse_fuer_praemien_tabs(db):
    """Der Quelle-Filter bekommt dieselbe Bindung wie die Aufgaben-Karten,
    nur an die beiden Prämien-Tabs statt an 'manuell' (siehe style.css)."""
    antwort = client.get("/todos")
    assert 'class="filterleiste todo-quelle-filter"' in antwort.text


def test_quelle_filter_steht_hinter_den_kacheln_vor_den_todos(db):
    """Der Filter soll unter der Status-Kachel-Navigation stehen, aber über
    dem eigentlichen ToDo-Inhalt - also im Markup nach .todo-tabs-nav und vor
    .todo-panels."""
    antwort = client.get("/todos")
    html = antwort.text
    idx_kacheln = html.index('class="todo-tabs-nav"')
    idx_filter = html.index('class="filterleiste todo-quelle-filter"')
    idx_panels = html.index('class="todo-panels"')
    assert idx_kacheln < idx_filter < idx_panels
