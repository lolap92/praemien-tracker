from __future__ import annotations

from decimal import Decimal
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Aufgabe, Bank, Bedingung, Deal, Inhaber, Praemie

client = TestClient(app)


def test_deal_stornieren_schliesst_auch_aufgaben(db):
    # Setup bank and inhaber
    bank = Bank(name="Storno-Test-Bank")
    inhaber = Inhaber(name="Storno-Test-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()

    # Create a Deal
    deal = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Girokonto"
    )

    # Add a task/aufgabe
    aufgabe = Aufgabe(beschreibung="Test-Aufgabe", erledigt=False)
    deal.aufgaben.append(aufgabe)

    # Add a bedingung
    bedingung = Bedingung(beschreibung="Test-Bedingung", erfuellt=False)
    deal.bedingungen.append(bedingung)

    # Add a praemie
    praemie = Praemie(quelle="bank", betrag=Decimal("100.00"), erhalten=False)
    deal.praemien.append(praemie)

    db.add(deal)
    db.commit()

    # Verify initial state
    assert not aufgabe.erledigt
    assert not bedingung.erfuellt
    assert not praemie.erhalten

    # Call the stornieren endpoint
    antwort = client.post(f"/deals/{deal.id}/stornieren", follow_redirects=False)
    assert antwort.status_code == 303  # Redirects back to edit form

    # Reload from DB
    db.expire_all()
    loaded_deal = db.get(Deal, deal.id)

    assert loaded_deal.storniert
    assert all(b.erfuellt for b in loaded_deal.bedingungen)
    assert all(p.erhalten for p in loaded_deal.praemien)
    assert all(a.erledigt for a in loaded_deal.aufgaben)
