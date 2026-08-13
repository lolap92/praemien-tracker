import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from praemien_tracker.main import app
from praemien_tracker.models import Deal, Bank, Inhaber

client = TestClient(app)


def test_ajax_add_praemie(db: Session):
    # Setup Bank and Inhaber
    bank = Bank(name="AJAX Bank")
    inhaber = Inhaber(name="Max Mustermann")
    db.add_all([bank, inhaber])
    db.commit()

    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Girokonto")
    db.add(deal)
    db.commit()

    headers = {"X-Requested-With": "XMLHttpRequest"}
    payload = {
        "neu_praemie_quelle": "bank",
        "neu_praemie_betrag": "100.50",
        "neu_praemie_erhalten": "on",
        "neu_praemie_auszahlung_erwartet": "2026-05",
    }

    response = client.post(
        f"/deals/{deal.id}/praemien",
        data=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["quelle"] == "bank"
    assert data["betrag"] == "100.50"
    assert data["erhalten"] is True
    assert data["auszahlung_erwartet"] == "2026-05"


def test_ajax_add_bedingung(db: Session):
    # Setup Bank and Inhaber
    bank = Bank(name="AJAX Bank 2")
    inhaber = Inhaber(name="Max Mustermann 2")
    db.add_all([bank, inhaber])
    db.commit()

    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Girokonto")
    db.add(deal)
    db.commit()

    headers = {"X-Requested-With": "XMLHttpRequest"}
    payload = {
        "neu_bedingung_beschreibung": "3 Trades machen",
        "neu_bedingung_faellig_bis": "2026-06-01",
    }

    response = client.post(
        f"/deals/{deal.id}/bedingungen",
        data=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["beschreibung"] == "3 Trades machen"
    assert data["faellig_bis"] == "2026-06-01"
    assert data["erfuellt"] is False


def test_ajax_add_aufgabe(db: Session):
    # Setup Bank and Inhaber
    bank = Bank(name="AJAX Bank 3")
    inhaber = Inhaber(name="Max Mustermann 3")
    db.add_all([bank, inhaber])
    db.commit()

    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Girokonto")
    db.add(deal)
    db.commit()

    headers = {"X-Requested-With": "XMLHttpRequest"}
    payload = {
        "neu_aufgabe_beschreibung": "Konto kündigen",
        "neu_aufgabe_faellig_bis": "2026-07-01",
    }

    response = client.post(
        f"/deals/{deal.id}/aufgaben",
        data=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["beschreibung"] == "Konto kündigen"
    assert data["faellig_bis"] == "2026-07-01"
    assert data["erledigt"] is False


def test_ajax_add_url(db: Session):
    # Setup Bank and Inhaber
    bank = Bank(name="AJAX Bank 4")
    inhaber = Inhaber(name="Max Mustermann 4")
    db.add_all([bank, inhaber])
    db.commit()

    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Girokonto")
    db.add(deal)
    db.commit()

    headers = {"X-Requested-With": "XMLHttpRequest"}
    payload = {
        "url": "https://example.com/ajax-login",
        "bezeichnung": "Login Page",
    }

    response = client.post(
        f"/deals/{deal.id}/urls",
        data=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["url"] == "https://example.com/ajax-login"
    assert data["bezeichnung"] == "Login Page"
