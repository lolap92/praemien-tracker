"""MCP-Server (mcp_server.py): nur lesend, Schlüssel-geschützt. Persönliche
Daten wie Kontonummer, Anschrift oder IBAN nur über die Kündigungs-Werkzeuge."""

from __future__ import annotations

import datetime
import io
import json
from decimal import Decimal

import pytest
from pypdf import PdfReader
from starlette.testclient import TestClient

from formular_hilfen import STANDARD_FORMULAR, formular_pdf

from praemien_tracker import kuendigung_formular as kf
from praemien_tracker import mcp_server
from praemien_tracker.main import app  # noqa: F401  (registriert u. a. das Änderungsprotokoll)
from praemien_tracker.models import (
    ART_KONTO,
    Bank,
    Bedingung,
    Deal,
    DealVorschlag,
    Inhaber,
    Kuendigungsschreiben,
    Praemie,
)

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


def test_deal_details_nennt_schreiben_ohne_text(db, daten):
    db.add(
        Kuendigungsschreiben(
            deal_id=daten["konto"].id, kanal="brief", absender="Max Muster", datum=datetime.date(2026, 1, 5),
            betreff="Kündigung", text="IBAN DE02 1203 0000 0000 2020 51", name="Max Muster",
        )
    )
    db.commit()
    d = mcp_server.deal_details_abfragen(db, daten["konto"].id)
    assert d["kuendigungsschreiben"][0]["id"] and "DE02" not in json.dumps(d)


def test_kuendigung_daten_unvollstaendig(db, daten):
    k = mcp_server.kuendigung_daten_abfragen(db, daten["deal"].id)
    werte = {a["schluessel"]: a["wert"] for a in k["angaben"]}
    # Persönliche Angaben im Klartext - die braucht das Schreiben.
    assert werte["strasse"] == "Geheimweg 1" and werte["kontonummer"] == "DE11111111111111111111"
    assert werte["iban"].replace(" ", "") == "DE02120300000000202051"
    assert k["iban_gueltig"] is True
    # Ohne vollen Namen kein Entwurf, nur die Rückfrage.
    assert k["entwurf"] is None and k["fehlende_angaben"]
    assert mcp_server.kuendigung_daten_abfragen(db, 999999) == {"fehler": "Deal 999999 existiert nicht."}


def test_kuendigung_daten_mit_entwurf(db, daten):
    daten["inhaber"].voller_name = "Max Muster"
    db.commit()
    k = mcp_server.kuendigung_daten_abfragen(db, daten["deal"].id)
    assert k["fehlende_angaben"] == []
    assert "DE11111111111111111111" in k["entwurf"]["betreff"] + k["entwurf"]["text"]
    assert k["entwurf"]["name"] == "Max Muster"
    assert "Geheimweg 1" in k["entwurf"]["absender"]


def test_kuendigungsschreiben_im_wortlaut(db, daten):
    for versendet in (datetime.date(2026, 1, 6), None):
        db.add(
            Kuendigungsschreiben(
                deal_id=daten["konto"].id, kanal="email", empfaenger="kuendigung@altbank.de",
                absender="Max Muster\nGeheimweg 1", datum=datetime.date(2026, 1, 5), betreff="Kündigung Tagesgeld",
                text="Restguthaben bitte auf DE02 1203 0000 0000 2020 51", name="Max Muster", versendet_am=versendet,
            )
        )
    db.commit()
    alle = mcp_server.kuendigungsschreiben_abfragen(db, None, False)
    assert alle["anzahl"] == 2
    assert "DE02 1203" in alle["schreiben"][0]["text"]
    assert alle["schreiben"][0]["deal"] == "Altbank · Tagesgeld · Max"
    entwuerfe = mcp_server.kuendigungsschreiben_abfragen(db, daten["konto"].id, True)["schreiben"]
    assert len(entwuerfe) == 1 and entwuerfe[0]["entwurf"] is True
    assert mcp_server.kuendigungsschreiben_abfragen(db, daten["deal"].id, False)["anzahl"] == 0
    assert len(mcp_server.kuendigung_daten_abfragen(db, daten["konto"].id)["gespeicherte_schreiben"]) == 2


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
            "vorschlaege", "inhaber", "kuendigung_infos", "kuendigung_daten", "kuendigungsformular",
            "kuendigungsschreiben",
            "aenderungsprotokoll", "finder_laeufe",
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


# --- Kündigungsdateien -------------------------------------------------------


@pytest.fixture()
def formular(db, daten):
    daten["inhaber"].voller_name = "Max Muster"
    pdf = formular_pdf(STANDARD_FORMULAR)
    kf.speichern(db, daten["deal"], pdf, "hochgeladen: k.pdf", None)
    db.commit()
    return pdf


def _felder(inhalt: bytes) -> dict:
    return {k: v.get("/V") for k, v in PdfReader(io.BytesIO(inhalt)).get_fields().items()}


