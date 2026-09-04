"""auszahlungs_sync.py - kein echtes Netzwerk, httpx.post wird gefaked."""

from __future__ import annotations

from decimal import Decimal

import pytest

from praemien_tracker import auszahlungs_sync
from praemien_tracker.models import Bank, Deal, Inhaber, Praemie


class _FakeAntwort:
    def raise_for_status(self):
        pass


@pytest.fixture
def deal(db):
    d = Deal(kontoart="Girokonto", bank=Bank(name="Testbank"), inhaber=Inhaber(name="Max"))
    db.add(d)
    db.commit()
    return d


@pytest.fixture
def aufrufe(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    aufgezeichnet = []
    monkeypatch.setattr(
        auszahlungs_sync.httpx,
        "post",
        lambda *a, **kw: aufgezeichnet.append(kw["json"]) or _FakeAntwort(),
    )
    return aufgezeichnet


def test_ohne_token_wird_nichts_gesendet(db, deal, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    aufgerufen = []
    monkeypatch.setattr(
        auszahlungs_sync.httpx, "post", lambda *a, **kw: aufgerufen.append(kw) or _FakeAntwort()
    )

    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()

    assert aufgerufen == []


def test_neue_praemie_mit_erwartetem_monat_wird_gemeldet(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100.00"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()

    assert len(aufrufe) == 1
    payload = aufrufe[0]
    assert payload["aktion"] == "upsert"
    assert payload["external_id"] == f"praemientracker:{praemie.id}"
    assert Decimal(payload["betrag"]) == Decimal("100.00")
    assert payload["datum"] == "2026-09-15"


def test_neue_praemie_ohne_erwarteten_monat_wird_nicht_gemeldet(db, deal, aufrufe):
    praemie = Praemie(deal_id=deal.id, quelle="bank", betrag=Decimal("50"), erhalten=False, auszahlung_erwartet=None)
    db.add(praemie)
    db.commit()

    assert aufrufe == []


def test_neue_spartanien_praemie_wird_nicht_gemeldet(db, deal, aufrufe):
    """Nur Bank-Prämien erreichen das Konto, das der Budget-Tracker führt.
    Eine Spartanien-Prämie dort als Forecast-Eintrag zu führen, sagte einen
    Geldeingang vorher, der auf diesem Konto nie ankommt."""
    praemie = Praemie(
        deal_id=deal.id, quelle="spartanien", betrag=Decimal("50"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()

    assert aufrufe == []


def test_aenderung_an_spartanien_praemie_zieht_alten_eintrag_zurueck(db, deal, aufrufe):
    """Eine Prämie, die von "bank" auf "spartanien" umgestellt wird, muss den
    im Budget-Tracker bereits angelegten Eintrag wieder loswerden."""
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    praemie.quelle = "spartanien"
    db.commit()

    assert aufrufe == [{"external_id": f"praemientracker:{praemie.id}", "aktion": "loeschen"}]


def test_betragsaenderung_wird_als_upsert_gemeldet(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    praemie.betrag = Decimal("150.00")
    db.commit()

    assert len(aufrufe) == 1
    assert aufrufe[0]["aktion"] == "upsert"
    assert Decimal(aufrufe[0]["betrag"]) == Decimal("150.00")


def test_bezeichnung_enthaelt_bank_kontoart_und_namen(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()

    assert aufrufe[0]["bezeichnung"] == "Prämienauszahlung – Testbank · Girokonto · Max"


def test_bezeichnung_nutzt_zweck_statt_generischem_text_wenn_vorhanden(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id,
        quelle="bank",
        betrag=Decimal("100"),
        erhalten=False,
        auszahlung_erwartet="2026-09",
        zweck="für den Kontowechselservice",
    )
    db.add(praemie)
    db.commit()

    assert aufrufe[0]["bezeichnung"] == "für den Kontowechselservice – Testbank · Girokonto · Max"


def test_erhalten_markiert_loest_loeschen_aus(db, deal, aufrufe):
    """Eine bereits erhaltene Auszahlung soll die Forecast-Prognose im
    Budget-Tracker nicht länger belasten."""
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    praemie.erhalten = True
    db.commit()

    assert aufrufe == [{"external_id": f"praemientracker:{praemie.id}", "aktion": "loeschen"}]


def test_geloeschte_praemie_meldet_loeschen(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()
    praemie_id = praemie.id

    db.delete(praemie)
    db.commit()

    assert aufrufe == [{"external_id": f"praemientracker:{praemie_id}", "aktion": "loeschen"}]


def test_unveraenderter_commit_loest_kein_event_aus(db, deal, aufrufe):
    praemie = Praemie(
        deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
    )
    db.add(praemie)
    db.commit()
    aufrufe.clear()

    db.commit()

    assert aufrufe == []


class TestSendeAlleAktuellen:
    """Nachtrag beim Start (auszahlungs_sync.sende_alle_aktuellen) - meldet
    auch Prämien, an denen seit dem Update nichts geändert wurde."""

    def test_meldet_jede_bestehende_faellige_bank_praemie(self, db, deal, aufrufe):
        p1 = Praemie(deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09")
        p2 = Praemie(deal_id=deal.id, quelle="bank", betrag=Decimal("50"), erhalten=False, auszahlung_erwartet="2026-10")
        db.add_all([p1, p2])
        db.commit()
        aufrufe.clear()

        anzahl = auszahlungs_sync.sende_alle_aktuellen()

        assert anzahl == 2
        external_ids = {a["external_id"] for a in aufrufe}
        assert external_ids == {f"praemientracker:{p1.id}", f"praemientracker:{p2.id}"}
        assert all(a["aktion"] == "upsert" for a in aufrufe)

    def test_raeumt_frueher_uebermittelte_spartanien_praemie_ab(self, db, deal, aufrufe):
        """Der Aufräumweg für Einträge, die vor der Quellen-Beschränkung
        schon im Budget-Tracker gelandet sind: sende_alle_aktuellen() läuft
        bei jedem Add-on-Start und meldet für jede Spartanien-Prämie
        "loeschen" - ohne dass jemand sie dort von Hand suchen müsste."""
        spartanien = Praemie(
            deal_id=deal.id, quelle="spartanien", betrag=Decimal("50"), erhalten=False, auszahlung_erwartet="2026-10"
        )
        bank = Praemie(
            deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
        )
        db.add_all([spartanien, bank])
        db.commit()
        aufrufe.clear()

        auszahlungs_sync.sende_alle_aktuellen()

        nach_id = {a["external_id"]: a for a in aufrufe}
        assert nach_id[f"praemientracker:{spartanien.id}"]["aktion"] == "loeschen"
        assert nach_id[f"praemientracker:{bank.id}"]["aktion"] == "upsert"

    def test_meldet_loeschen_fuer_bereits_erhaltene_praemie(self, db, deal, aufrufe):
        praemie = Praemie(deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=True, auszahlung_erwartet="2026-09")
        db.add(praemie)
        db.commit()
        aufrufe.clear()

        auszahlungs_sync.sende_alle_aktuellen()

        assert aufrufe == [{"external_id": f"praemientracker:{praemie.id}", "aktion": "loeschen"}]

    def test_ohne_praemien_passiert_nichts(self, db, aufrufe):
        anzahl = auszahlungs_sync.sende_alle_aktuellen()

        assert anzahl == 0
        assert aufrufe == []

    def test_aktualisiert_bezeichnung_bereits_bestehender_eintraege(self, db, deal, aufrufe):
        """Beantwortet 'aktualisiert das auch schon bestehende Forecast-
        Einträge': ja, sobald sende_alle_aktuellen() erneut läuft (bei jedem
        Add-on-Start, siehe main.py) - der Budget-Tracker ist über die
        external_id idempotent, ein erneutes 'upsert' überschreibt die
        bezeichnung eines schon vorhandenen Eintrags."""
        praemie = Praemie(
            deal_id=deal.id, quelle="bank", betrag=Decimal("100"), erhalten=False, auszahlung_erwartet="2026-09"
        )
        db.add(praemie)
        db.commit()
        aufrufe.clear()

        deal.bank.name = "Neue Bank GmbH"
        db.commit()
        aufrufe.clear()

        auszahlungs_sync.sende_alle_aktuellen()

        assert len(aufrufe) == 1
        assert aufrufe[0]["aktion"] == "upsert"
        assert aufrufe[0]["bezeichnung"] == "Prämienauszahlung – Neue Bank GmbH · Girokonto · Max"
