"""routers/vorschlaege.py: Übernehmen/Verwerfen und die Gruppierung nach
Status."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Deal, DealVorschlag, Inhaber

client = TestClient(app)


@pytest.fixture()
def inhaber(db):
    eintrag = Inhaber(name="Alice")
    db.add(eintrag)
    db.commit()
    return eintrag


def _vorschlag(db, inhaber, status: str, **kwargs) -> DealVorschlag:
    daten = {
        "inhaber_id": inhaber.id,
        "quelle": "mydealz",
        "quelle_url": "https://www.mydealz.de/x",
        "bank_name": "C24",
        "kontoart": "Girokonto",
        "praemie_betrag": Decimal("125.00"),
        "sperrfrist_monate": None,
        "ablehnungsgruende": None,
        "roh_json": (
            '{"bank": "C24", "kontoart": "Girokonto", "inhaber": "Alice", '
            '"praemien": [{"quelle": "bank", "betrag": "125.00", "erhalten": false}], '
            '"bedingungen": [], "urls": [{"url": "https://www.mydealz.de/x", "bezeichnung": "mydealz-Angebot"}]}'
        ),
        "inhalt_hash": "abc123",
        "status": status,
    }
    daten.update(kwargs)
    eintrag = DealVorschlag(**daten)
    db.add(eintrag)
    db.commit()
    return eintrag


def test_vorschlaege_seite_gruppiert_nach_status(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1")
    _vorschlag(db, inhaber, "zu_pruefen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2")
    _vorschlag(db, inhaber, "automatisch_abgelehnt", quelle_url="https://www.mydealz.de/3", inhalt_hash="h3")

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "1 vorgeschlagen" in antwort.text
    assert "1 zu prüfen" in antwort.text
    assert "1 abgelehnt" in antwort.text


def test_uebernehmen_legt_deal_an_und_markiert_vorschlag(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    antwort = client.post(f"/vorschlaege/{vorschlag.id}/uebernehmen", follow_redirects=False)
    assert antwort.status_code == 303

    db.refresh(vorschlag)
    assert vorschlag.status == "uebernommen"

    deal = db.query(Deal).filter(Deal.kontoart == "Girokonto").one()
    assert deal.bank.name == "C24"
    assert deal.inhaber.name == "Alice"
    assert deal.praemien[0].quelle == "bank"
    assert deal.urls[0].url == "https://www.mydealz.de/x"


def test_uebernehmen_funktioniert_auch_bei_automatisch_abgelehnt(db, inhaber):
    """Bewusstes Überstimmen laut Konzept - "Trotzdem übernehmen"."""
    vorschlag = _vorschlag(db, inhaber, "automatisch_abgelehnt")

    antwort = client.post(f"/vorschlaege/{vorschlag.id}/uebernehmen", follow_redirects=False)
    assert antwort.status_code == 303
    db.refresh(vorschlag)
    assert vorschlag.status == "uebernommen"
    assert db.query(Deal).count() == 1


def test_bereits_uebernommener_vorschlag_wird_nicht_doppelt_verarbeitet(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "uebernommen")

    client.post(f"/vorschlaege/{vorschlag.id}/uebernehmen", follow_redirects=False)

    assert db.query(Deal).count() == 0


def test_verwerfen_setzt_nur_den_status(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "zu_pruefen")

    antwort = client.post(f"/vorschlaege/{vorschlag.id}/verwerfen", follow_redirects=False)
    assert antwort.status_code == 303

    db.refresh(vorschlag)
    assert vorschlag.status == "verworfen"
    assert db.query(Deal).count() == 0


def test_verworfener_vorschlag_taucht_nicht_mehr_in_der_liste_auf(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")
    client.post(f"/vorschlaege/{vorschlag.id}/verwerfen", follow_redirects=False)

    antwort = client.get("/vorschlaege")
    assert "0 vorgeschlagen" in antwort.text


def test_unbekannter_vorschlag_liefert_404(db):
    antwort = client.post("/vorschlaege/999999/uebernehmen")
    assert antwort.status_code == 404


def test_unbekannter_vorschlag_beim_verwerfen_wird_ignoriert(db):
    antwort = client.post("/vorschlaege/999999/verwerfen", follow_redirects=False)
    assert antwort.status_code == 303