def test_kuendigungsformular_mit_feldern(db, daten, formular):
    f = mcp_server.kuendigungsformular_abfragen(db, daten["deal"].id)
    felder = {x["name"]: x for x in f["felder"]}
    assert felder["IBAN"]["wert"] == "DE02120300000000202051"
    assert felder["Grund"]["optionen"] == ["Umzug", "Sonstiges"]
    assert f["downloads"]["ausgefuellt"] == f"/dateien/formular/{daten['deal'].id}/ausgefuellt.pdf"
    assert mcp_server.kuendigungsformular_abfragen(db, daten["konto"].id)["fehler"].startswith("Für Altbank")
    assert mcp_server.kuendigung_daten_abfragen(db, daten["deal"].id)["bankformular"]["downloads"]


def test_formular_downloads(db, daten, formular):
    kopf = {"Authorization": f"Bearer {TOKEN}"}
    basis = f"/dateien/formular/{daten['deal'].id}"
    with TestClient(mcp_server.asgi_app(TOKEN)) as client:
        assert client.get(f"{basis}/leer.pdf").status_code == 401
        assert client.get(f"{basis}/leer.pdf", headers=kopf).content == formular

        app_werte = client.get(f"{basis}/ausgefuellt.pdf", headers=kopf)
        assert app_werte.headers["content-type"] == "application/pdf"
        assert _felder(app_werte.content)["IBAN"] == "DE02120300000000202051"

        eigene = client.post(f"{basis}/ausgefuellt.pdf", headers=kopf, json={"Kundennummer": "K-9", "Restguthaben": "an"})
        werte = _felder(eigene.content)
        assert werte["Kundennummer"] == "K-9" and werte["Restguthaben"] == "/Ja"
        assert werte["Feld2"] == "Muster"  # nicht übergeben: Wert der App

        assert client.post(f"{basis}/ausgefuellt.pdf", headers=kopf, json={"Gibtsnicht": "x"}).status_code == 400
        assert client.post(f"{basis}/leer.pdf", headers=kopf, json={}).status_code == 405
        assert client.get(f"/dateien/formular/{daten['konto'].id}/leer.pdf", headers=kopf).status_code == 404
    # Nur Vorschau - nichts gespeichert.
    db.expire_all()
    assert db.query(Kuendigungsschreiben).count() == 0
    assert db.get(Deal, daten["deal"].id).kuendigung_formular_werte is None


def test_schreiben_downloads(db, daten):
    brief = Kuendigungsschreiben(
        deal_id=daten["konto"].id, kanal="brief", empfaenger="Altbank\nPostfach 1", absender="Max Muster",
        datum=datetime.date(2026, 1, 5), betreff="Kündigung Tagesgeld", text="Sehr geehrte Damen und Herren,", name="Max Muster",
    )
    ausgefuellt = Kuendigungsschreiben(
        deal_id=daten["deal"].id, kanal="formular", absender="Max Muster", datum=datetime.date(2026, 1, 5),
        betreff="Kündigungsformular", text="IBAN: DE02", name="Max Muster", datei=b"%PDF-1.4 ausgefuellt",
    )
    db.add_all([brief, ausgefuellt])
    db.commit()
    eintraege = {k["id"]: k for k in mcp_server.kuendigungsschreiben_abfragen(db, None, False)["schreiben"]}
    assert set(eintraege[brief.id]["downloads"]) == {"pdf", "docx"}
    assert set(eintraege[ausgefuellt.id]["downloads"]) == {"pdf"}
    kopf = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(mcp_server.asgi_app(TOKEN)) as client:
        assert client.get(f"/dateien/schreiben/{brief.id}.pdf").status_code == 401
        pdf = client.get(f"/dateien/schreiben/{brief.id}.pdf", headers=kopf)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        docx = client.get(f"/dateien/schreiben/{brief.id}.docx", headers=kopf)
        assert docx.status_code == 200 and docx.content.startswith(b"PK")
        assert client.get(f"/dateien/schreiben/{ausgefuellt.id}.pdf", headers=kopf).content == b"%PDF-1.4 ausgefuellt"
        assert client.get(f"/dateien/schreiben/{ausgefuellt.id}.docx", headers=kopf).status_code == 404
        assert client.get("/dateien/schreiben/999999.pdf", headers=kopf).status_code == 404
        assert client.get("/dateien/schreiben/x.exe", headers=kopf).status_code == 404


# --- Entwürfe speichern (Option mcp_entwuerfe_speichern) ----------------------


def _werkzeuge(entwuerfe_speichern: bool) -> dict:
    kopf = {**KOPF, "Authorization": f"Bearer {TOKEN}"}
    with TestClient(mcp_server.asgi_app(TOKEN, entwuerfe_speichern)) as client:
        _rpc(
            client,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
            kopf=kopf,
        )
        return {w["name"]: w for w in _rpc(client, "tools/list", kopf=kopf, nr=2).json()["result"]["tools"]}


def test_speicher_werkzeuge_nur_mit_option():
    aus = _werkzeuge(False)
    assert "kuendigungsbrief_speichern" not in aus and "kuendigungsformular_speichern" not in aus
    an = _werkzeuge(True)
    for name in ("kuendigungsbrief_speichern", "kuendigungsformular_speichern"):
        assert an[name]["annotations"]["readOnlyHint"] is False
    assert {n for n, w in an.items() if not w["annotations"]["readOnlyHint"]} == {
        "kuendigungsbrief_speichern", "kuendigungsformular_speichern",
    }


