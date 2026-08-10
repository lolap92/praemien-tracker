"""routers/inhaber.py: einzige Stelle, an der sich ist_minderjaehrig setzen
lässt - ohne diese Seite gibt es keinen Weg, ein Haushaltsmitglied nachträglich
als minderjährig zu kennzeichnen (neue Inhaber entstehen automatisch beim
ersten Deal, immer als erwachsen, siehe helpers.get_or_create_inhaber)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Inhaber

client = TestClient(app)


def test_inhaber_seite_zeigt_alle_inhaber(db):
    db.add_all([Inhaber(name="Alice"), Inhaber(name="Kim", ist_minderjaehrig=True)])
    db.commit()

    antwort = client.get("/inhaber")
    assert antwort.status_code == 200
    assert "Alice" in antwort.text
    assert "Kim" in antwort.text


def test_inhaber_speichern_setzt_minderjaehrig(db):
    """Ein bisher als erwachsen geführter Inhaber (z.B. automatisch beim
    ersten Deal angelegt) lässt sich nachträglich als minderjährig markieren
    - die Checkbox für alle anderen Inhaber bleibt dabei unangetastet."""
    kind = Inhaber(name="Kim")
    erwachsen = Inhaber(name="Bob")
    db.add_all([kind, erwachsen])
    db.commit()
    kind_id, erwachsen_id = kind.id, erwachsen.id

    antwort = client.post(
        "/inhaber",
        data={f"minderjaehrig_{kind_id}": "on"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.refresh(kind)
    db.refresh(erwachsen)
    assert kind.ist_minderjaehrig is True
    assert erwachsen.ist_minderjaehrig is False


def test_inhaber_speichern_kann_minderjaehrig_auch_wieder_entfernen(db):
    kind = Inhaber(name="Kim", ist_minderjaehrig=True)
    db.add(kind)
    db.commit()
    kind_id = kind.id

    client.post("/inhaber", data={}, follow_redirects=False)

    db.refresh(kind)
    assert kind.ist_minderjaehrig is False
