"""MCP-Server (mcp_server.py): nur lesend, Schlüssel-geschützt, ohne
persönliche Daten wie Kontonummer, Anschrift oder IBAN."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from praemien_tracker import mcp_server
from praemien_tracker.main import app  # noqa: F401  (registriert u. a. das Änderungsprotokoll)
from praemien_tracker.models import ART_KONTO, Bank, Bedingung, Deal, DealVorschlag, Inhaber, Praemie

TOKEN = "geheimer-test-schluessel-123"
KOPF = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture()
def daten(db):
    max_ = Inhaber(name="Max", strasse="Geheimweg 1", plz="12345", ort="Geheimstadt", iban="DE02120300000000202051")
    db.add(max_)
    deal = Deal(
        kontoart="Girokonto",
        kontonummer="DE89370400440532013000",
        bank=Bank(name="Prämienbank"),
        inhaber=max_,
        kontofuehrungsgebuehren=Decimal("0"),
    )
    deal.praemien.append(Praemie(quelle="bank", betrag=Decimal("150"), erhalten=False))
    deal.bedingungen.append(Bedingung(beschreibung="3 Kartenzahlungen", erfuellt=False))
    konto = Deal(
        art=ART_KONTO,
        kontoart="Tagesgeld",
        bank=Bank(name="Altbank"),
        inhaber=max_,
        gekuendigt=True,
        gekuendigt_im_monat="2026-01",
    )
    db.add_all([deal, konto])
    db.flush()
    db.add(
        DealVorschlag(
            inhaber_id=max_.id,
            quelle="mydealz",
            quelle_url="https://mydealz.de/x",
            bank_name="Neubank",
            kontoart="Depot",
            praemie_betrag=Decimal("0"),
            praemie_art="sachpraemie",
            praemie_bis=Decimal("100"),
            praemie_beschreibung="Gratisaktie bis 100 €",
            roh_json="{}",
            inhalt_hash="h",
            status="zu_pruefen",
            ablehnungsgruende="Prämie schwankt: Gratisaktie bis 100 €",
        )
    )
    db.commit()
    # Änderung, die im Protokoll landet - samt Kontonummer.
    deal.kontonummer = "DE11111111111111111111"
    db.commit()
    return {"deal": deal, "konto": konto, "inhaber": max_}


# --- Abfragen --------------------------------------------------------------


def test_uebersicht(db, daten):
    u = mcp_server.uebersicht_abfragen(db)
    assert u["praemien_gesamt"] == {"gesamt": 150.0, "erhalten": 0.0, "offen": 150.0}
    assert u["anzahl_deals"] == 1 and u["anzahl_konten_ohne_praemie"] == 1
    assert u["je_status"] == {"Bedingungen": 1, "Bestätigung warten": 1}
    assert u["vorschlaege_je_status"] == {"zu_pruefen": 1}
    assert u["offene_todos_je_kategorie"]["Bedingungen"]["anzahl"] == 1


def test_deals_suchen_filtert(db, daten):
    assert mcp_server.deals_suchen_abfragen(db, None, None, None, None)["anzahl"] == 2
    nur_konten = mcp_server.deals_suchen_abfragen(db, None, None, "konto", None)["deals"]
    assert [d["bank"] for d in nur_konten] == ["Altbank"]
    # Status als Code oder als angezeigter Name.
    assert mcp_server.deals_suchen_abfragen(db, ["bedingungen"], None, None, None)["anzahl"] == 1
    assert mcp_server.deals_suchen_abfragen(db, ["Bestätigung warten"], None, None, None)["anzahl"] == 1
    assert mcp_server.deals_suchen_abfragen(db, None, None, None, "prämien")["anzahl"] == 1


def test_deal_details_ohne_kontonummer(db, daten):
    d = mcp_server.deal_details_abfragen(db, daten["deal"].id)
    assert d["kontonummer_hinterlegt"] is True
    assert "DE11111111111111111111" not in json.dumps(d)
    assert d["praemien_einzeln"][0]["betrag"] == 150.0
    assert d["bedingungen"][0]["beschreibung"] == "3 Kartenzahlungen"
    assert mcp_server.deal_details_abfragen(db, 999999) == {"fehler": "Deal 999999 existiert nicht."}


def test_todos_und_sperrfristen(db, daten):
    t = mcp_server.todos_abfragen(db, "bestätigung", False)
    assert [x["deal_id"] for x in t["todos"]] == [daten["konto"].id]
    s = mcp_server.sperrfristen_abfragen(db)
    assert [z["bezeichnung"] for z in s["kuendigungen"]] == ["Altbank · Tagesgeld · Max"]


def test_statistiken(db, daten):
    s = mcp_server.statistiken_abfragen(db)
    assert s["pipeline"]["Bedingungen"] == 1
    assert s["je_inhaber"][0]["inhaber"] == "Max"


def test_vorschlaege_mit_sachpraemie(db, daten):
    v = mcp_server.vorschlaege_abfragen(db, ["zu_pruefen"], None, None, 50)["vorschlaege"][0]
    assert v["praemie_bis"] == 100.0 and v["praemie_art"] == "sachpraemie"
    assert v["ablehnungs_oder_pruefgruende"] == ["Prämie schwankt: Gratisaktie bis 100 €"]
    assert mcp_server.vorschlaege_abfragen(db, ["verworfen"], None, None, 50)["anzahl_gesamt"] == 0


def test_inhaber_ohne_persoenliche_angaben(db, daten):
    text = json.dumps(mcp_server.inhaber_abfragen(db))
    for geheim in ("Geheimweg", "12345", "Geheimstadt", "DE0212"):
        assert geheim not in text
    assert '"iban_hinterlegt": true' in text


def test_protokoll_verdeckt_kontonummer(db, daten):
    eintraege = mcp_server.protokoll_abfragen(db, daten["deal"].id, 50)["eintraege"]
    kontonummer = [e for e in eintraege if e["feld"] == "kontonummer"]
    assert kontonummer and kontonummer[0]["neuer_wert"] == "(verdeckt)"
    assert "DE11111111111111111111" not in json.dumps(eintraege)


# --- Zugriff über HTTP -----------------------------------------------------


class _Antwort:
    """Antwort als Event-Stream ("data: {...}") - .json() liest die
    JSON-RPC-Nachricht daraus."""

    def __init__(self, response):
        self.status_code = response.status_code
        self.text = response.text

    def json(self):
        for zeile in self.text.splitlines():
            if zeile.startswith("data:"):
                return json.loads(zeile[5:])
        return json.loads(self.text)


def _rpc(client, methode, params=None, kopf=KOPF, nr=1):
    return _Antwort(
        client.post("/mcp", headers=kopf, json={"jsonrpc": "2.0", "id": nr, "method": methode, "params": params or {}})
    )


def test_ohne_schluessel_kein_zugriff(db, daten):
    with TestClient(mcp_server.asgi_app(TOKEN)) as client:
        assert _rpc(client, "tools/list").status_code == 401
        falsch = {**KOPF, "Authorization": "Bearer falscher-schluessel-0000"}
        assert _rpc(client, "tools/list", kopf=falsch).status_code == 401


def test_mcp_ueber_http_nur_lesende_werkzeuge(db, daten):
    kopf = {**KOPF, "Authorization": f"Bearer {TOKEN}"}
    with TestClient(mcp_server.asgi_app(TOKEN)) as client:
        init = _rpc(
            client,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
            kopf=kopf,
        )
        assert init.status_code == 200, init.text
        assert init.json()["result"]["serverInfo"]["name"] == "Prämien-Tracker"

        werkzeuge = _rpc(client, "tools/list", kopf=kopf, nr=2).json()["result"]["tools"]
        namen = {w["name"] for w in werkzeuge}
        assert namen == {
            "uebersicht", "deals_suchen", "deal_details", "todos", "sperrfristen", "statistiken",
            "vorschlaege", "inhaber", "kuendigung_infos", "aenderungsprotokoll", "finder_laeufe",
        }
        assert all(w["annotations"]["readOnlyHint"] is True for w in werkzeuge)

        aufruf = _rpc(client, "tools/call", {"name": "uebersicht", "arguments": {}}, kopf=kopf, nr=3).json()
        inhalt = aufruf["result"]
        assert not inhalt.get("isError"), inhalt
        ergebnis = inhalt.get("structuredContent") or json.loads(inhalt["content"][0]["text"])
        assert ergebnis["anzahl_deals"] == 1


def test_schluessel_mindestlaenge():
    assert not mcp_server.token_ok("")
    assert not mcp_server.token_ok("kurz")
    assert mcp_server.token_ok("x" * mcp_server.MINDESTLAENGE_TOKEN)


def test_server_laesst_das_logging_der_oberflaeche_in_ruhe():
    """uvicorn.Config richtet sonst das Logging prozessweit neu ein - mit
    log_level="warning" verschwanden Start-, Stopp- und Zugriffszeilen der
    Oberfläche aus dem Add-on-Log."""
    import logging

    vorher = {name: logging.getLogger(name).level for name in ("uvicorn", "uvicorn.error", "uvicorn.access")}
    mcp_server.server_erstellen(TOKEN, 8099)
    nachher = {name: logging.getLogger(name).level for name in vorher}
    assert nachher == vorher