def test_brief_entwurf_aus_app_vorlage(db, daten):
    daten["inhaber"].voller_name = "Max Muster"
    daten["deal"].bank.anschrift = "Prämienbank AG\nPostfach 1\n10000 Berlin"
    db.commit()
    r = mcp_server.kuendigungsbrief_speichern_ausfuehren(db, daten["deal"].id, "brief", None, None)
    assert r["gespeichert"] is True
    s = db.query(Kuendigungsschreiben).one()
    assert s.kanal == "brief" and s.versendet_am is None
    assert "DE11111111111111111111" in s.betreff + s.text
    assert s.empfaenger.startswith("Prämienbank AG") and s.absender.startswith("Max Muster")
    # Nichts als gekündigt markiert.
    db.expire_all()
    assert db.get(Deal, daten["deal"].id).gekuendigt is False


def test_email_eigener_text_ersetzt_offenen_entwurf(db, daten):
    daten["inhaber"].voller_name = "Max Muster"
    db.commit()
    deal_id = daten["deal"].id
    mcp_server.kuendigungsbrief_speichern_ausfuehren(db, deal_id, "email", "Kündigung", "Sehr geehrte Damen und Herren,\n\nerste Fassung")
    r = mcp_server.kuendigungsbrief_speichern_ausfuehren(db, deal_id, "email", "Kündigung Girokonto", "Sehr geehrte Damen und Herren,\n\nzweite Fassung")
    alle = db.query(Kuendigungsschreiben).all()
    assert len(alle) == 1 and "zweite Fassung" in alle[0].text
    assert "Geheimweg 1" in alle[0].text  # Signatur mit Anschrift wie in der App
    assert r["schreiben"]["betreff"] == "Kündigung Girokonto"


def test_brief_ohne_angaben_wird_nicht_gespeichert(db, daten):
    r = mcp_server.kuendigungsbrief_speichern_ausfuehren(db, daten["deal"].id, "brief", None, None)
    assert "fehlt" in r["fehler"]
    # Mit eigenem Text, aber ohne vollen Namen und Bankanschrift: kein Brief.
    r = mcp_server.kuendigungsbrief_speichern_ausfuehren(db, daten["deal"].id, "brief", "Kündigung", "Text")
    assert "Postanschrift der Bank" in r["fehler"]
    assert mcp_server.kuendigungsbrief_speichern_ausfuehren(db, daten["deal"].id, "fax", "a", "b")["fehler"]
    assert mcp_server.kuendigungsbrief_speichern_ausfuehren(db, 999999, "email", "a", "b")["fehler"]
    assert db.query(Kuendigungsschreiben).count() == 0


def test_formular_entwurf_speichert_pdf_und_eigene_werte(db, daten, formular):
    deal_id = daten["deal"].id
    r = mcp_server.kuendigungsformular_speichern_ausfuehren(
        db, deal_id, {"Kundennummer": "K-9", "Restguthaben": "an", "Feld2": "Muster"}
    )
    assert r["gespeichert"] is True
    s = db.query(Kuendigungsschreiben).one()
    assert s.kanal == "formular" and s.versendet_am is None
    werte = _felder(s.datei)
    assert werte["Kundennummer"] == "K-9" and werte["Restguthaben"] == "/Ja"
    assert werte["IBAN"] == "DE02120300000000202051"
    assert "Kundennummer: K-9" in s.text
    db.expire_all()
    deal = db.get(Deal, deal_id)
    # Feld2 entspricht dem Vorschlag - kein eigener Wert, folgt also Änderungen.
    assert json.loads(deal.kuendigung_formular_werte) == {"Kundennummer": "K-9", "Restguthaben": "an"}
    assert deal.gekuendigt is False


def test_formular_entwurf_unbekanntes_feld(db, daten, formular):
    r = mcp_server.kuendigungsformular_speichern_ausfuehren(db, daten["deal"].id, {"Gibtsnicht": "x"})
    assert r["fehler"] == "Unbekannte Felder: Gibtsnicht"
    assert db.query(Kuendigungsschreiben).count() == 0
    assert mcp_server.kuendigungsformular_speichern_ausfuehren(db, daten["konto"].id, None)["fehler"]


def test_formular_entwurf_ueber_http(db, daten, formular):
    kopf = {**KOPF, "Authorization": f"Bearer {TOKEN}"}
    with TestClient(mcp_server.asgi_app(TOKEN, True)) as client:
        _rpc(
            client,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
            kopf=kopf,
        )
        aufruf = _rpc(
            client,
            "tools/call",
            {"name": "kuendigungsformular_speichern", "arguments": {"deal_id": daten["deal"].id, "werte": {"Kundennummer": "K-1"}}},
            kopf=kopf,
            nr=3,
        ).json()["result"]
        assert not aufruf.get("isError"), aufruf
    db.expire_all()
    assert db.query(Kuendigungsschreiben).one().kanal == "formular"
