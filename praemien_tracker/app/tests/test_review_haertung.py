"""Fachliches Review, Etappe D: die POST-Handler dürfen bei verstümmelten
Formulardaten keinen 500 auslösen - dieselbe Robustheit, mit der die GET-Filter
schon arbeiten (deals._als_int, vgl. altes Finding A6)."""
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Aufgabe

client = TestClient(app)


class TestNeueAufgabeRobust:
    def test_nicht_numerische_deal_id_wird_ignoriert(self, db):
        antwort = client.post(
            "/todos/aufgaben",
            data={"beschreibung": "Testaufgabe", "deal_id": "abc"},
            follow_redirects=False,
        )
        assert antwort.status_code == 303
        a = db.query(Aufgabe).filter(Aufgabe.beschreibung == "Testaufgabe").one()
        assert a.deal_id is None

    def test_unbekannte_deal_id_loest_keinen_fk_fehler_aus(self, db):
        antwort = client.post(
            "/todos/aufgaben",
            data={"beschreibung": "Waise", "deal_id": "999999"},
            follow_redirects=False,
        )
        assert antwort.status_code == 303
        a = db.query(Aufgabe).filter(Aufgabe.beschreibung == "Waise").one()
        assert a.deal_id is None


class TestUebernehmenRobust:
    def test_verstuemmelte_ids_ergeben_keinen_500(self, db):
        # Kaputte hidden-Felder: früher hätte int("x") die Seite mit 500
        # abgebrochen. Jetzt werden die Werte übergangen; ohne gültige
        # Vorschläge landet der Ablauf sauf einer normalen Seite/Weiterleitung.
        antwort = client.post(
            "/vorschlaege/uebernehmen/bestaetigen",
            data={
                "vorschlag_ids": ["x", "y"],
                "praemien_anzahl": "nichtzahl",
            },
            follow_redirects=False,
        )
        assert antwort.status_code < 500
