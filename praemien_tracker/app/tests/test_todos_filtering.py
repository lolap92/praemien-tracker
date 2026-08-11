from __future__ import annotations

import datetime
from decimal import Decimal
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber, Praemie

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
