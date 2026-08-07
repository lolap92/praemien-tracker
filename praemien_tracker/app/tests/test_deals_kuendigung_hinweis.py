"""routers/deals.py: manuelles Bearbeiten des Kündigungshinweises setzt das
kuendigung_hinweis_ki-Flag zurück - der Text gehört ab dann dem Nutzer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber

client = TestClient(app)


@pytest.fixture()
def ki_deal(db) -> Deal:
    bank = Bank(name="Testbank")
    inhaber = Inhaber(name="Alice")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(
        bank=bank,
        inhaber=inhaber,
        kontoart="Girokonto",
        kuendigung_hinweis="KI-Text",
        kuendigung_hinweis_url="https://x",
        kuendigung_hinweis_ki=True,
    )
    db.add(deal)
    db.commit()
    return deal


def test_kuendigung_hinweis_update_setzt_ki_flag_zurueck(db, ki_deal):
    antwort = client.post(
        f"/deals/{ki_deal.id}/kuendigung-hinweis",
        data={"kuendigung_hinweis": "Eigener Text", "kuendigung_hinweis_url": "https://eigene-quelle"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.refresh(ki_deal)
    assert ki_deal.kuendigung_hinweis == "Eigener Text"
    assert ki_deal.kuendigung_hinweis_ki is False


def test_deal_update_setzt_ki_flag_ebenfalls_zurueck(db, ki_deal):
    antwort = client.post(
        f"/deals/{ki_deal.id}",
        data={
            "bank": "Testbank",
            "inhaber": "Alice",
            "kontoart": "Girokonto",
            "kuendigung_hinweis": "KI-Text",
            "kuendigung_hinweis_url": "https://x",
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.refresh(ki_deal)
    assert ki_deal.kuendigung_hinweis_ki is False
