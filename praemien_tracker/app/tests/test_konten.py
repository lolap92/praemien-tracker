"""Konten ohne Prämie (models.ART_KONTO): anderweitig eröffnete Konten, die
nur bis zur Kündigung mitverfolgt werden.

Sie kennen nur die Status Kündigen -> Bestätigung warten -> Abgeschlossen,
werden nirgends angemahnt und laufen trotzdem überall mit, wo es um die
Kündigung geht: Kündigen-Reiter, Sperrfristen, Kündigungshinweis-Batch und
der "bereits Kunde"-Abgleich des KI-Deal-Finders.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from praemien_tracker import derived, kuendigung_recherche
from praemien_tracker.finder import matching
from praemien_tracker.finder.extraktion import AngebotExtraktion
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.main import app
from praemien_tracker.models import ART_KONTO, Bank, Deal, Inhaber, Praemie
from praemien_tracker.schemas import DealImport

client = TestClient(app)


def _konto(db, bank_name: str = "Kontobank", **kwargs) -> Deal:
    konto = Deal(
        art=ART_KONTO,
        kontoart="Girokonto",
        bank=Bank(name=bank_name),
        inhaber=Inhaber(name=f"Inhaber-{bank_name}"),
        **kwargs,
    )
    db.add(konto)
    db.commit()
    return konto


# --- Status ---------------------------------------------------------------


def test_neues_konto_steht_sofort_auf_kuendigen():
    """Ohne Prämie bliebe ein Deal in "Auf Prämie warten" hängen - ein
    Konto überspringt Bedingungen, Prämien und Sperrfrist."""
    konto = Deal(art=ART_KONTO, kontoart="Girokonto", kuendbar_ab=datetime.date(2099, 1, 1))
    assert derived.status(konto) == derived.STATUS_KUENDIGEN


def test_konto_status_folgt_nur_der_kuendigung():
    konto = Deal(art=ART_KONTO, kontoart="Girokonto", gekuendigt=True)
    assert derived.status(konto) == derived.STATUS_BESTAETIGUNG_WARTEN
    konto.kuendigung_bestaetigt = True
    assert derived.status(konto) == derived.STATUS_ABGESCHLOSSEN


def test_deal_ohne_art_bleibt_ein_deal():
    deal = Deal(kontoart="Girokonto", bank=Bank(name="B"), inhaber=Inhaber(name="I"))
    deal.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=False))
    assert not deal.ist_konto
    assert derived.status(deal) != derived.STATUS_KUENDIGEN


# --- keine Erinnerungen ---------------------------------------------------


def test_konto_wird_nirgends_angemahnt(db):
    konto = _konto(db)
    # Alles leer, was bei einem Deal angemahnt würde - und älter als die
    # 72-Stunden-Schonfrist für "keine Prämie hinterlegt".
    konto.erstellt_am = datetime.datetime(2020, 1, 1)
    assert derived.offene_felder(konto) == []
    assert derived.pruefpunkte(konto) == []
    kategorien = {t.kategorie for t in derived.deal_todos(konto)}
    assert kategorien == {"Kündigen"}


def test_kuendigen_todo_mit_eigenem_text_und_gebuehr(db):
    _konto(db, kontofuehrungsgebuehren=Decimal("4.90"))
    html = client.get("/todos?tab=kuendigen").text
    assert "Konto kündigen" in html
    assert "kostet 4,90 € mtl." in html


# --- Anlegen und Bearbeiten -----------------------------------------------


def test_konto_anlegen(db):
    antwort = client.post(
        "/konten/new",
        data={"bank": "Neubank", "inhaber": "Max", "kontoart": "Tagesgeld"},
        follow_redirects=False,
    )
    assert antwort.status_code in (302, 303)
    konto = db.query(Deal).one()
    assert konto.art == ART_KONTO
    assert (konto.bank.name, konto.inhaber.name, konto.kontoart) == ("Neubank", "Max", "Tagesgeld")
    assert konto.praemien == [] and konto.aufgaben == []
    assert antwort.headers["location"].endswith(f"deals/{konto.id}")


def test_konto_anlegen_ohne_pflichtfeld_wird_abgelehnt(db):
    antwort = client.post("/konten/new", data={"bank": " ", "inhaber": "Max", "kontoart": "Girokonto"})
    assert antwort.status_code == 400
    assert "Bitte ausfüllen: Bank." in antwort.text
    assert db.query(Deal).count() == 0


def test_bearbeiten_zeigt_nur_die_konto_felder(db):
    konto = _konto(db)
    soup = BeautifulSoup(client.get(f"/deals/{konto.id}/edit").text, "html.parser")
    assert "Konto bearbeiten" in soup.title.text
    for vorhanden in ("kontofuehrungsgebuehren", "freibetrag", "freibetrag_jahr", "kontonummer", "kommentar", "gekuendigt"):
        assert soup.select_one(f'[name="{vorhanden}"]') is not None, vorhanden
    for fehlt in ("kuendbar_ab", "zugangsdaten_gespeichert", "praemien_auf_sparkonto", "neu_praemie_betrag", "neu_bedingung_beschreibung", "url"):
        assert soup.select_one(f'[name="{fehlt}"]') is None, fehlt
    assert soup.select_one('[name="neu_aufgabe_beschreibung"]') is not None
    assert "stornieren" not in soup.text


def test_detailseite_ohne_praemien_und_bedingungen(db):
    konto = _konto(db)
    html = client.get(f"/deals/{konto.id}").text
    assert "Konto ohne Prämie" in html
    assert "Noch keine Prämien erfasst." not in html
    assert "Keine Bedingungen hinterlegt" not in html


def test_speichern_mit_gekuendigt_setzt_den_kuendigungsmonat(db):
    """Ohne Monat fehlte das Konto in den Sperrfristen - und anmahnen soll
    die App bei Konten nichts."""
    konto = _konto(db)
    client.post(
        f"/deals/{konto.id}",
        data={"bank": "Kontobank", "inhaber": "Inhaber-Kontobank", "kontoart": "Girokonto", "gekuendigt": "on"},
        follow_redirects=False,
    )
    db.refresh(konto)
    assert konto.gekuendigt_im_monat == derived.format_monat(datetime.date.today())


# --- läuft überall mit, wo es um die Kündigung geht -----------------------


def test_gekuendigtes_konto_erscheint_in_den_sperrfristen(db):
    _konto(db, bank_name="Sperrbank", gekuendigt=True, gekuendigt_im_monat="2026-01")
    assert "Sperrbank" in client.get("/sperrfristen").text


def test_kuendigungshinweis_batch_laeuft_auch_fuer_konten(db, monkeypatch):
    konto = _konto(db, bank_name="Unbekannte Bank")
    monkeypatch.setattr(kuendigung_recherche, "hinweis_recherchieren", lambda *a, **kw: ("Per Brief.", "https://x"))
    assert kuendigung_recherche.alle_ohne_hinweis_nachtragen(db) == 1
    assert konto.kuendigung_hinweis == "Per Brief."


def test_konto_zaehlt_im_deal_finder_als_bestehende_kundschaft(db):
    konto = _konto(db, bank_name="Bestandsbank")
    fund = RohFund("mydealz", "https://mydealz.de/bestandsbank", "t", "x")
    ext = AngebotExtraktion(bank_name="Bestandsbank", kontoart="Girokonto", praemie_betrag=100.0, bedingungen=[])
    ergebnis = matching.bewerten(db, fund, ext, konto.inhaber, Decimal("50"))
    assert ergebnis.status == matching.STATUS_ABGELEHNT


# --- Liste und Import -----------------------------------------------------


def test_liste_markiert_konten_und_filtert_nach_art(db):
    _konto(db, bank_name="Nurkontobank")
    deal = Deal(kontoart="Depot", bank=Bank(name="Dealbank"), inhaber=Inhaber(name="Erika"))
    db.add(deal)
    db.commit()

    def banken(url: str) -> list[str]:
        soup = BeautifulSoup(client.get(url).text, "html.parser")
        return [b.text for b in soup.select(".deal-zeile .bank")]

    assert 'name="art" value="konto"' in client.get("/deals").text
    assert sorted(banken("/deals")) == ["Dealbank", "Nurkontobank"]
    assert banken("/deals?art=konto") == ["Nurkontobank"]
    assert banken("/deals?art=deal") == ["Dealbank"]


def test_art_chip_fehlt_solange_es_keine_konten_gibt(db):
    db.add(Deal(kontoart="Depot", bank=Bank(name="Dealbank"), inhaber=Inhaber(name="Erika")))
    db.commit()
    assert 'name="art"' not in client.get("/deals").text


def test_import_kennt_die_art():
    assert DealImport(bank="B", kontoart="Girokonto", inhaber="I").art == "deal"
    assert DealImport(bank="B", kontoart="Girokonto", inhaber="I", art="konto").art == "konto"
    with pytest.raises(ValueError):
        DealImport(bank="B", kontoart="Girokonto", inhaber="I", art="sparbuch")
