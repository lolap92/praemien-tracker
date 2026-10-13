"""Kündigungs-Assistent (kuendigung_assistent.py, routers/kuendigung.py) -
kein echtes Netzwerk, der Anthropic-Client wird gefaked wie in
test_kuendigung_recherche.py."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from praemien_tracker import config, iban
from praemien_tracker import kuendigung_assistent as ka
from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber, KuendigungAnforderung, Kuendigungsschreiben, ProtokollEintrag

client = TestClient(app)

GUELTIGE_IBAN = "DE89370400440532013000"


class _FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output
        self.aufrufe: list[dict] = []

    def parse(self, **kwargs):
        self.aufrufe.append(kwargs)
        return SimpleNamespace(parsed_output=self._parsed_output)


class _FakeClient:
    def __init__(self, parsed_output):
        self.messages = _FakeMessages(parsed_output)


def _ergebnis(**overrides):
    daten = {
        "gefunden": True,
        "kanal": "brief",
        "empfaenger_anschrift": "Testbank AG\nPostfach 1\n10000 Berlin",
        "empfaenger_email": "kuendigung@testbank.example",
        "besonderheiten": ["Depot muss leer sein"],
        "zusatzfelder": [{"schluessel": "kundennummer", "label": "Kundennummer", "hinweis": "Steht im Postfach."}],
        "betreff": "Kündigung Depot {kontonummer}",
        "text": "hiermit kündige ich mein Depot {kontonummer} (Kundennummer {kundennummer}) {termin}. "
        "Restguthaben bitte auf {iban}.",
        "quelle_url": "https://testbank.example/kuendigen",
    }
    daten.update(overrides)
    return ka._AnforderungErgebnis(**daten)


@pytest.fixture()
def deal(db):
    eintrag = Deal(kontoart="Depot", bank=Bank(name="Testbank"), inhaber=Inhaber(name="Max"))
    db.add(eintrag)
    db.commit()
    return eintrag


@pytest.fixture()
def mit_key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEMO_MODUS", False)


def _absender(inhaber: Inhaber) -> None:
    inhaber.voller_name = "Max Mustermann"
    inhaber.strasse = "Musterweg 1"
    inhaber.plz = "12345"
    inhaber.ort = "Musterstadt"


# ---------- IBAN ----------


def test_iban_normalisieren_und_pruefen():
    assert iban.normalisieren(" de89 3704 0044 0532 0130 00 ") == GUELTIGE_IBAN
    assert iban.normalisieren("   ") is None
    assert iban.gueltig(GUELTIGE_IBAN)
    assert not iban.gueltig("DE89370400440532013001")
    assert iban.formatiert(GUELTIGE_IBAN) == "DE89 3704 0044 0532 0130 00"
    assert iban.maskiert(GUELTIGE_IBAN) == "DE89 … 3000"


# ---------- Vorlage und Platzhalter ----------


def test_standardvorlage_fragt_nach_absender_kontonummer_und_iban(deal):
    """Ohne Recherche greift die feste Vorlage - der kurze Anzeigename zählt
    nicht als vollständiger Name."""
    anforderung = ka.standard_anforderung()
    werte = ka.werte_fuer(deal)

    assert ka.absender_fehlend(werte) == ["name", "strasse", "plz", "ort"]
    assert ka.fehlende(anforderung, werte) == ["kontonummer", "iban"]
    assert werte["termin"] == ka.STANDARD_TERMIN


def test_schreiben_setzt_werte_ein_und_ergaenzt_anrede_und_gruss(deal):
    _absender(deal.inhaber)
    deal.kontonummer = "4711"
    deal.inhaber.iban = GUELTIGE_IBAN
    werte = ka.werte_fuer(deal)

    schreiben = ka.schreiben(ka.standard_anforderung(), werte)

    assert schreiben["betreff"] == "Kündigung Depot, Kontonummer 4711"
    assert schreiben["text"].startswith(ka.ANREDE)
    assert schreiben["text"].endswith(ka.GRUSS)
    assert "DE89 3704 0044 0532 0130 00" in schreiben["text"]
    assert "{" not in schreiben["text"]
    assert ka.mail_signatur(werte) == "Max Mustermann\nMusterweg 1\n12345 Musterstadt"


def test_unbekannter_platzhalter_der_ki_wird_zum_zusatzfeld():
    """Ein Platzhalter, den die KI nicht als Zusatzfeld aufgeführt hat, darf
    nicht ungefragt im Schreiben landen; ein aufgeführtes, aber ungenutztes
    Zusatzfeld fällt weg, ebenso eines, das einen Standard-Schlüssel
    überschreiben würde."""
    werte = ka._bereinigt(
        _ergebnis(
            text="hiermit kündige ich {kontonummer}, Depotnummer {depot_nr}.",
            zusatzfelder=[
                {"schluessel": "kundennummer", "label": "Kundennummer"},
                {"schluessel": "name", "label": "Überschrieben"},
            ],
        )
    )
    assert json.loads(werte["zusatzfelder"]) == [{"schluessel": "depot_nr", "label": "Depot nr", "hinweis": ""}]


def test_unbrauchbares_ergebnis_wird_verworfen():
    assert ka._bereinigt(_ergebnis(gefunden=False)) is None
    assert ka._bereinigt(_ergebnis(text="  ")) is None
    assert ka._bereinigt(_ergebnis(kanal="fax"))["kanal"] == "brief"


# ---------- Recherche ----------


def test_recherche_speichert_und_schickt_keine_persoenlichen_daten(db, deal, mit_key, monkeypatch):
    _absender(deal.inhaber)
    deal.inhaber.iban = GUELTIGE_IBAN
    deal.kontonummer = "4711"
    db.commit()
    fake = _FakeClient(_ergebnis())
    monkeypatch.setattr(ka, "anthropic_client", lambda: fake)

    anforderung = ka.recherchieren(db, deal)

    assert anforderung is not None and anforderung.ki
    assert anforderung.zusatzfelder[0]["schluessel"] == "kundennummer"
    zeile = db.query(KuendigungAnforderung).one()
    assert (zeile.bank_name, zeile.kontoart, zeile.kanal) == ("Testbank", "Depot", "brief")

    prompt = fake.messages.aufrufe[0]["messages"][0]["content"]
    for geheim in ("Max Mustermann", "Musterweg", GUELTIGE_IBAN, "4711"):
        assert geheim not in prompt
    assert "{iban}" in prompt and "{kundennummer}" in prompt


def test_fehlgeschlagene_neu_recherche_behaelt_bisherigen_eintrag(db, deal, mit_key, monkeypatch):
    monkeypatch.setattr(ka, "anthropic_client", lambda: _FakeClient(_ergebnis()))
    ka.recherchieren(db, deal)
    monkeypatch.setattr(ka, "anthropic_client", lambda: _FakeClient(_ergebnis(gefunden=False)))

    assert ka.recherchieren(db, deal) is None
    assert ka.anforderung_fuer(db, deal).ki
    assert db.query(KuendigungAnforderung).count() == 1


def test_demo_modus_recherchiert_nie(db, deal, mit_key, monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODUS", True)
    fake = _FakeClient(_ergebnis())
    monkeypatch.setattr(ka, "anthropic_client", lambda: fake)

    antwort = client.post(f"/deals/{deal.id}/kuendigung/recherche", follow_redirects=False)

    assert antwort.status_code == 303
    assert antwort.headers["location"].endswith("recherche=demo")
    assert fake.messages.aufrufe == []


# ---------- Seiten ----------


def test_seite_ohne_angaben_fragt_nach_und_zeigt_kein_schreiben(deal):
    antwort = client.get(f"/deals/{deal.id}/kuendigung")
    assert antwort.status_code == 200
    assert "Für das Schreiben fehlt noch" in antwort.text
    assert 'id="ka-schreiben"' not in antwort.text
    # Der Anzeigename steht als Startwert im Namensfeld.
    assert 'name="name" value="Max"' in antwort.text


def test_unbekannter_deal_liefert_404():
    assert client.get("/deals/999999/kuendigung").status_code == 404


def test_angaben_speichern_verteilt_auf_inhaber_bank_und_deal(db, deal):
    antwort = client.post(
        f"/deals/{deal.id}/kuendigung/angaben",
        data={
            "name": "Max Mustermann",
            "strasse": "Musterweg 1",
            "plz": "12345",
            "ort": "Musterstadt",
            "iban": "de89 3704 0044 0532 0130 00",
            "kontonummer": "4711",
            "bank_anschrift": "Testbank AG\n\n  Postfach 1  \n10000 Berlin",
            "bank_email": "kuendigung@testbank.example",
            "termin": "zum 31.12.2026",
            "zusatz_kundennummer": "K-1",
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.expire_all()
    deal = db.get(Deal, deal.id)
    assert deal.inhaber.voller_name == "Max Mustermann"
    assert deal.inhaber.iban == GUELTIGE_IBAN
    assert deal.kontonummer == "4711"
    assert deal.bank.anschrift == "Testbank AG\nPostfach 1\n10000 Berlin"
    assert deal.bank.kuendigung_email == "kuendigung@testbank.example"
    assert ka.angaben_laden(deal) == {"termin": "zum 31.12.2026", "kundennummer": "K-1"}

    seite = client.get(f"/deals/{deal.id}/kuendigung").text
    assert 'id="ka-schreiben"' in seite
    assert "zum 31.12.2026" in seite
    assert "kuendigung@testbank.example" in seite


def test_nicht_mitgeschickte_felder_bleiben_unangetastet(db, deal):
    _absender(deal.inhaber)
    deal.inhaber.iban = GUELTIGE_IBAN
    db.commit()

    client.post(f"/deals/{deal.id}/kuendigung/angaben", data={"kontonummer": "4711"}, follow_redirects=False)

    db.expire_all()
    inhaber = db.get(Deal, deal.id).inhaber
    assert inhaber.voller_name == "Max Mustermann"
    assert inhaber.iban == GUELTIGE_IBAN


def _brief_bereit(db, deal) -> None:
    _absender(deal.inhaber)
    deal.inhaber.iban = GUELTIGE_IBAN
    deal.kontonummer = "4711"
    deal.bank.anschrift = "Testbank AG\nPostfach 1\n10000 Berlin"
    deal.bank.kuendigung_email = "kuendigung@testbank.example"
    db.commit()


def _schreiben(deal, ausgabe: str, betreff: str = "Kündigung Depot 4711", text: str = "Sehr geehrte Damen und Herren,\n\nhiermit kündige ich.\n\nMit freundlichen Grüßen"):
    return client.post(
        f"/deals/{deal.id}/kuendigung/schreiben",
        data={"ausgabe": ausgabe, "betreff": betreff, "text": text},
        follow_redirects=False,
    )


def _pdf_text(inhalt: bytes) -> bytes:
    """Entpackte Inhaltsströme - genug, um gesetzten Text wiederzufinden,
    ohne eine PDF-Bibliothek als Testabhängigkeit."""
    import re
    import zlib

    return b"".join(zlib.decompress(m) for m in re.findall(rb"stream\n(.*?)\nendstream", inhalt, re.S))


def test_druckansicht_speichert_entwurf_mit_bearbeitetem_text(db, deal):
    _brief_bereit(db, deal)

    antwort = _schreiben(deal, "druck", betreff="Eigener Betreff", text="Absatz eins\n\nAbsatz zwei")

    assert antwort.status_code == 200
    assert "Eigener Betreff" in antwort.text
    assert "<p>Absatz eins</p>" in antwort.text and "<p>Absatz zwei</p>" in antwort.text
    assert "Postfach 1" in antwort.text and "Musterstadt, " in antwort.text
    gespeichert = db.query(Kuendigungsschreiben).one()
    assert (gespeichert.kanal, gespeichert.versendet_am) == ("brief", None)


def test_pdf_download(db, deal):
    _brief_bereit(db, deal)

    antwort = _schreiben(deal, "pdf")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "application/pdf"
    assert 'filename="Kuendigung_Testbank_Depot_Max_' in antwort.headers["content-disposition"]
    assert antwort.content.startswith(b"%PDF-1.4")
    text = _pdf_text(antwort.content)
    assert "Kündigung Depot 4711".encode("cp1252") in text
    assert "Grüßen".encode("cp1252") in text
    assert b"Postfach 1" in text


def test_word_download_ist_gueltiges_docx(db, deal):
    import io
    import zipfile
    from xml.dom import minidom

    _brief_bereit(db, deal)

    antwort = _schreiben(deal, "docx")

    assert antwort.status_code == 200
    with zipfile.ZipFile(io.BytesIO(antwort.content)) as z:
        assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml"} <= set(z.namelist())
        dokument = z.read("word/document.xml").decode()
    minidom.parseString(dokument)  # wohlgeformt
    assert "Kündigung Depot 4711" in dokument
    assert "Postfach 1" in dokument


def test_erneuter_download_ueberschreibt_den_entwurf(db, deal):
    """Ein Entwurf je Kanal - erst nach dem Versand entsteht ein neuer."""
    _brief_bereit(db, deal)
    _schreiben(deal, "pdf", betreff="Erster")
    _schreiben(deal, "docx", betreff="Zweiter")
    assert [s.betreff for s in db.query(Kuendigungsschreiben).all()] == ["Zweiter"]

    erstes = db.query(Kuendigungsschreiben).one()
    client.post(f"/deals/{deal.id}/kuendigung/schreiben/{erstes.id}/versendet", data={"datum": "2026-10-01"})
    _schreiben(deal, "pdf", betreff="Dritter")

    db.expire_all()
    assert [s.betreff for s in db.query(Kuendigungsschreiben).order_by(Kuendigungsschreiben.id)] == ["Zweiter", "Dritter"]


def test_brief_ohne_absender_oder_anschrift_wird_abgelehnt(db, deal):
    antwort = _schreiben(deal, "pdf")

    assert antwort.status_code == 400
    assert db.query(Kuendigungsschreiben).count() == 0


def test_email_entwurf_mit_signatur_und_empfaenger(db, deal):
    _brief_bereit(db, deal)

    antwort = _schreiben(deal, "mail")

    assert antwort.status_code == 200
    gespeichert = db.get(Kuendigungsschreiben, antwort.json()["id"])
    assert gespeichert.kanal == "email"
    assert gespeichert.empfaenger == "kuendigung@testbank.example"
    assert gespeichert.text.endswith("Mit freundlichen Grüßen\nMax Mustermann\nMusterweg 1\n12345 Musterstadt")
    # Eine E-Mail hat kein PDF.
    assert client.get(f"/deals/{deal.id}/kuendigung/schreiben/{gespeichert.id}/pdf").status_code == 404


def test_versendet_markiert_deal_als_gekuendigt(db, deal):
    _brief_bereit(db, deal)
    _schreiben(deal, "pdf")
    gespeichert = db.query(Kuendigungsschreiben).one()

    antwort = client.post(
        f"/deals/{deal.id}/kuendigung/schreiben/{gespeichert.id}/versendet",
        data={"datum": "2026-09-30"},
        follow_redirects=False,
    )

    assert antwort.status_code == 303
    db.expire_all()
    deal = db.get(Deal, deal.id)
    assert deal.gekuendigt is True
    assert deal.gekuendigt_im_monat == "2026-09"
    assert deal.kuendigungsschreiben[0].versendet_am.isoformat() == "2026-09-30"
    assert "versendet am 30.09.2026" in client.get(f"/deals/{deal.id}/kuendigung").text
    assert "versendet am 30.09.2026" in client.get(f"/deals/{deal.id}").text


def test_versendet_behaelt_gepflegten_kuendigungsmonat(db, deal):
    _brief_bereit(db, deal)
    deal.gekuendigt_im_monat = "2026-08"
    db.commit()
    _schreiben(deal, "pdf")
    gespeichert = db.query(Kuendigungsschreiben).one()

    client.post(f"/deals/{deal.id}/kuendigung/schreiben/{gespeichert.id}/versendet", data={"datum": "2026-09-30"})

    db.expire_all()
    assert db.get(Deal, deal.id).gekuendigt_im_monat == "2026-08"


def test_gespeichertes_schreiben_ist_eine_momentaufnahme(db, deal):
    """Eine spätere Adressänderung darf ein schon erzeugtes Schreiben nicht
    nachträglich umschreiben."""
    _brief_bereit(db, deal)
    _schreiben(deal, "pdf")
    gespeichert = db.query(Kuendigungsschreiben).one()
    deal.inhaber.strasse = "Neue Straße 9"
    db.commit()

    html = client.get(f"/deals/{deal.id}/kuendigung/schreiben/{gespeichert.id}/druck").text

    assert "Musterweg 1" in html
    assert "Neue Straße 9" not in html


def test_schreiben_eines_anderen_deals_ist_nicht_abrufbar(db, deal):
    _brief_bereit(db, deal)
    _schreiben(deal, "pdf")
    gespeichert = db.query(Kuendigungsschreiben).one()
    anderer = Deal(kontoart="Girokonto", bank=deal.bank, inhaber=deal.inhaber)
    db.add(anderer)
    db.commit()

    assert client.get(f"/deals/{anderer.id}/kuendigung/schreiben/{gespeichert.id}/pdf").status_code == 404


def test_loeschen_laesst_gekuendigt_stehen_und_deal_loeschen_nimmt_schreiben_mit(db, deal):
    _brief_bereit(db, deal)
    _schreiben(deal, "pdf")
    gespeichert = db.query(Kuendigungsschreiben).one()
    client.post(f"/deals/{deal.id}/kuendigung/schreiben/{gespeichert.id}/versendet", data={})
    client.post(f"/deals/{deal.id}/kuendigung/schreiben/{gespeichert.id}/loeschen")

    db.expire_all()
    deal = db.get(Deal, deal.id)
    assert deal.gekuendigt is True
    assert deal.kuendigungsschreiben == []

    _schreiben(deal, "pdf")
    db.expire_all()
    db.delete(db.get(Deal, deal.id))
    db.commit()
    assert db.query(Kuendigungsschreiben).count() == 0


def test_pdf_umbruch_und_folgeseite():
    from praemien_tracker import kuendigung_dokumente as kd

    zeilen = kd._umbrechen("a " * 200 + "x" * 300, 165, 11)
    assert all(kd._breite_mm(z, 11) <= 165 for z in zeilen)
    assert "".join(zeilen).count("x") == 300

    brief = kd.Brief(["A"], ["B"], "Ort, 01.01.2026", "Betreff", ["Absatz " * 40] * 30, "Name")
    # 30 Absätze à drei Zeilen füllen vier Seiten.
    assert kd.als_pdf(brief).count(b"/Type /Page ") == 4


def test_deal_seite_verlinkt_den_assistenten(deal):
    assert f'href="deals/{deal.id}/kuendigung"' in client.get(f"/deals/{deal.id}").text


# ---------- Inhaber und Protokoll ----------


def test_inhaber_seite_speichert_absender_und_iban(db):
    inhaber = Inhaber(name="Max")
    db.add(inhaber)
    db.commit()
    i = inhaber.id

    client.post(
        "/inhaber",
        data={f"voller_name_{i}": "Max Mustermann", f"iban_{i}": "DE89 3704 0044 0532 0130 00", f"geburtsdatum_{i}": "1990-02-03"},
        follow_redirects=False,
    )

    db.refresh(inhaber)
    assert inhaber.voller_name == "Max Mustermann"
    assert inhaber.iban == GUELTIGE_IBAN
    assert inhaber.geburtsdatum.isoformat() == "1990-02-03"
    assert "DE89 3704 0044 0532 0130 00" in client.get("/inhaber").text


def test_protokoll_speichert_iban_nur_maskiert(db):
    inhaber = Inhaber(name="Max", iban=GUELTIGE_IBAN)
    db.add(inhaber)
    db.commit()
    inhaber.iban = "DE02120300000000202051"
    db.commit()

    eintraege = db.query(ProtokollEintrag).filter(ProtokollEintrag.tabelle == "Inhaber").all()
    assert eintraege
    for e in eintraege:
        for text in (e.alter_wert, e.neuer_wert, e.json_snapshot):
            assert GUELTIGE_IBAN not in (text or "")
            assert "DE02120300000000202051" not in (text or "")
    aenderung = next(e for e in eintraege if e.feld == "iban")
    assert aenderung.neuer_wert == "DE02 … 2051"
