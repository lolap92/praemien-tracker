"""Smoke-Tests: jede Seite muss sich ausliefern lassen.

Diese Datei existiert wegen eines konkreten Fehlers: Ein neu eingeführter
Jinja-Helfer hieß wie eine Variable, die der ToDo-Router bereits übergibt, und
überschattete sie. Der Tab "Zu erledigen" lieferte dadurch nur noch einen
Serverfehler. Alle Fachlogik-Tests blieben grün - der Fehler steckte
ausschließlich im Zusammenspiel von Route, Kontext und Template.

Deshalb wird hier nichts Fachliches geprüft, sondern nur: Kommt jede Seite
durch, und stimmt die Navigationsmarkierung? Beides einmal direkt und einmal
mit Ingress-Präfix, denn im Add-on läuft die App ausschließlich dahinter.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie

# Ohne Kontextmanager läuft der lifespan nicht - die Tabellen legt bereits die
# conftest an, und die Migrationen sind hier nicht Gegenstand der Prüfung.
client = TestClient(app)

INGRESS = "/api/hassio_ingress/abcdef123456"

# (Pfad, erwarteter Navigationsreiter)
SEITEN = [
    ("overview", "overview"),
    ("todos", "todos"),
    ("deals", "deals"),
    ("deals/new", "deals"),
    ("vorschlaege", "vorschlaege"),
    ("sperrfristen", "sperrfristen"),
    ("protokoll", "protokoll"),
    ("statistiken", "statistiken"),
    ("inhaber", "inhaber"),
    ("backup", "backup"),
]


@pytest.fixture()
def deal(db):
    """Ein Deal mit allem Drum und Dran, damit die Seiten nicht nur ihren
    Leer-Zweig rendern."""
    eintrag = Deal(
        kontoart="Depot",
        kontonummer=None,
        gekuendigt=True,
        gekuendigt_im_monat="2025-03",
        kuendigung_bestaetigt=False,
        zugangsdaten_gespeichert=False,
        freibetrag=Decimal("500"),
        freibetrag_jahr=2026,
        bank=Bank(name="Testbank"),
        inhaber=Inhaber(name="Max"),
    )
    eintrag.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=False))
    eintrag.bedingungen.append(Bedingung(beschreibung="3 Trades", erfuellt=False))
    eintrag.urls.append(DealUrl(url="https://example.invalid", bezeichnung="Login"))
    db.add(eintrag)
    db.commit()
    return eintrag


def aktiver_reiter(html: str) -> str | None:
    """Findet den aktiven Reiter, egal ob er in der Desktop-Nav, der mobilen
    Tabbar oder im "Mehr"-Menü steht. Die Tabbar-Variante trägt zusätzlich
    die Klasse "tab" (class="tab on") und würde die einfache Suche nach
    class="on" doppelt treffen - deshalb zählt hier nur das exakte class="on"
    der Desktop-Nav- bzw. Mehr-Menü-Links."""
    treffer = re.search(r'<a href="([a-z/]+)" class="on"', html)
    return treffer.group(1) if treffer else None


@pytest.mark.parametrize("pfad, reiter", SEITEN)
def test_seite_liefert_html(pfad, reiter, deal):
    antwort = client.get(f"/{pfad}")
    assert antwort.status_code == 200, f"/{pfad} antwortete {antwort.status_code}"
    assert "text/html" in antwort.headers["content-type"]


@pytest.mark.parametrize("pfad, reiter", SEITEN)
def test_navigation_markiert_den_richtigen_reiter(pfad, reiter, deal):
    assert aktiver_reiter(client.get(f"/{pfad}").text) == reiter


@pytest.mark.parametrize("pfad, reiter", SEITEN)
def test_seiten_funktionieren_hinter_ingress(pfad, reiter, deal):
    """Unter Ingress trägt jeder Pfad ein wechselndes Präfix. Eine Prüfung auf
    das Pfadende allein trägt dort nicht."""
    antwort = client.get(f"/{pfad}", headers={"X-Ingress-Path": INGRESS})
    assert antwort.status_code == 200
    assert aktiver_reiter(antwort.text) == reiter


def test_deal_formular_gehoert_zum_deals_reiter(deal):
    """Unterseiten sollen ihren Oberreiter markieren."""
    antwort = client.get(f"/deals/{deal.id}/edit")
    assert antwort.status_code == 200
    assert aktiver_reiter(antwort.text) == "deals"


def test_links_oeffnen_read_only_detailseite(db, deal):
    """Prüft, dass die relevanten Navigations-Links nun auf die schreibgeschützte Detailseite statt auf edit verweisen."""
    # ToDos
    todos_html = client.get("/todos").text
    assert f'href="deals/{deal.id}"' in todos_html
    assert f'href="deals/{deal.id}/edit"' not in todos_html

    # Deal pflegen (ehemals eigene Vollständigkeits-Seite, jetzt Teil von
    # "Zu erledigen")
    pflegen_html = client.get("/todos?tab=pflegen").text
    assert f'href="deals/{deal.id}"' in pflegen_html
    # +-Chip soll weiterhin auf die Bearbeiten-Seite mit Anker springen
    assert f'href="deals/{deal.id}/edit#' in pflegen_html

    # Sperrfristen
    sperrfristen_html = client.get("/sperrfristen").text
    assert f'href="deals/{deal.id}"' in sperrfristen_html
    assert f'href="deals/{deal.id}/edit"' not in sperrfristen_html

    # Protokoll
    # Zuerst einen Eintrag im Protokoll erzeugen
    deal.kontoart = "Girokonto"
    db.add(deal)
    db.commit()
    protokoll_html = client.get("/protokoll").text
    assert f'href="deals/{deal.id}"' in protokoll_html
    assert f'href="deals/{deal.id}/edit"' not in protokoll_html


def test_startseite_leitet_auf_die_uebersicht(deal):
    antwort = client.get("/", follow_redirects=False)
    assert antwort.status_code == 303
    assert antwort.headers["location"].endswith("/overview")


def test_startseite_leitet_hinter_ingress_mit_praefix(deal):
    """Redirects löst der Browser nicht gegen <base> auf - das Präfix muss im
    Location-Header stehen."""
    antwort = client.get("/", headers={"X-Ingress-Path": INGRESS}, follow_redirects=False)
    assert antwort.headers["location"] == f"{INGRESS}/overview"


def test_export_liefert_eine_arbeitsmappe(deal):
    antwort = client.get("/deals/export.xlsx")
    assert antwort.status_code == 200
    assert "spreadsheetml" in antwort.headers["content-type"]
    assert antwort.content.startswith(b"PK")  # xlsx ist ein ZIP


def test_unbekannter_deal_liefert_eine_fehlerseite():
    antwort = client.get("/deals/999999/edit")
    assert antwort.status_code == 404
    assert "text/html" in antwort.headers["content-type"]
    assert "999999" in antwort.text


@pytest.mark.parametrize(
    "abfrage",
    ["?inhaber_id=abc", "?inhaber_id=", "?status=quatsch", "?q=", "?inhaber_id=1&status=bedingungen&q=Test"],
)
def test_filter_verkraftet_beliebige_werte(abfrage, deal):
    assert client.get(f"/deals{abfrage}").status_code == 200


@pytest.mark.parametrize("seite", ["1", "0", "-5", "9999", "abc", ""])
def test_protokoll_verkraftet_beliebige_seitenzahlen(seite, deal):
    assert client.get(f"/protokoll?seite={seite}").status_code == 200


def test_alle_todo_kategorien_rendern(db):
    """Jede Kategorie hat einen eigenen Zweig im Template - fehlt einer, wird
    der Posten stillschweigend nicht angezeigt."""
    from praemien_tracker import derived
    from praemien_tracker.routers.todos import KATEGORIE_SLUGS

    # Deal, der möglichst viele Kategorien gleichzeitig auslöst
    eintrag = Deal(
        kontoart="Depot",
        gekuendigt=True,
        gekuendigt_im_monat=None,
        kuendigung_bestaetigt=False,
        zugangsdaten_gespeichert=False,
        bank=Bank(name="Vielfalt"),
        inhaber=Inhaber(name="Max"),
    )
    eintrag.praemien.append(Praemie(quelle="bank", betrag=Decimal("10"), erhalten=False))
    eintrag.bedingungen.append(Bedingung(beschreibung="offen", erfuellt=False))
    db.add(eintrag)
    db.commit()

    antwort = client.get("/todos")
    assert antwort.status_code == 200
    for kategorie in {t.kategorie for t in derived.deal_todos(eintrag)}:
        slug = KATEGORIE_SLUGS[kategorie]
        assert f"panel-{slug}" in antwort.text, f"Kategorie {kategorie} wird nicht gerendert"


def test_uebersicht_zeigt_eigene_deal_pflegen_kachel_neben_der_pipeline(db):
    """"Deal pflegen" ist kein siebter Pipeline-Status (ein Deal kann
    gleichzeitig einen echten Status UND offene Angaben haben), taucht also
    als eigene Kachel auf - nicht als zusätzliches Pipeline-Segment."""
    eintrag = Deal(
        kontoart="Depot",
        kontonummer=None,
        bank=Bank(name="Pflegen-Uebersicht"),
        inhaber=Inhaber(name="Max"),
    )
    db.add(eintrag)
    db.commit()

    antwort = client.get("/overview")
    assert antwort.status_code == 200
    assert 'href="todos?tab=pflegen"' in antwort.text
    assert "Deal pflegen" in antwort.text


def test_jede_todo_kategorie_hat_einen_css_reiter():
    """Die Tab-Umschaltung ist im CSS pro Slug ausgeschrieben - ein neuer Slug
    ohne CSS-Eintrag wäre unsichtbar."""
    from praemien_tracker.routers.todos import KATEGORIE_SLUGS
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    for slug in KATEGORIE_SLUGS.values():
        assert f"#todotab-{slug}:checked ~ .todo-panels #panel-{slug}" in css, f"CSS fehlt für {slug}"


def test_jeder_status_hat_eine_pipeline_farbe():
    """Derselbe Fehler wie A1: die CSS-Klasse hieß anders als der Status."""
    from praemien_tracker import derived
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    for s in derived.STATUS_ORDER:
        assert f".pipe-bar-{s} {{" in css, f"Pipeline-Farbe fehlt für {s}"
        assert f".chip.status-{s} {{" in css, f"Chip-Farbe fehlt für {s}"


def test_overview_tiles_link_to_todos(deal):
    antwort = client.get("/overview")
    assert antwort.status_code == 200
    html = antwort.text
    assert 'href="todos?tab=bedingungen"' in html
    assert 'href="todos?tab=praemie"' in html
    assert 'href="todos?tab=praemie_pruefen"' in html
    assert 'href="deals?status=wartet_auf_kuendigung"' in html
    assert 'href="todos?tab=kuendigen"' in html
    assert 'href="todos?tab=bestaetigung"' in html
    assert 'href="deals?status=abgeschlossen"' in html
