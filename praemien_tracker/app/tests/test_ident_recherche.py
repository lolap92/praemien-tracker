"""Identifikationsverfahren (eID/Video/Post): Extraktion aus dem Angebot,
Websuche je Bank mit Cache, Etikett auf der Vorschlagskarte. Kein Netzwerk,
der Anthropic-Client wird gefaked."""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from praemien_tracker import ident_recherche
from praemien_tracker.finder import lauf, matching
from praemien_tracker.finder.extraktion import EXTRAKTION_PROMPT, AngebotExtraktion
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.models import DealVorschlag, IdentRecherche, Inhaber


class _FakeMessages:
    def __init__(self, parsed_output=None, fehler: Exception | None = None):
        self.parsed_output = parsed_output
        self.fehler = fehler
        self.banken: list[str] = []

    def parse(self, *, messages, **kwargs):
        self.banken.append(messages[0]["content"])
        if self.fehler:
            raise self.fehler
        return SimpleNamespace(parsed_output=self.parsed_output)


class _FakeClient:
    def __init__(self, **kw):
        self.messages = _FakeMessages(**kw)


def _ergebnis(*verfahren, gefunden=True):
    return ident_recherche._IdentErgebnis(gefunden=gefunden, verfahren=list(verfahren), quelle_url="https://bank.example/ident")


def _vorschlag(db, bank: str, status: str = matching.STATUS_VORGESCHLAGEN, **kw) -> DealVorschlag:
    inhaber = db.query(Inhaber).first() or Inhaber(name="Alice")
    v = DealVorschlag(
        inhaber=inhaber,
        quelle="mydealz",
        quelle_url=f"https://mydealz.de/{bank}-{status}",
        bank_name=bank,
        kontoart="Girokonto",
        praemie_betrag=Decimal("100"),
        roh_json="{}",
        inhalt_hash=f"h-{bank}-{status}",
        status=status,
        **kw,
    )
    db.add(v)
    db.commit()
    return v


# --- Extraktion / Matching ----------------------------------------------------


def test_prompt_fragt_identifikation_ab():
    assert "identifikation" in EXTRAKTION_PROMPT


def test_alte_cache_eintraege_ohne_feld_sind_unbekannt():
    ext = AngebotExtraktion.model_validate({"bank_name": "B", "kontoart": "Girokonto", "praemie_betrag": 50, "bedingungen": []})
    assert ext.identifikation == []


def test_identifikation_aus_angebot_landet_normalisiert_im_match(db):
    alice = Inhaber(name="Alice")
    db.add(alice)
    db.commit()
    ext = AngebotExtraktion(
        bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, identifikation=["video", "eid", "video"], bedingungen=[]
    )
    match = matching.bewerten(db, RohFund("mydealz", "https://x", "t", "x"), ext, alice, Decimal("50"))
    assert match.identifikation == "eid,video"
    assert match.status == matching.STATUS_VORGESCHLAGEN


def test_identifikation_aendert_weder_status_noch_hash(db):
    alice = Inhaber(name="Alice")
    db.add(alice)
    db.commit()
    fund = RohFund("mydealz", "https://x", "t", "x")
    basis = dict(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[])
    ohne = matching.bewerten(db, fund, AngebotExtraktion(**basis), alice, Decimal("50"))
    nur_video = matching.bewerten(db, fund, AngebotExtraktion(**basis, identifikation=["video"]), alice, Decimal("50"))
    assert ohne.status == nur_video.status == matching.STATUS_VORGESCHLAGEN
    assert ohne.inhalt_hash == nur_video.inhalt_hash


def test_etikett():
    assert matching.ident_einordnung(None) is None
    assert matching.ident_einordnung("") is None
    eid = matching.ident_einordnung("eid,video", "recherche")
    assert (eid.klasse, eid.label) == ("eid", "eID möglich")
    assert "Websuche" in eid.titel
    ohne = matching.ident_einordnung("video,post", "angebot")
    assert ohne.klasse == "ohne-eid"
    assert ohne.label == "Ohne eID: VideoIdent / PostIdent"
    assert "laut Angebot" in ohne.titel


# --- Websuche je Bank -----------------------------------------------------------


def test_ohne_api_key_passiert_nichts(db, monkeypatch):
    monkeypatch.setattr(ident_recherche, "anthropic_client", lambda: None)
    v = _vorschlag(db, "Testbank")
    assert ident_recherche.offene_vorschlaege_nachtragen(db) == 0
    assert v.identifikation is None
    assert db.query(IdentRecherche).count() == 0


