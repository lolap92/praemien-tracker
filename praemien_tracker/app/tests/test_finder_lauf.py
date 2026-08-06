"""finder/lauf.py: der komplette Durchlauf, mit Fake-Anthropic-Client und
gepatchten Quellen (kein Netzwerk)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from praemien_tracker.finder import lauf, matching, notify
from praemien_tracker.finder.extraktion import AngebotExtraktion, BedingungExtraktion, RelevanzErgebnis
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.models import DealVorschlag, FinderLauf, Inhaber


class FakeMessages:
    def __init__(self, relevanz: RelevanzErgebnis, extraktion: AngebotExtraktion | None):
        self.relevanz = relevanz
        self.extraktion = extraktion

    def parse(self, *, output_format, **kwargs):
        if output_format is RelevanzErgebnis:
            return SimpleNamespace(parsed_output=self.relevanz, stop_reason="end_turn")
        return SimpleNamespace(parsed_output=self.extraktion, stop_reason="end_turn")


class FakeClient:
    def __init__(self, relevanz: RelevanzErgebnis, extraktion: AngebotExtraktion | None):
        self.messages = FakeMessages(relevanz, extraktion)


class ZaehlenderFakeClient:
    """Wie FakeClient, zählt aber jeden Aufruf von messages.parse - damit
    sich prüfen lässt, ob der Cache einen API-Aufruf tatsächlich einspart."""

    def __init__(self, relevanz: RelevanzErgebnis, extraktion: AngebotExtraktion | None):
        self.relevanz = relevanz
        self.extraktion = extraktion
        self.aufrufe = 0
        self.messages = self

    def parse(self, *, output_format, **kwargs):
        self.aufrufe += 1
        if output_format is RelevanzErgebnis:
            return SimpleNamespace(parsed_output=self.relevanz, stop_reason="end_turn")
        return SimpleNamespace(parsed_output=self.extraktion, stop_reason="end_turn")


@pytest.fixture()
def zwei_inhaber(db):
    """Erwachsene und minderjährige Inhaber - der Lauf soll für *alle*
    gelten, nicht nur Erwachsene (explizite Entscheidung, kein Filter)."""
    Alice = Inhaber(name="Alice")
    Max = Inhaber(name="Max", ist_minderjaehrig=True)
    db.add_all([Alice, Max])
    db.commit()
    return [Alice, Max]


def _patch_quellen(monkeypatch, funde: list[RohFund]) -> None:
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: funde)
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])


def test_lauf_ohne_client_tut_nichts(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(lauf.config, "ANTHROPIC_API_KEY", None)
    zaehler = lauf.taeglicher_lauf(db)
    assert zaehler["gefunden"] == 0
    assert db.query(DealVorschlag).count() == 0


def test_lauf_legt_pro_inhaber_eine_zeile_an_auch_fuer_kinder(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "C24 125 Euro", "Neukunden erhalten 125 Euro.")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 2  # ein Fund, zwei Inhaber
    assert zaehler[matching.STATUS_VORGESCHLAGEN] == 2
    zeilen = db.query(DealVorschlag).all()
    inhaber_namen = {z.inhaber.name for z in zeilen}
    assert inhaber_namen == {"Alice", "Max"}


def test_lauf_ist_wiederholungssicher(db, zwei_inhaber, monkeypatch):
    """Zweiter Lauf mit identischem Fund darf keine weiteren Zeilen anlegen."""
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    lauf.taeglicher_lauf(db, client=client)

    assert db.query(DealVorschlag).count() == 2


def test_irrelevantes_angebot_erzeugt_keinen_vorschlag(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/versicherung", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(RelevanzErgebnis(ist_relevant=False), None)

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 0
    assert db.query(DealVorschlag).count() == 0


def test_benachrichtigung_nur_bei_vorgeschlagen_oder_zu_pruefen(db, zwei_inhaber, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(notify, "benachrichtigen", lambda *a, **kw: aufrufe.append(a))

    # Nur automatisch abgelehnt (Praemie zu niedrig) -> keine Benachrichtigung.
    fund = RohFund("mydealz", "https://mydealz.de/klein", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Klein-Bank", kontoart="Girokonto", praemie_betrag=5.0, bedingungen=[]),
    )
    lauf.taeglicher_lauf(db, client=client)
    assert aufrufe == []

    # Vorgeschlagen -> Benachrichtigung.
    fund2 = RohFund("mydealz", "https://mydealz.de/gross", "t", "x")
    _patch_quellen(monkeypatch, [fund2])
    client2 = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )
    lauf.taeglicher_lauf(db, client=client2)
    assert len(aufrufe) == 1


def _letzter_lauf(db) -> FinderLauf:
    return db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()


def test_erfolgreicher_lauf_protokolliert_zaehlerstaende(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [
        RohFund("mydealz", "https://mydealz.de/1", "t", "x"),
        RohFund("mydealz", "https://mydealz.de/2", "t", "x"),
    ])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [
        RohFund("spartanien", "https://spartanien.de/1", "t", "x"),
    ])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)

    protokoll = _letzter_lauf(db)
    assert protokoll is not None
    assert protokoll.erfolgreich is True
    assert protokoll.mydealz_geladen == 2
    assert protokoll.spartanien_geladen == 1
    assert protokoll.neu_gefunden == 6  # 3 Funde x 2 Inhaber
    assert protokoll.uebersprungen == 0
    assert protokoll.fehler is None
    assert protokoll.beendet_am is not None


def test_ohne_client_wird_trotzdem_protokolliert(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(lauf.config, "ANTHROPIC_API_KEY", None)
    lauf.taeglicher_lauf(db)

    protokoll = _letzter_lauf(db)
    assert protokoll is not None
    assert protokoll.erfolgreich is True
    assert "API-Key" in protokoll.fehler


def test_fehlgeschlagene_quelle_wird_als_fehler_protokolliert(db, zwei_inhaber, monkeypatch):
    def kaputt(*args, **kwargs):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(lauf, "fetch_mydealz", kaputt)
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    client = FakeClient(RelevanzErgebnis(ist_relevant=False), None)

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 0
    protokoll = _letzter_lauf(db)
    # Der Lauf selbst läuft trotzdem durch (die andere Quelle funktioniert) -
    # "erfolgreich", aber mit sichtbarem Fehlertext zur ausgefallenen Quelle.
    assert protokoll.erfolgreich is True
    assert protokoll.mydealz_geladen == 0
    assert "mydealz" in protokoll.fehler
    assert "HTTP 500" in protokoll.fehler


def test_extraktionsfehler_wird_gezaehlt_und_protokolliert(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/kaputt", "t", "x")
    _patch_quellen(monkeypatch, [fund])

    class KaputteMessages:
        def parse(self, *, output_format, **kwargs):
            raise RuntimeError("API-Fehler")

    class KaputterClient:
        messages = KaputteMessages()

    zaehler = lauf.taeglicher_lauf(db, client=KaputterClient())

    assert zaehler["uebersprungen"] == 1
    assert zaehler["gefunden"] == 0
    protokoll = _letzter_lauf(db)
    assert protokoll.erfolgreich is True
    assert protokoll.uebersprungen == 1
    assert "Themen-Check" in protokoll.fehler


def test_unerwarteter_fehler_wird_zurueckgerollt_und_als_fehlgeschlagen_protokolliert(db, zwei_inhaber, monkeypatch):
    """Ein Bug im Matching (o.ä.) darf weder halb gespeicherte Vorschläge
    hinterlassen noch die Seite abstürzen lassen - stattdessen: rollback,
    Lauf als fehlgeschlagen protokolliert."""
    fund = RohFund("mydealz", "https://mydealz.de/bug", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )
    monkeypatch.setattr(
        matching, "bewerten", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Programmierfehler"))
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 0
    assert db.query(DealVorschlag).count() == 0
    protokoll = _letzter_lauf(db)
    assert protokoll.erfolgreich is False
    assert "Programmierfehler" in protokoll.fehler


# ---------------------------------------------------------------------------
# Cache: unveränderte/irrelevante Funde sollen keinen erneuten API-Aufruf
# auslösen (siehe FinderFund in models.py).
# ---------------------------------------------------------------------------


def test_unveraenderter_fund_wird_beim_zweiten_lauf_nicht_erneut_an_die_api_geschickt(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "immer derselbe Text")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    aufrufe_nach_erstem_lauf = client.aufrufe
    assert aufrufe_nach_erstem_lauf == 2  # Themen-Check + Struktur-Extraktion

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == aufrufe_nach_erstem_lauf  # keine weiteren API-Aufrufe
    assert zaehler["aus_cache"] == 1
    assert db.query(DealVorschlag).count() == 2  # unverändert - kein neuer Datensatz


def test_irrelevanter_fund_wird_nie_wieder_an_die_api_geschickt(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/versicherung", "t", "Autoversicherung wechseln")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(RelevanzErgebnis(ist_relevant=False), None)

    lauf.taeglicher_lauf(db, client=client)
    assert client.aufrufe == 1  # nur der Themen-Check, keine Extraktion

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == 1  # beim zweiten Lauf gar kein API-Aufruf mehr
    assert zaehler["aus_cache"] == 1
    assert db.query(DealVorschlag).count() == 0


def test_geaenderter_rohtext_loest_erneuten_api_aufruf_aus(db, zwei_inhaber, monkeypatch):
    """Wird derselbe Beitrag bearbeitet (z.B. höhere Prämie), muss trotz
    gleicher URL neu geprüft werden."""
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    fund_v1 = RohFund("mydealz", "https://mydealz.de/c24", "t", "125 Euro Praemie")
    _patch_quellen(monkeypatch, [fund_v1])
    lauf.taeglicher_lauf(db, client=client)
    assert client.aufrufe == 2

    fund_v2 = RohFund("mydealz", "https://mydealz.de/c24", "t", "jetzt 150 Euro Praemie")
    _patch_quellen(monkeypatch, [fund_v2])
    lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == 4  # erneuter Themen-Check + Extraktion


def test_kaputter_cache_eintrag_wird_neu_extrahiert_statt_den_lauf_abzubrechen(db, zwei_inhaber, monkeypatch):
    from praemien_tracker.models import FinderFund

    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "125 Euro Praemie")
    _patch_quellen(monkeypatch, [fund])
    db.add(
        FinderFund(
            quelle="mydealz",
            quelle_url=fund.quelle_url,
            rohtext_hash=lauf._rohtext_hash(fund.text),
            ist_relevant=True,
            extraktion_json="das ist kein gueltiges AngebotExtraktion-JSON",
        )
    )
    db.commit()

    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    # Ein kaputter Cache-Eintrag wird wie ein Cache-Miss behandelt: kompletter
    # Themen-Check + Extraktion, statt den Lauf abzubrechen.
    assert client.aufrufe == 2
    assert zaehler["gefunden"] == 2


def test_sperrfrist_wird_trotz_cache_treffer_neu_bewertet(db, zwei_inhaber, monkeypatch):
    """Kernanliegen: das Matching muss weiterlaufen, auch wenn dank Cache
    kein API-Aufruf mehr nötig ist - sonst würde eine inzwischen erreichte
    Sperrfrist nie sichtbar."""
    from praemien_tracker.models import Bank, Deal

    Alice = zwei_inhaber[0]
    santander = Bank(name="Santander")
    db.add(santander)
    db.commit()
    # Kündigung vor 11 Monaten - Sperrfrist von 12 Monaten noch nicht erreicht.
    heute = datetime.date.today().replace(day=1)
    jahr, monat = heute.year, heute.month - 11
    while monat <= 0:
        monat += 12
        jahr -= 1
    db.add(
        Deal(
            bank=santander,
            inhaber=Alice,
            kontoart="Girokonto",
            gekuendigt=True,
            gekuendigt_im_monat=f"{jahr:04d}-{monat:02d}",
        )
    )
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/santander", "t", "Santander 100 Euro")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=12, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    eintrag = db.query(DealVorschlag).filter(DealVorschlag.inhaber_id == Alice.id).one()
    assert eintrag.status == matching.STATUS_ABGELEHNT

    # Zeit vergeht: Kündigung liegt jetzt 13 statt 11 Monate zurück -
    # Sperrfrist erreicht. Rohtext bleibt gleich, also kein neuer API-Aufruf.
    eintrag_deal = db.query(Deal).filter(Deal.bank_id == santander.id).one()
    jahr2, monat2 = heute.year, heute.month - 13
    while monat2 <= 0:
        monat2 += 12
        jahr2 -= 1
    eintrag_deal.gekuendigt_im_monat = f"{jahr2:04d}-{monat2:02d}"
    db.commit()

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == 2  # weiterhin nur der allererste Themen-Check + Extraktion
    assert zaehler["aktualisiert"] >= 1
    db.refresh(eintrag)
    assert eintrag.status == matching.STATUS_VORGESCHLAGEN
    # Immer noch nur eine Zeile je Inhaber, kein Duplikat.
    assert db.query(DealVorschlag).filter(DealVorschlag.inhaber_id == Alice.id).count() == 1


def test_status_wird_nicht_fuer_bereits_entschiedene_vorschlaege_ueberschrieben(db, zwei_inhaber, monkeypatch):
    """Ein vom Nutzer übernommener oder verworfener Vorschlag darf durch eine
    erneute Bewertung nicht wieder verändert werden."""
    fund = RohFund("mydealz", "https://mydealz.de/klein", "t", "5 Euro Praemie")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Klein-Bank", kontoart="Girokonto", praemie_betrag=5.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    eintrag = db.query(DealVorschlag).first()
    eintrag.status = matching.STATUS_VERWORFEN
    db.commit()

    lauf.taeglicher_lauf(db, client=client)

    db.refresh(eintrag)
    assert eintrag.status == matching.STATUS_VERWORFEN
