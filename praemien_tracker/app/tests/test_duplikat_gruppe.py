"""routers/vorschlaege.py: quellenübergreifende Duplikat-Erkennung - gleiche
Bank+Kontoart aus mehreren Fundstellen (z.B. mydealz und spartanien) werden
zu einer Duplikat-Gruppe gebündelt, mit der Möglichkeit, eine Version zu
übernehmen (verwirft die übrigen automatisch) oder alle zu verwerfen."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Deal, DealVorschlag, Inhaber

client = TestClient(app)


@pytest.fixture()
def inhaber(db):
    eintrag = Inhaber(name="Alice")
    db.add(eintrag)
    db.commit()
    return eintrag


def _vorschlag(db, inhaber, status: str, **kwargs) -> DealVorschlag:
    daten = {
        "inhaber_id": inhaber.id,
        "quelle": "mydealz",
        "quelle_url": "https://www.mydealz.de/x",
        "bank_name": "C24",
        "kontoart": "Girokonto",
        "praemie_betrag": Decimal("125.00"),
        "sperrfrist_monate": None,
        "ablehnungsgruende": None,
        "roh_json": (
            '{{"bank": "C24", "kontoart": "Girokonto", "inhaber": "{name}", '
            '"praemien": [{{"quelle": "bank", "betrag": "125.00", "erhalten": false}}], '
            '"bedingungen": [], "urls": [{{"url": "https://www.mydealz.de/x", "bezeichnung": "mydealz-Angebot"}}]}}'
        ).format(name=inhaber.name),
        "inhalt_hash": "abc123",
        "status": status,
    }
    daten.update(kwargs)
    eintrag = DealVorschlag(**daten)
    db.add(eintrag)
    db.commit()
    return eintrag


def test_zwei_quellen_gleiche_bank_werden_gebuendelt(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle="mydealz", quelle_url="https://www.mydealz.de/ing", inhalt_hash="h1",
               bank_name="ING", praemie_betrag=Decimal("150.00"))
    _vorschlag(db, inhaber, "vorgeschlagen", quelle="spartanien", quelle_url="https://www.spartanien.de/ing", inhalt_hash="h2",
               bank_name="ING", praemie_betrag=Decimal("175.00"))

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "dup-gruppe" in antwort.text
    assert "2×" in antwort.text
    # Beide Prämienhöhen sichtbar, nicht nur eine.
    assert "150,00 €" in antwort.text
    assert "175,00 €" in antwort.text
    assert "Ausgewählte übernehmen" in antwort.text
    assert "Alle verwerfen" in antwort.text
    # Wie bei der bestehenden Mehrpersonen-Bündelung zählt der Chip die
    # gebündelte Karte nur einmal, nicht jede Quelle einzeln.
    assert "1 vorgeschlagen" in antwort.text


def test_drei_quellen_werden_gebuendelt(db, inhaber):
    """Die Bündelung ist nicht auf mydealz/spartanien beschränkt - eine
    dritte (oder vierte, fünfte, ...) Quelle wird genauso erkannt."""
    _vorschlag(db, inhaber, "vorgeschlagen", quelle="mydealz", quelle_url="https://www.mydealz.de/ing", inhalt_hash="h1",
               bank_name="ING", praemie_betrag=Decimal("150.00"))
    _vorschlag(db, inhaber, "vorgeschlagen", quelle="spartanien", quelle_url="https://www.spartanien.de/ing", inhalt_hash="h2",
               bank_name="ING", praemie_betrag=Decimal("175.00"))
    _vorschlag(db, inhaber, "vorgeschlagen", quelle="spartanien", quelle_url="https://www.bankkonditionen.invalid/ing", inhalt_hash="h3",
               bank_name="ING", praemie_betrag=Decimal("160.00"))

    antwort = client.get("/vorschlaege")
    assert "3×" in antwort.text


def test_unterschiedliche_bank_wird_nicht_gebuendelt(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1", bank_name="ING")
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2", bank_name="DKB")

    antwort = client.get("/vorschlaege")
    assert 'class="card dup-gruppe' not in antwort.text
    assert "2 vorgeschlagen" in antwort.text


def test_unterschiedliche_kontoart_wird_nicht_gebuendelt(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1",
               bank_name="ING", kontoart="Girokonto")
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2",
               bank_name="ING", kontoart="Depot")

    antwort = client.get("/vorschlaege")
    assert 'class="card dup-gruppe' not in antwort.text


def test_bankname_normalisiert_erkannt(db, inhaber):
    """Groß-/Kleinschreibung und Schreibweise-Unterschiede zwischen den
    Quellen dürfen die Erkennung nicht verhindern (wie beim bestehenden
    Bank-Abgleich, siehe derived.bank_name_normalisieren)."""
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1", bank_name="SMARTBROKER")
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2", bank_name="Smart Broker")

    antwort = client.get("/vorschlaege")
    assert "dup-gruppe" in antwort.text
    assert "2×" in antwort.text


def test_praemienhoehe_kein_kriterium(db, inhaber):
    """Zentrale Anforderung: unterschiedliche Prämienhöhe je Quelle darf die
    Bündelung nicht verhindern."""
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1",
               bank_name="ING", praemie_betrag=Decimal("50.00"))
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2",
               bank_name="ING", praemie_betrag=Decimal("500.00"))

    antwort = client.get("/vorschlaege")
    assert "dup-gruppe" in antwort.text


def test_bester_status_bestimmt_die_sektion(db, inhaber):
    """Ist eine Quelle vorgeschlagen, die andere automatisch abgelehnt, soll
    die Gruppe unter 'Vorgeschlagen' auftauchen - gleiches Prinzip wie beim
    bestehenden Mehrpersonen-Fund."""
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1", bank_name="ING")
    _vorschlag(db, inhaber, "automatisch_abgelehnt", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2", bank_name="ING",
               ablehnungsgruende="Bereits Kundin.")

    antwort = client.get("/vorschlaege")
    assert "1 vorgeschlagen" in antwort.text
    assert "0 abgelehnt" in antwort.text


def test_status_filter_zeigt_keine_karte_wenn_badge_dafuer_0_zeigt(db, inhaber):
    """Regression: ein Bündel mit einer besseren ('vorgeschlagen') und einer
    schlechteren ('zu prüfen') Fundstelle zählt beim Badge als 'vorgeschlagen'
    (bester Status gewinnt). Filtert man gezielt auf 'zu prüfen', darf dafür
    keine Karte mehr auftauchen - sonst zeigt der Chip 0, während trotzdem
    eine Karte in der Liste steht (genau dieser Bug: die Karten-Liste wurde
    bei aktivem Status-Filter aus den ungebündelten Einzel-Funden neu
    zusammengesetzt, statt aus demselben Bündel wie der Zähler)."""
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1", bank_name="ING")
    _vorschlag(db, inhaber, "zu_pruefen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2", bank_name="ING")

    antwort = client.get("/vorschlaege")
    assert "1 vorgeschlagen" in antwort.text
    assert "0 zu prüfen" in antwort.text

    gefiltert = client.get("/vorschlaege?status=zu_pruefen")
    assert "0 zu prüfen" in gefiltert.text
    # 'dup-gruppe' steckt auch im eingebetteten <script> (JS-Selektor) -
    # gezielt auf die Karte selbst prüfen, nicht bloß die Klasse irgendwo im HTML.
    assert 'class="card dup-gruppe' not in gefiltert.text


def test_automatisch_abgelehnte_duplikat_gruppe_zeigt_begruendung(db, inhaber):
    """Sind alle gebündelten Fundstellen automatisch abgelehnt, soll die
    Kachel trotz mehrerer Quellen oben eine gemeinsame Begründung zeigen -
    dedupliziert, falls beide Quellen denselben Grund liefern."""
    _vorschlag(db, inhaber, "automatisch_abgelehnt", quelle="mydealz", quelle_url="https://www.mydealz.de/ing",
               inhalt_hash="h1", bank_name="ING", ablehnungsgruende="Bereits Kundin.")
    _vorschlag(db, inhaber, "automatisch_abgelehnt", quelle="spartanien", quelle_url="https://www.spartanien.de/ing",
               inhalt_hash="h2", bank_name="ING", ablehnungsgruende="Bereits Kundin.")

    antwort = client.get("/vorschlaege")
    assert "dup-gruppe" in antwort.text
    box_start = antwort.text.index("Automatisch abgelehnt:")
    box_ende = antwort.text.index("</div>", box_start)
    box = antwort.text[box_start:box_ende]
    assert box.count("Bereits Kundin.") == 1


def test_uebernehmen_verwirft_andere_quellen_automatisch(db, inhaber):
    gewinner = _vorschlag(db, inhaber, "vorgeschlagen", quelle="mydealz", quelle_url="https://www.mydealz.de/ing",
                           inhalt_hash="h1", bank_name="ING", praemie_betrag=Decimal("175.00"))
    verlierer = _vorschlag(db, inhaber, "vorgeschlagen", quelle="spartanien", quelle_url="https://www.spartanien.de/ing",
                            inhalt_hash="h2", bank_name="ING", praemie_betrag=Decimal("150.00"))

    antwort = client.post(
        "/vorschlaege/uebernehmen/bestaetigen",
        data={
            "vorschlag_ids": [gewinner.id],
            "verwerfen_duplikat_ids": [verlierer.id],
            "bank": "ING",
            "kontoart": "Girokonto",
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.refresh(gewinner)
    db.refresh(verlierer)
    assert gewinner.status == "uebernommen"
    assert verlierer.status == "verworfen"
    assert verlierer.verwerfen_gruende == "duplikat"
    assert db.query(Deal).count() == 1


def test_uebernehmen_ohne_duplikat_ids_verhaelt_sich_wie_bisher(db, inhaber):
    """Rückwärtskompatibel: ohne verwerfen_duplikat_ids (normale, nicht
    gebündelte Karte) ändert sich am bisherigen Verhalten nichts."""
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    antwort = client.post(
        "/vorschlaege/uebernehmen/bestaetigen",
        data={"vorschlag_ids": [vorschlag.id], "bank": "C24", "kontoart": "Girokonto"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    db.refresh(vorschlag)
    assert vorschlag.status == "uebernommen"


def test_alle_verwerfen_button_deckt_alle_quellen_ab(db, inhaber):
    a = _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1", bank_name="ING")
    b = _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2", bank_name="ING")

    antwort = client.get("/vorschlaege")
    # "Alle verwerfen" öffnet wie beim einzelnen Vorschlag einen Dialog mit
    # Grund-Auswahl (Mehrfachauswahl) statt fest "duplikat" zu setzen - das
    # versteckte Formular trägt aber weiterhin beide IDs.
    assert f'name="vorschlag_ids" value="{a.id}"' in antwort.text
    assert f'name="vorschlag_ids" value="{b.id}"' in antwort.text
    assert 'name="gruende" value="praemie_niedrig"' in antwort.text
    # "Duplikat" ist sinnvoll vorausgewählt (Kacheln bündeln ja vermutliche
    # Duplikate), aber weiterhin nur eine von mehreren wählbaren Optionen.
    assert 'name="gruende" value="duplikat" checked' in antwort.text


def test_alle_verwerfen_dialog_erlaubt_anderen_grund_als_duplikat(db, inhaber):
    a = _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1", bank_name="ING")
    b = _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2", bank_name="ING")

    antwort = client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [a.id, b.id], "gruende": ["praemie_niedrig"]},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    db.refresh(a)
    db.refresh(b)
    assert a.status == "verworfen"
    assert a.verwerfen_gruende == "praemie_niedrig"
    assert b.status == "verworfen"
    assert b.verwerfen_gruende == "praemie_niedrig"