def test_recherche_fuellt_vorschlaege_und_cacht_je_bank(db):
    client = _FakeClient(parsed_output=_ergebnis("video", "eid"))
    a = _vorschlag(db, "Testbank")
    b = _vorschlag(db, "TESTBANK", status=matching.STATUS_ZU_PRUEFEN)

    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 1
    assert len(client.messages.banken) == 1  # gleiche Bank, nur ein Aufruf
    for v in (a, b):
        assert v.identifikation == "eid,video"
        assert v.identifikation_quelle == ident_recherche.QUELLE_RECHERCHE
    eintrag = db.query(IdentRecherche).one()
    assert eintrag.quelle_url == "https://bank.example/ident"

    # Neuer Vorschlag derselben Bank: aus dem Cache, ohne API-Aufruf.
    c = _vorschlag(db, "Test Bank", status=matching.STATUS_ABGELEHNT)
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 0
    assert len(client.messages.banken) == 1
    assert c.identifikation == "eid,video"


def test_angabe_im_angebot_hat_vorrang(db):
    client = _FakeClient(parsed_output=_ergebnis("eid"))
    v = _vorschlag(db, "Testbank", identifikation="video", identifikation_quelle="angebot")
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 0
    assert client.messages.banken == []
    assert v.identifikation == "video"


def test_entschiedene_vorschlaege_werden_nicht_recherchiert(db):
    client = _FakeClient(parsed_output=_ergebnis("eid"))
    _vorschlag(db, "Testbank", status=matching.STATUS_VERWORFEN)
    _vorschlag(db, "Andere", status=matching.STATUS_UEBERNOMMEN)
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 0
    assert client.messages.banken == []


def test_nichts_gefunden_bleibt_unbekannt_und_wird_gecacht(db):
    client = _FakeClient(parsed_output=_ergebnis(gefunden=False))
    v = _vorschlag(db, "Testbank")
    ident_recherche.offene_vorschlaege_nachtragen(db, client=client)
    ident_recherche.offene_vorschlaege_nachtragen(db, client=client)
    assert len(client.messages.banken) == 1
    assert v.identifikation is None
    assert db.query(IdentRecherche).one().fehlgeschlagen is False


def test_fehlschlag_wird_nach_einer_woche_wiederholt_und_behaelt_alten_treffer(db):
    _vorschlag(db, "Testbank")
    alt = datetime.datetime.utcnow() - datetime.timedelta(days=200)
    db.add(IdentRecherche(bank_schluessel="testbank", bank_name="Testbank", verfahren="eid", recherchiert_am=alt))
    db.commit()

    client = _FakeClient(fehler=RuntimeError("API weg"))
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 1
    eintrag = db.query(IdentRecherche).one()
    assert eintrag.fehlgeschlagen is True
    assert eintrag.verfahren == "eid"  # alter Treffer bleibt

    # Innerhalb einer Woche kein neuer Versuch.
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 0


def test_hoechstens_zehn_recherchen_je_lauf(db):
    client = _FakeClient(parsed_output=_ergebnis("eid"))
    for i in range(12):
        _vorschlag(db, f"Bank{i}")
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 10
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 2


def test_demo_modus_recherchiert_nicht(db, monkeypatch):
    monkeypatch.setattr(ident_recherche.config, "DEMO_MODUS", True)
    client = _FakeClient(parsed_output=_ergebnis("eid"))
    _vorschlag(db, "Testbank")
    assert ident_recherche.offene_vorschlaege_nachtragen(db, client=client) == 0


# --- Zusammenspiel mit dem Lauf --------------------------------------------------


def test_neuanalyse_ohne_angabe_behaelt_recherchierten_wert(db):
    v = _vorschlag(db, "Testbank", identifikation="eid", identifikation_quelle="recherche")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    match = matching.bewerten(db, RohFund("mydealz", v.quelle_url, "t", "x"), ext, v.inhaber, Decimal("50"))
    lauf._vorschlag_felder_setzen(v, ext, match)
    assert (v.identifikation, v.identifikation_quelle) == ("eid", "recherche")


def test_neuanalyse_ohne_angabe_leert_frueheren_angebotswert(db):
    v = _vorschlag(db, "Testbank", identifikation="video", identifikation_quelle="angebot")
    ext = AngebotExtraktion(bank_name="Testbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    match = matching.bewerten(db, RohFund("mydealz", v.quelle_url, "t", "x"), ext, v.inhaber, Decimal("50"))
    lauf._vorschlag_felder_setzen(v, ext, match)
    assert v.identifikation is None and v.identifikation_quelle is None


def test_fehler_der_recherche_bricht_den_lauf_nicht_ab(db, monkeypatch):
    def kaputt(db, **kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(ident_recherche, "offene_vorschlaege_nachtragen", kaputt)
    lauf._ident_nachtragen(db)  # darf nicht werfen
