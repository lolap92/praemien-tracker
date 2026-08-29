"""Der "Archiv"-Link im Protokoll: eine gerenderte Momentaufnahme der
Dealseite (deal_snapshot.html), die anders als der Link auf deals/{id} auch
nach dem Löschen des Deals noch erreichbar bleibt (siehe protokoll.py::
_html_snapshot_von und routers/protokoll.py::protokoll_archiv)."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber, Praemie, ProtokollEintrag

client = TestClient(app)


def test_deal_anlegen_erzeugt_protokoll_eintrag_mit_html_snapshot(db):
    bank = Bank(name="Snapshot-Testbank")
    inhaber = Inhaber(name="Snapshot-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer="DE1", zugangsdaten_gespeichert=True)
    db.add(deal)
    db.commit()

    eintrag = (
        db.query(ProtokollEintrag)
        .filter(ProtokollEintrag.tabelle == "Deal", ProtokollEintrag.objekt_id == deal.id, ProtokollEintrag.aktion == "erstellt")
        .one()
    )
    assert eintrag.html_snapshot is not None
    assert "Snapshot-Testbank" in eintrag.html_snapshot
    assert "Snapshot-Inhaber" in eintrag.html_snapshot


def test_bank_und_inhaber_name_aufgeloest_auch_bei_rohem_fremdschluessel(db):
    """Deals, die (wie in vielen Tests und potenziell künftigem Bulk-Code)
    per bank_id=/inhaber_id= statt per Objektzuweisung (deal.bank = ...)
    angelegt werden, lieferten bank_name/inhaber_name auf dem 'erstellt'-
    Eintrag bisher als None: SQLAlchemy löst die bank-/inhaber-Beziehung an
    einem druckfrischen Objekt innerhalb von after_flush nicht lazy auf. Der
    Fallback über Session.get() (_bank_von/_inhaber_von) behebt das."""
    bank = Bank(name="Fremdschluessel-Bank")
    inhaber = Inhaber(name="Fremdschluessel-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer="DE9", zugangsdaten_gespeichert=True)
    db.add(deal)
    db.commit()

    eintrag = (
        db.query(ProtokollEintrag)
        .filter(ProtokollEintrag.tabelle == "Deal", ProtokollEintrag.objekt_id == deal.id, ProtokollEintrag.aktion == "erstellt")
        .one()
    )
    assert eintrag.bank_name == "Fremdschluessel-Bank"
    assert eintrag.inhaber_name == "Fremdschluessel-Inhaber"


def test_archiv_route_liefert_gespeicherten_snapshot(db):
    bank = Bank(name="Archiv-Testbank")
    inhaber = Inhaber(name="Archiv-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer="DE2", zugangsdaten_gespeichert=True)
    db.add(deal)
    db.commit()

    eintrag = (
        db.query(ProtokollEintrag)
        .filter(ProtokollEintrag.tabelle == "Deal", ProtokollEintrag.objekt_id == deal.id)
        .one()
    )

    antwort = client.get(f"/protokoll/{eintrag.id}/archiv")
    assert antwort.status_code == 200
    assert "text/html" in antwort.headers["content-type"]
    assert "Archiv-Testbank" in antwort.text


def test_archiv_bleibt_nach_dem_loeschen_des_deals_erreichbar(db):
    """Der eigentliche Zweck: der Live-Link auf deals/{id} stirbt mit dem
    Deal, der Archiv-Link nicht."""
    bank = Bank(name="Verschwindet-Bank")
    inhaber = Inhaber(name="Verschwindet-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer="DE3", zugangsdaten_gespeichert=True)
    deal.praemien.append(Praemie(quelle="bank", betrag=Decimal("42.00"), erhalten=True))
    db.add(deal)
    db.commit()
    deal_id = deal.id

    assert client.get(f"/deals/{deal_id}").status_code == 200

    loesch_antwort = client.post(f"/deals/{deal_id}/delete", follow_redirects=False)
    assert loesch_antwort.status_code == 303

    assert client.get(f"/deals/{deal_id}").status_code == 404

    geloescht_eintrag = (
        db.query(ProtokollEintrag)
        .filter(
            ProtokollEintrag.tabelle == "Deal",
            ProtokollEintrag.objekt_id == deal_id,
            ProtokollEintrag.aktion == "geloescht",
        )
        .one()
    )
    archiv_antwort = client.get(f"/protokoll/{geloescht_eintrag.id}/archiv")
    assert archiv_antwort.status_code == 200
    assert "Verschwindet-Bank" in archiv_antwort.text
    assert "42,00" in archiv_antwort.text or "42.00" in archiv_antwort.text


def test_archiv_route_404_ohne_snapshot_oder_unbekannten_eintrag(db):
    assert client.get("/protokoll/999999/archiv").status_code == 404


def test_protokoll_seite_zeigt_archiv_link_neben_der_deal_id(db):
    bank = Bank(name="Linktest-Bank")
    inhaber = Inhaber(name="Linktest-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer="DE4", zugangsdaten_gespeichert=True)
    db.add(deal)
    db.commit()

    html = client.get("/protokoll").text
    assert f'href="deals/{deal.id}"' in html
    assert "/archiv" in html
