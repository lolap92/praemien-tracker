"""Bankformulare im Kündigungs-Assistenten (kuendigung_formular.py) - mit
einem selbst gebauten AcroForm-PDF (formular_hilfen.py), ohne Netzwerk und
mit gefaktem Anthropic-Client."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from praemien_tracker import config
from praemien_tracker import kuendigung_dokumente as kd
from praemien_tracker import kuendigung_formular as kf
from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber, KuendigungFormular, Kuendigungsschreiben

from formular_hilfen import STANDARD_FORMULAR, formular_pdf

client = TestClient(app)


@pytest.fixture()
def deal(db):
    eintrag = Deal(
        kontoart="Depot",
        kontonummer="4711",
        bank=Bank(name="Testbank", anschrift="Testbank AG\nPostfach 1\n10000 Berlin"),
        inhaber=Inhaber(
            name="Max",
            voller_name="Max Mustermann",
            strasse="Musterweg 1",
            plz="12345",
            ort="Musterstadt",
            iban="DE89370400440532013000",
        ),
    )
    db.add(eintrag)
    db.commit()
    return eintrag


@pytest.fixture(autouse=True)
def ohne_ki(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(config, "DEMO_MODUS", False)


def _hochladen(deal, pdf: bytes, dateiname: str = "kuendigung.pdf"):
    return client.post(
        f"/deals/{deal.id}/kuendigung/formular/hochladen",
        files={"datei": (dateiname, pdf, "application/pdf")},
        follow_redirects=False,
    )


def _ausgefuellt(inhalt: bytes) -> dict:
    return {k: v.get("/V") for k, v in PdfReader(io.BytesIO(inhalt)).get_fields().items()}


# ---------- Einlesen und Zuordnung ----------


def test_einlesen_erkennt_feldtypen_und_ueberspringt_schreibgeschuetzte():
    felder, hinweis = kf.einlesen(formular_pdf(STANDARD_FORMULAR))

    assert hinweis is None
    nach_name = {f.name: f for f in felder}
    assert "Bearbeiter" not in nach_name
    assert nach_name["Feld1"].label == "Vorname"
    assert nach_name["IBAN"].max_len == 22
    assert (nach_name["Restguthaben"].typ, nach_name["Restguthaben"].optionen) == ("checkbox", ["Ja"])
    assert (nach_name["Grund"].typ, nach_name["Grund"].optionen) == ("radio", ["Umzug", "Sonstiges"])
    assert (nach_name["Kontoart"].typ, nach_name["Kontoart"].optionen) == ("auswahl", ["Girokonto", "Depot"])
    assert "Unterschrift.Datum" in nach_name


def test_pdf_ohne_felder_ist_nicht_ausfuellbar():
    brief = kd.Brief(["A"], ["B"], "Ort", "Betreff", ["Text"], "Name")
    felder, hinweis = kf.einlesen(kd.als_pdf(brief))
    assert felder == []
    assert "keine ausfüllbaren Felder" in hinweis


def test_kein_pdf_wird_abgelehnt():
    with pytest.raises(kf.FormularFehler):
        kf.einlesen(b"<html>Formularcenter</html>")


def test_stichwort_zuordnung():
    felder, _ = kf.einlesen(formular_pdf(STANDARD_FORMULAR))
    assert kf.stichwort_zuordnung(felder) == {
        "Feld1": "{vorname}",
        "Feld2": "{nachname}",
        "Strasse": "{strasse}",
        "PLZ": "{plz}",
        "Ort": "{ort}",
        "IBAN": "{iban}",
        "Kundennummer": "{kundennummer}",
        "Unterschrift.Datum": "{ort_datum}",
    }


def test_ki_zuordnung_wird_bereinigt_und_bekommt_keine_persoenlichen_daten(db, deal):
    felder, _ = kf.einlesen(formular_pdf(STANDARD_FORMULAR))
    antwort = kf._ZuordnungErgebnis(
        zuordnungen=[
            {"feld": "Feld1", "vorlage": "{vorname}"},
            {"feld": "Kundennummer", "vorlage": "{kunden_nr}"},
            {"feld": "Restguthaben", "vorlage": "An"},
            {"feld": "Grund", "vorlage": "Erfunden"},
            {"feld": "GibtsNicht", "vorlage": "{name}"},
        ],
        zusatzfelder=[{"schluessel": "kunden_nr", "label": "Kundennummer", "hinweis": "Im Postfach"}],
    )
    aufrufe = []

    def parse(**kwargs):
        aufrufe.append(kwargs)
        return SimpleNamespace(parsed_output=antwort)

    fake = SimpleNamespace(messages=SimpleNamespace(parse=parse))

    zuordnung, zusatz = kf.ki_zuordnung(fake, deal, felder, "Text des Formulars")

    assert zuordnung == {"Feld1": "{vorname}", "Kundennummer": "{kunden_nr}", "Restguthaben": "an"}
    assert zusatz == [{"schluessel": "kunden_nr", "label": "Kundennummer", "hinweis": "Im Postfach"}]
    prompt = aufrufe[0]["messages"][0]["content"]
    for geheim in ("Mustermann", "Musterweg", "DE89", "4711"):
        assert geheim not in prompt


# ---------- Hochladen und Ausfüllen ----------


def test_hochladen_zeigt_vorausgefuellte_felder(db, deal):
    antwort = _hochladen(deal, formular_pdf(STANDARD_FORMULAR))
    assert antwort.status_code == 303

    formular = db.query(KuendigungFormular).one()
    assert (formular.bank_name, formular.kontoart, formular.zuordnung_ki) == ("Testbank", "Depot", False)
    assert formular.quelle == "hochgeladen: kuendigung.pdf"

    seite = client.get(f"/deals/{deal.id}/kuendigung/formular").text
    assert 'value="Max"' in seite and 'value="Mustermann"' in seite
    # IBAN passt in Vierergruppen nicht in 22 Zeichen - also ohne Leerzeichen.
    assert 'value="DE89370400440532013000"' in seite
    assert "Kundennummer ⚠ offen" in seite
    assert "Formular ausfüllen" in client.get(f"/deals/{deal.id}/kuendigung").text


def test_ausfuellen_liefert_pdf_und_speichert_schreiben(db, deal):
    _hochladen(deal, formular_pdf(STANDARD_FORMULAR))

    antwort = client.post(
        f"/deals/{deal.id}/kuendigung/formular/angaben",
        data={
            "aktion": "ausfuellen",
            "zusatz_kundennummer": "K-77",
            "feld_Feld1": "Max",
            "feld_Restguthaben": kf.AN,
            "feld_Grund": "Umzug",
            "feld_Kontoart": "Depot",
        },
    )

    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "application/pdf"
    werte = _ausgefuellt(antwort.content)
    assert werte["Feld1"] == "Max"
    assert werte["Feld2"] == "Mustermann"
    assert werte["IBAN"] == "DE89370400440532013000"
    assert werte["Kundennummer"] == "K-77"
    assert werte["Restguthaben"] == "/Ja"
    assert werte["Grund"] == "/Umzug"
    assert werte["Kontoart"] == "Depot"
    assert werte["Unterschrift.Datum"].startswith("Musterstadt, ")

    schreiben = db.query(Kuendigungsschreiben).one()
    assert schreiben.kanal == "formular"
    assert schreiben.datei == antwort.content
    assert "Kundennummer: K-77" in schreiben.text
    # Erneut abrufbar und als versendet markierbar wie Brief und E-Mail.
    assert client.get(f"/deals/{deal.id}/kuendigung/schreiben/{schreiben.id}/pdf").content == antwort.content
    client.post(f"/deals/{deal.id}/kuendigung/schreiben/{schreiben.id}/versendet", data={"datum": "2026-10-01"})
    db.expire_all()
    assert db.get(Deal, deal.id).gekuendigt is True


def test_eigene_werte_nur_wenn_sie_vom_vorschlag_abweichen(db, deal):
    _hochladen(deal, formular_pdf(STANDARD_FORMULAR))

    client.post(
        f"/deals/{deal.id}/kuendigung/formular/angaben",
        data={"feld_Feld1": "Max", "feld_Feld2": "Mustermann-Berg", "feld_Ort": ""},
    )

    db.expire_all()
    deal = db.get(Deal, deal.id)
    # Feld1 entspricht dem Vorschlag und folgt weiter den Daten; ein bewusst
    # geleertes Feld ist dagegen eine eigene Angabe.
    assert json.loads(deal.kuendigung_formular_werte) == {"Feld2": "Mustermann-Berg", "Ort": ""}
    nach_name = {fw.feld.name: fw for fw in kf.feldwerte(db.query(KuendigungFormular).one(), deal)}
    assert nach_name["Feld2"].wert == "Mustermann-Berg" and nach_name["Feld2"].eigen
    assert nach_name["Ort"].wert == ""


def test_zusatzangabe_fuellt_das_gleichzeitig_leer_geschickte_feld(db, deal):
    """Genau so schickt der Browser es ab: Kundennummer oben eingetragen,
    das zugehörige Formularfeld darunter noch leer."""
    _hochladen(deal, formular_pdf(STANDARD_FORMULAR))

    antwort = client.post(
        f"/deals/{deal.id}/kuendigung/formular/angaben",
        data={"aktion": "ausfuellen", "zusatz_kundennummer": "K-77", "feld_Kundennummer": ""},
    )

    assert _ausgefuellt(antwort.content)["Kundennummer"] == "K-77"
    db.expire_all()
    assert db.get(Deal, deal.id).kuendigung_formular_werte is None


def test_gleiches_pdf_behaelt_zuordnung_neues_setzt_eigene_werte_zurueck(db, deal):
    pdf = formular_pdf(STANDARD_FORMULAR)
    _hochladen(deal, pdf)
    client.post(f"/deals/{deal.id}/kuendigung/formular/angaben", data={"feld_Feld2": "Anders"})
    formular = db.query(KuendigungFormular).one()
    formular.zuordnung = json.dumps({"Feld2": "{nachname}"})
    db.commit()

    _hochladen(deal, pdf, "nochmal.pdf")
    db.expire_all()
    assert json.loads(db.query(KuendigungFormular).one().zuordnung) == {"Feld2": "{nachname}"}
    assert db.get(Deal, deal.id).kuendigung_formular_werte is not None

    _hochladen(deal, formular_pdf(STANDARD_FORMULAR[:3]), "neu.pdf")
    db.expire_all()
    assert db.query(KuendigungFormular).count() == 1
    assert db.get(Deal, deal.id).kuendigung_formular_werte is None


def test_nicht_ausfuellbares_formular_zeigt_ausfuellhilfe(db, deal):
    brief = kd.Brief(["A"], ["B"], "Ort", "Betreff", ["Text"], "Name")
    _hochladen(deal, kd.als_pdf(brief))

    seite = client.get(f"/deals/{deal.id}/kuendigung/formular").text

    assert "keine ausfüllbaren Felder" in seite
    assert "Ausfüllhilfe" in seite
    assert "DE89 3704 0044 0532 0130 00" in seite
    assert "Ausgefülltes Formular herunterladen" not in seite


def test_hochladen_einer_falschen_datei(db, deal):
    antwort = _hochladen(deal, b"kein pdf", "bild.png")
    assert "meldung=" in antwort.headers["location"]
    assert db.query(KuendigungFormular).count() == 0


# ---------- Laden von der Bank ----------


def _mit_formular_url(db, deal, url: str) -> None:
    from praemien_tracker.models import KuendigungAnforderung

    db.add(
        KuendigungAnforderung(
            bank_name="Testbank", kontoart="Depot", kanal="formular", betreff_vorlage="B", text_vorlage="T", formular_url=url
        )
    )
    db.commit()


class _FakeStream:
    def __init__(self, inhalt: bytes):
        self.inhalt = inhalt

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self):
        yield self.inhalt


def test_laden_von_der_bank(db, deal, monkeypatch):
    _mit_formular_url(db, deal, "https://testbank.example/kuendigung.pdf")
    pdf = formular_pdf(STANDARD_FORMULAR)
    monkeypatch.setattr(kf.httpx, "stream", lambda *a, **k: _FakeStream(pdf))

    client.post(f"/deals/{deal.id}/kuendigung/formular/laden", follow_redirects=False)

    assert db.query(KuendigungFormular).one().quelle == "https://testbank.example/kuendigung.pdf"


def test_laden_einer_webseite_statt_pdf_erklaert_den_weg(db, deal, monkeypatch):
    _mit_formular_url(db, deal, "https://testbank.example/formulare")
    monkeypatch.setattr(kf.httpx, "stream", lambda *a, **k: _FakeStream(b"<!doctype html><html>"))

    antwort = client.post(f"/deals/{deal.id}/kuendigung/formular/laden", follow_redirects=True)

    assert "hier hochladen" in antwort.text
    assert db.query(KuendigungFormular).count() == 0


def test_laden_nur_per_https_und_nie_im_demo_modus(db, deal, monkeypatch):
    with pytest.raises(kf.FormularFehler):
        kf.von_url_laden("http://192.168.1.10/formular.pdf")

    _mit_formular_url(db, deal, "https://testbank.example/kuendigung.pdf")
    monkeypatch.setattr(config, "DEMO_MODUS", True)
    aufrufe = []
    monkeypatch.setattr(kf.httpx, "stream", lambda *a, **k: aufrufe.append(a))
    client.post(f"/deals/{deal.id}/kuendigung/formular/laden")
    assert aufrufe == []


def test_formular_entfernen(db, deal):
    _hochladen(deal, formular_pdf(STANDARD_FORMULAR))
    client.post(f"/deals/{deal.id}/kuendigung/formular/entfernen")
    assert db.query(KuendigungFormular).count() == 0
