"""routers/vorschlaege.py: Gruppierung gleicher Funde, Filter, Mehrfach-
Übernehmen/Verwerfen und die Laufstatus-Anzeige."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Deal, DealVorschlag, FinderLauf, Inhaber, VorschlagPraemie

client = TestClient(app)


@pytest.fixture()
def inhaber(db):
    eintrag = Inhaber(name="Alice")
    db.add(eintrag)
    db.commit()
    return eintrag


@pytest.fixture()
def zwei_inhaber(db):
    alice = Inhaber(name="Alice")
    max_ = Inhaber(name="Max", ist_minderjaehrig=True)
    db.add_all([alice, max_])
    db.commit()
    return alice, max_


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


def test_vorschlaege_seite_gruppiert_nach_status(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1")
    _vorschlag(db, inhaber, "zu_pruefen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2")
    _vorschlag(db, inhaber, "automatisch_abgelehnt", quelle_url="https://www.mydealz.de/3", inhalt_hash="h3")

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "1 vorgeschlagen" in antwort.text
    assert "1 zu prüfen" in antwort.text
    assert "1 abgelehnt" in antwort.text


def test_karte_hat_deal_link_und_tags(db, inhaber):
    _vorschlag(
        db,
        inhaber,
        "vorgeschlagen",
        quelle="spartanien",
        quelle_url="https://www.spartanien.de/Santander+BestGiro",
        kontoart="Tagesgeld",
    )

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    # Link öffnet die Deal-Seite in einem neuen Tab.
    assert 'href="https://www.spartanien.de/Santander+BestGiro"' in antwort.text
    assert 'target="_blank"' in antwort.text
    # Tags: Quelle (groß geschrieben) und Kontoart.
    assert "Spartanien" in antwort.text
    assert "Tagesgeld" in antwort.text


def test_uebernehmen_button_orange_nur_bei_hinweisen(db, zwei_inhaber):
    """Hat ein Inhaber der Gruppe einen abweichenden Status/Hinweis, wird der
    Übernehmen-Button orange (Klasse 'warn'); ohne Hinweise bleibt er grün."""
    alice, max_ = zwei_inhaber

    # Der Übernehmen-Button ist speziell an "dlg-uebernehmen-" gebunden -
    # dieses Muster prüfen statt einer bloßen 'class="warn"'-Suche über die
    # ganze Seite, die auch auf andere Buttons (z.B. "Alle neu analysieren")
    # anspringen könnte.
    def _uebernehmen_button_ist_warn(html: str) -> bool:
        return 'class="warn" onclick="document.getElementById(\'dlg-uebernehmen-' in html

    # Mit Hinweis: alice vorgeschlagen, max abgelehnt (Begründung).
    _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="gleich", quelle_url="https://www.mydealz.de/a")
    _vorschlag(db, max_, "automatisch_abgelehnt", inhalt_hash="gleich", quelle_url="https://www.mydealz.de/a",
               ablehnungsgruende="Bereits Kundin.")
    antwort = client.get("/vorschlaege")
    assert _uebernehmen_button_ist_warn(antwort.text)

    from praemien_tracker.models import DealVorschlag as _DV
    db.query(_DV).delete()
    db.commit()

    # Ohne Hinweis: beide sauber vorgeschlagen -> kein 'warn'.
    _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="sauber", quelle_url="https://www.mydealz.de/b")
    _vorschlag(db, max_, "vorgeschlagen", inhalt_hash="sauber", quelle_url="https://www.mydealz.de/b")
    antwort2 = client.get("/vorschlaege")
    assert not _uebernehmen_button_ist_warn(antwort2.text)


def test_karte_zeigt_mehrere_teilpraemien_mit_bedingung(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen", praemie_betrag=Decimal("300.00"))
    vorschlag.praemien.append(VorschlagPraemie(betrag=Decimal("50.00"), geber="Spartanien", bedingung="für die Kontoeröffnung"))
    vorschlag.praemien.append(VorschlagPraemie(betrag=Decimal("250.00"), geber="Santander", bedingung="für den Kontowechselservice"))
    db.commit()

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "Spartanien" in antwort.text
    assert "für die Kontoeröffnung" in antwort.text
    assert "Santander" in antwort.text
    assert "für den Kontowechselservice" in antwort.text


def test_karte_zeigt_kinderdepot_tag_nur_bei_minderjaehrigem(db, zwei_inhaber):
    """Ein Fund, der (auch) zu einem minderjährigen Inhaber passt, bekommt den
    Kinderdepot-Tag; ein reiner Erwachsenen-Fund nicht."""
    alice, max_ = zwei_inhaber
    _vorschlag(db, max_, "vorgeschlagen", quelle_url="https://www.mydealz.de/kind", inhalt_hash="k1",
               kontoart="Depot")
    antwort = client.get("/vorschlaege")
    # Gezielt auf den Karten-Tag prüfen ("Kinderdepot" steht auch im Filter).
    assert "tag-kind" in antwort.text

    # Neuer Lauf-Kontext: nur ein Erwachsener -> kein Kinderdepot-Tag.
    from praemien_tracker.models import DealVorschlag as _DV

    db.query(_DV).delete()
    db.commit()
    _vorschlag(db, alice, "vorgeschlagen", quelle_url="https://www.mydealz.de/erw", inhalt_hash="e1")
    antwort2 = client.get("/vorschlaege")
    assert "tag-kind" not in antwort2.text


def test_gleicher_fund_fuer_mehrere_inhaber_erscheint_nur_einmal(db, zwei_inhaber):
    """Zentrale Anforderung: derselbe Fund (gleiche quelle_url+inhalt_hash)
    soll nicht einmal je Inhaber in der Liste auftauchen."""
    alice, max_ = zwei_inhaber
    _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="gleich")
    _vorschlag(db, max_, "vorgeschlagen", inhalt_hash="gleich")

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "1 vorgeschlagen" in antwort.text
    assert "Alice" in antwort.text
    assert "Max" in antwort.text


def test_gruppen_status_ist_der_beste_einzelstatus(db, zwei_inhaber):
    """Ist der Fund für eine Person ein echter Neukunden-Deal, für eine
    andere aber automatisch abgelehnt (z.B. schon Bestandskunde), soll die
    Gruppe unter "Vorgeschlagen" auftauchen statt unter "Abgelehnt"."""
    alice, max_ = zwei_inhaber
    _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="gleich")
    _vorschlag(db, max_, "automatisch_abgelehnt", inhalt_hash="gleich", ablehnungsgruende="Bereits Kundin.")

    antwort = client.get("/vorschlaege")
    assert "1 vorgeschlagen" in antwort.text
    assert "0 abgelehnt" in antwort.text
    assert "Bereits Kundin." in antwort.text


def test_uebernehmen_legt_deal_an_und_markiert_vorschlag(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    antwort = client.post("/vorschlaege/uebernehmen", data={"vorschlag_ids": [vorschlag.id]}, follow_redirects=False)
    assert antwort.status_code == 303

    db.refresh(vorschlag)
    assert vorschlag.status == "uebernommen"

    deal = db.query(Deal).filter(Deal.kontoart == "Girokonto").one()
    assert deal.bank.name == "C24"
    assert deal.inhaber.name == "Alice"
    assert deal.praemien[0].quelle == "bank"
    assert deal.urls[0].url == "https://www.mydealz.de/x"


def test_uebernehmen_mit_mehreren_ids_legt_fuer_jeden_ausgewaehlten_namen_einen_deal_an(db, zwei_inhaber):
    alice, max_ = zwei_inhaber
    v_elli = _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="gleich")
    v_max = _vorschlag(db, max_, "vorgeschlagen", inhalt_hash="gleich")

    antwort = client.post(
        "/vorschlaege/uebernehmen",
        data={"vorschlag_ids": [v_elli.id, v_max.id]},
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.refresh(v_elli)
    db.refresh(v_max)
    assert v_elli.status == "uebernommen"
    assert v_max.status == "uebernommen"
    assert db.query(Deal).count() == 2
    namen = {d.inhaber.name for d in db.query(Deal).all()}
    assert namen == {"Alice", "Max"}


def test_uebernehmen_mit_teilauswahl_laesst_nicht_ausgewaehlte_offen(db, zwei_inhaber):
    """Wird nur ein Name ausgewählt, bleibt der Vorschlag für die andere
    Person offen und weiterhin sichtbar - kein automatisches Verwerfen."""
    alice, max_ = zwei_inhaber
    v_elli = _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="gleich")
    v_max = _vorschlag(db, max_, "vorgeschlagen", inhalt_hash="gleich")

    client.post("/vorschlaege/uebernehmen", data={"vorschlag_ids": [v_elli.id]}, follow_redirects=False)

    db.refresh(v_elli)
    db.refresh(v_max)
    assert v_elli.status == "uebernommen"
    assert v_max.status == "vorgeschlagen"
    assert db.query(Deal).count() == 1


def test_uebernehmen_funktioniert_auch_bei_automatisch_abgelehnt(db, inhaber):
    """Bewusstes Überstimmen laut Konzept - "Trotzdem übernehmen"."""
    vorschlag = _vorschlag(db, inhaber, "automatisch_abgelehnt")

    antwort = client.post("/vorschlaege/uebernehmen", data={"vorschlag_ids": [vorschlag.id]}, follow_redirects=False)
    assert antwort.status_code == 303
    db.refresh(vorschlag)
    assert vorschlag.status == "uebernommen"
    assert db.query(Deal).count() == 1


def test_bereits_uebernommener_vorschlag_wird_nicht_doppelt_verarbeitet(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "uebernommen")

    client.post("/vorschlaege/uebernehmen", data={"vorschlag_ids": [vorschlag.id]}, follow_redirects=False)

    assert db.query(Deal).count() == 0


def test_verwerfen_setzt_status_und_speichert_grund(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "zu_pruefen")

    antwort = client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [vorschlag.id], "gruende": ["duplikat"]},
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    db.refresh(vorschlag)
    assert vorschlag.status == "verworfen"
    assert vorschlag.verwerfen_gruende == "duplikat"
    assert db.query(Deal).count() == 0


def test_verwerfen_speichert_mehrere_gruende(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [vorschlag.id], "gruende": ["duplikat", "bedingungen_aufwendig"]},
        follow_redirects=False,
    )

    db.refresh(vorschlag)
    assert vorschlag.status == "verworfen"
    assert vorschlag.verwerfen_gruende == "duplikat,bedingungen_aufwendig"


def test_verwerfen_ohne_grund_tut_nichts(db, inhaber):
    """Ein manuelles Verwerfen braucht immer eine Begründung - ohne gültigen
    Grund bleibt der Vorschlag unverändert offen (Dialog erzwingt die Auswahl
    clientseitig, das hier ist die serverseitige Absicherung)."""
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    client.post("/vorschlaege/verwerfen", data={"vorschlag_ids": [vorschlag.id]}, follow_redirects=False)

    db.refresh(vorschlag)
    assert vorschlag.status == "vorgeschlagen"
    assert vorschlag.verwerfen_gruende is None


def test_verwerfen_ignoriert_ungueltige_gruende(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [vorschlag.id], "gruende": ["quatsch"]},
        follow_redirects=False,
    )

    db.refresh(vorschlag)
    assert vorschlag.status == "vorgeschlagen"


def test_verwerfen_mit_teilauswahl_laesst_nicht_ausgewaehlte_offen(db, zwei_inhaber):
    alice, max_ = zwei_inhaber
    v_elli = _vorschlag(db, alice, "vorgeschlagen", inhalt_hash="gleich")
    v_max = _vorschlag(db, max_, "vorgeschlagen", inhalt_hash="gleich")

    client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [v_elli.id], "gruende": ["duplikat"]},
        follow_redirects=False,
    )

    db.refresh(v_elli)
    db.refresh(v_max)
    assert v_elli.status == "verworfen"
    assert v_max.status == "vorgeschlagen"


def test_verworfener_vorschlag_taucht_nicht_mehr_bei_offenen_auf(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")
    client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [vorschlag.id], "gruende": ["duplikat"]},
        follow_redirects=False,
    )

    antwort = client.get("/vorschlaege")
    assert "0 vorgeschlagen" in antwort.text


def test_verworfener_vorschlag_zeigt_begruendung_in_eigener_sektion(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")
    client.post(
        "/vorschlaege/verwerfen",
        data={"vorschlag_ids": [vorschlag.id], "gruende": ["duplikat", "noch_nicht_neukunde"]},
        follow_redirects=False,
    )

    antwort = client.get("/vorschlaege")
    assert "1 verworfene anzeigen" in antwort.text
    assert "Duplikat" in antwort.text
    assert "Noch nicht wieder Neukunde" in antwort.text


def test_verwerfen_dialog_zeigt_alle_grund_optionen(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen")
    antwort = client.get("/vorschlaege")
    assert "Duplikat" in antwort.text
    assert "Bedingungen zu aufwendig" in antwort.text
    assert "Noch nicht wieder Neukunde" in antwort.text


def test_unbekannte_id_beim_uebernehmen_wird_ignoriert(db):
    """Bulk-Aktion: eine einzelne unbekannte ID (z.B. veralteter Formular-
    Stand) soll nicht die ganze Anfrage abbrechen."""
    antwort = client.post("/vorschlaege/uebernehmen", data={"vorschlag_ids": [999999]}, follow_redirects=False)
    assert antwort.status_code == 303
    assert client.get("/vorschlaege").status_code == 200


def test_unbekannter_vorschlag_beim_verwerfen_wird_ignoriert(db):
    antwort = client.post("/vorschlaege/verwerfen", data={"vorschlag_ids": [999999]}, follow_redirects=False)
    assert antwort.status_code == 303


def test_uebernehmen_ohne_auswahl_tut_nichts(db, inhaber):
    vorschlag = _vorschlag(db, inhaber, "vorgeschlagen")

    antwort = client.post("/vorschlaege/uebernehmen", data={}, follow_redirects=False)
    assert antwort.status_code == 303

    db.refresh(vorschlag)
    assert vorschlag.status == "vorgeschlagen"
    assert db.query(Deal).count() == 0


def test_filter_nach_quelle(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle="mydealz", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1")
    _vorschlag(
        db, inhaber, "vorgeschlagen", quelle="spartanien", quelle_url="https://www.spartanien.de/1", inhalt_hash="h2"
    )

    antwort = client.get("/vorschlaege", params={"quelle": "spartanien"})
    assert antwort.status_code == 200
    assert "1 vorgeschlagen" in antwort.text


def test_filter_nach_typ_kind_zeigt_nur_minderjaehrige(db, zwei_inhaber):
    alice, max_ = zwei_inhaber
    _vorschlag(db, alice, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1")
    _vorschlag(db, max_, "vorgeschlagen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2")

    antwort = client.get("/vorschlaege", params={"typ": "kind"})
    assert antwort.status_code == 200
    assert "1 vorgeschlagen" in antwort.text
    assert "Max" in antwort.text
    assert "Alice" not in antwort.text


def test_filter_nach_status(db, inhaber):
    _vorschlag(db, inhaber, "vorgeschlagen", quelle_url="https://www.mydealz.de/1", inhalt_hash="h1")
    _vorschlag(db, inhaber, "zu_pruefen", quelle_url="https://www.mydealz.de/2", inhalt_hash="h2")

    antwort = client.get("/vorschlaege", params={"status": "zu_pruefen"})
    assert antwort.status_code == 200
    assert "0 vorgeschlagen" in antwort.text
    assert "1 zu prüfen" in antwort.text


def test_ungueltiger_filterwert_wird_ignoriert(db, inhaber):
    """Von Hand getippte oder veraltete Filterwerte in der URL sollen die
    Seite nicht mit einem Fehler abbrechen."""
    _vorschlag(db, inhaber, "vorgeschlagen")
    antwort = client.get("/vorschlaege", params={"quelle": "unbekannt"})
    assert antwort.status_code == 200


def test_seite_ohne_bisherigen_lauf_zeigt_neutralen_hinweis(db):
    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "Noch kein Lauf durchgeführt" in antwort.text


def test_seite_zeigt_erfolgreichen_lauf(db):
    db.add(
        FinderLauf(
            erfolgreich=True,
            mydealz_geladen=5,
            spartanien_geladen=2,
            mydealz_neu=3,
            mydealz_vorhanden=1,
            mydealz_rauschen=1,
            spartanien_neu=2,
            neu_gefunden=5,
            uebersprungen=0,
            fehler=None,
        )
    )
    db.commit()

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "Letzter Lauf erfolgreich" in antwort.text
    # Tabelle: Quellen als Zeilen, die vier Kategorien als Spalten.
    assert "mydealz" in antwort.text
    assert "Spartanien" in antwort.text
    assert "Neue Vorschläge" in antwort.text
    assert "Schon vorhanden" in antwort.text
    assert "Aktualisiert" in antwort.text
    assert "Aussortiert" in antwort.text


def test_seite_zeigt_fehlgeschlagenen_lauf_mit_fehlertext(db):
    db.add(
        FinderLauf(
            erfolgreich=False,
            mydealz_geladen=0,
            spartanien_geladen=0,
            neu_gefunden=0,
            uebersprungen=0,
            fehler="mydealz nicht erreichbar: HTTP 500",
        )
    )
    db.commit()

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "Letzter Lauf fehlgeschlagen" in antwort.text
    assert "mydealz nicht erreichbar: HTTP 500" in antwort.text


def test_seite_zeigt_erfolgreichen_lauf_mit_teilfehler_als_teilweise_erfolgreich(db):
    """erfolgreich=True heißt nur: kein Absturz - fällt eine Quelle einzeln
    aus, ist das kein kompletter Fehlschlag, soll aber auch nicht wie ein
    unauffälliger Lauf aussehen."""
    db.add(
        FinderLauf(
            erfolgreich=True,
            mydealz_geladen=30,
            spartanien_geladen=0,
            neu_gefunden=92,
            uebersprungen=0,
            fehler="spartanien nicht erreichbar: Redirect response '302 Found'",
        )
    )
    db.commit()

    antwort = client.get("/vorschlaege")
    assert antwort.status_code == 200
    assert "Letzter Lauf teilweise erfolgreich" in antwort.text
    assert "spartanien nicht erreichbar" in antwort.text


def test_seite_zeigt_nur_den_juengsten_lauf(db):
    db.add(FinderLauf(erfolgreich=False, fehler="alter Fehler"))
    db.commit()
    db.add(FinderLauf(erfolgreich=True, fehler=None))
    db.commit()

    antwort = client.get("/vorschlaege")
    assert "Letzter Lauf erfolgreich" in antwort.text
    assert "alter Fehler" not in antwort.text


def test_seite_zeigt_alle_neu_analysieren_button_mit_bestaetigungsdialog(db):
    antwort = client.get("/vorschlaege")
    assert "Alle neu analysieren" in antwort.text
    # Der Bestätigungsdialog erklärt die höheren API-Kosten, bevor die
    # eigentliche Aktion (POST /vorschlaege/alle-neu-analysieren) ausgelöst wird.
    assert "erneut per KI geprüft" in antwort.text
    assert 'action="vorschlaege/alle-neu-analysieren"' in antwort.text


def test_alle_neu_analysieren_ruft_lauf_mit_ignoriere_cache_auf(monkeypatch):
    aufrufe = []

    def fake_lauf(db_arg, *, ignoriere_cache=False):
        aufrufe.append(ignoriere_cache)
        return {}

    monkeypatch.setattr("praemien_tracker.routers.vorschlaege.taeglicher_lauf", fake_lauf)

    antwort = client.post("/vorschlaege/alle-neu-analysieren", follow_redirects=False)

    assert antwort.status_code == 303
    assert aufrufe == [True]
