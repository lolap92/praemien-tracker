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

from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
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
    """Findet den aktiven Reiter - entweder in der Tabbar unten (die vier
    Hauptreiter, auf jeder Bildschirmbreite) oder im "Mehr"-Menü.

    Früher gab es zusätzlich eine Pill-Navigation oben, die nur ab 720px
    sichtbar war; seit sie entfallen ist, tragen die Hauptreiter ihre
    Markierung ausschließlich in der Tabbar (class="tab on"). Deshalb hier
    ein CSS-Selektor statt der früheren Suche nach dem exakten class="on"."""
    treffer = BeautifulSoup(html, "html.parser").select_one("nav.tabbar a.on, .nav-more-panel a.on")
    return treffer.get("href") if treffer else None


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


def test_speichern_button_im_bearbeitungsmodus_vorhanden(deal):
    """Prüft, dass der Speichern-Button im Bearbeitungsmodus eines Deals in der Appbar vorhanden ist."""
    antwort = client.get(f"/deals/{deal.id}/edit")
    assert antwort.status_code == 200
    html = antwort.text
    # Der Button soll als Speichern-Button mit der Referenz auf das Formular im Appbar-Aktionen-Block sein
    assert 'form="deal-form"' in html
    assert "Speichern" in html


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
    # "Eingeben" öffnet einen Modaldialog statt auf die Bearbeiten-Seite zu springen
    assert f'href="deals/{deal.id}/edit#' not in pflegen_html
    assert f'id="dlg-pflegen-{deal.id}"' in pflegen_html
    assert f'action="deals/{deal.id}/felder"' in pflegen_html

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


def test_unbekannte_route_liefert_html_fehlerseite():
    # Ein Routing-404 (Starlette-HTTPException) muss auf der Fehlerseite landen,
    # nicht als rohes JSON.
    antwort = client.get("/gibt-es-nicht")
    assert antwort.status_code == 404
    assert "text/html" in antwort.headers["content-type"]


def test_ungueltiger_pfadparameter_liefert_html_fehlerseite():
    # /deals/abc löst einen RequestValidationError (422) aus - der gehört
    # ebenfalls auf die Fehlerseite statt als Pydantic-JSON auf den Schirm.
    antwort = client.get("/deals/abc")
    assert antwort.status_code == 400
    assert "text/html" in antwort.headers["content-type"]
    assert "ungültigen Wert" in antwort.text


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


def test_uebersicht_zeigt_deal_pflegen_ausserhalb_von_jetzt_dran(db):
    """Fehlende Stammdaten sind eine Aufgabe ohne Frist. Sie stehen deshalb in
    der ruhigen "Nebenbei"-Zeile und nicht in "Jetzt dran" - sonst stellt die
    Pflege (meist die größte Zahl der Seite) alles Dringende in den
    Schatten."""
    eintrag = Deal(
        kontoart="Depot",
        kontonummer=None,
        bank=Bank(name="Pflegen-Uebersicht"),
        inhaber=Inhaber(name="Max"),
    )
    db.add(eintrag)
    db.commit()

    html = client.get("/overview").text
    assert 'href="todos?tab=pflegen"' in html
    assert "Deals pflegen" in html

    jetzt_dran = html.split('class="akt-liste"')[1].split("</div>")[0] if 'class="akt-liste"' in html else ""
    assert "pflegen" not in jetzt_dran


def test_jede_todo_kategorie_hat_einen_css_reiter():
    """Die Tab-Umschaltung ist im CSS pro Slug ausgeschrieben - ein neuer Slug
    ohne CSS-Eintrag wäre unsichtbar."""
    from praemien_tracker.routers.todos import KATEGORIE_SLUGS
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    for slug in KATEGORIE_SLUGS.values():
        assert f"#todotab-{slug}:checked ~ .todo-panels #panel-{slug}" in css, f"CSS fehlt für {slug}"


def test_navigation_steht_nur_in_der_tabbar(db):
    """Die vier Hauptreiter gibt es genau einmal, unten in der Tabbar - auf
    jeder Bildschirmbreite. Die frühere zweite Leiste oben (nur ab 720px
    sichtbar) ist entfallen: dieselben vier Ziele an zwei verschiedenen
    Stellen, je nach Gerät."""
    html = client.get("/overview").text
    soup = BeautifulSoup(html, "html.parser")

    assert soup.select_one("nav.desktop-nav") is None
    tabbar = soup.select_one("nav.tabbar")
    assert tabbar is not None
    ziele = [a.get("href") for a in tabbar.select("a.tab")]
    assert ziele == ["overview", "todos", "deals", "vorschlaege"]


def test_tabbar_wird_nicht_mehr_ab_720px_ausgeblendet():
    """Die Regel, die die Tabbar auf breiten Bildschirmen versteckte, ist
    weg - sonst hätte man dort gar keine Navigation mehr."""
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    assert "desktop-nav" not in css
    assert ".tabbar {\n  display: none;" not in css
    # Der Platz für die fixe Fußzeile muss auf jeder Breite freibleiben.
    assert "padding-bottom: 4.5rem;" in css


def test_jeder_status_hat_eine_chip_farbe():
    """Derselbe Fehler wie A1: die CSS-Klasse hieß anders als der Status."""
    from praemien_tracker import derived
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    for s in derived.STATUS_ORDER:
        assert f".chip.status-{s} {{" in css, f"Chip-Farbe fehlt für {s}"


def test_jede_aktionsfarbe_der_uebersicht_existiert_im_css():
    """Die Aufgabenzeilen der Startseite färben sich über .akt-<farbe>. Ein
    Tippfehler dort bliebe sonst unbemerkt: die Zeile wäre einfach grau."""
    from praemien_tracker.routers.overview import AKTION_KATEGORIEN
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    for _, _, _, farbe in AKTION_KATEGORIEN:
        assert f".akt-{farbe} .akt-num {{" in css, f"Farbe fehlt für .akt-{farbe}"


def test_overview_verlinkt_offene_aufgaben_in_die_todo_liste(deal):
    """Jede Aufgabenzeile führt genau dorthin, wo die Sache erledigt wird."""
    antwort = client.get("/overview")
    assert antwort.status_code == 200
    html = antwort.text
    assert 'href="todos?tab=bedingungen"' in html
    assert 'href="todos?tab=pruefen"' in html
    assert 'href="todos?tab=pflegen"' in html


def test_overview_zeigt_nur_kategorien_mit_offenen_punkten(deal):
    """Kern des Umbaus: Zähler, hinter denen nichts steckt, verschwinden. Die
    Fixture hat weder ein kündbares noch ein bestätigungsreifes Konto - beide
    Zeilen dürfen deshalb gar nicht erst auftauchen."""
    html = client.get("/overview").text
    aufgaben = html.split('class="akt-liste"')[1].split("</div>\n</div>")[0]
    assert "todos?tab=kuendigen" not in aufgaben
    assert "todos?tab=bestaetigung" not in aufgaben


def test_statistiken_traegt_die_zaehlungen_der_startseite(deal):
    """Die Status-, Punkte- und Vorschlagszahlen sind von der Startseite
    hierher gezogen worden - sie müssen vollständig ankommen, sonst wären sie
    beim Umbau schlicht verschwunden."""
    from praemien_tracker import derived

    html = client.get("/statistiken").text
    for status, label in derived.STATUS_LABELS.items():
        assert label in html, f"Status-Zeile fehlt: {label}"
    assert 'href="deals?status=abgeschlossen"' in html
    assert 'href="deals?status=wartet_auf_kuendigung"' in html
    for kategorie in ("Manuelle Aufgaben", "Deals pflegen", "Zu prüfen"):
        assert kategorie in html, f"Kategorie fehlt: {kategorie}"
    for status in ("vorgeschlagen", "zu_pruefen", "automatisch_abgelehnt", "verworfen"):
        assert f'href="vorschlaege?status={status}"' in html


def test_uebersicht_zaehlt_keine_zustaende_mehr(deal):
    """Gegenprobe: Zustände ohne Handlungsbedarf stehen nicht mehr auf der
    Startseite. Der Weg dorthin bleibt als Textlink erhalten."""
    html = client.get("/overview").text
    assert "deals?status=abgeschlossen" not in html
    assert "deals?status=wartet_auf_kuendigung" not in html
    assert 'href="statistiken"' in html


def test_overview_stellt_ueberfaelliges_nach_oben(db):
    """Überfälliges steht vor allem anderen und wird ausdrücklich benannt -
    vorher war einer Zahl nicht anzusehen, ob eine Frist schon verstrichen
    war."""
    import datetime

    max_ = Inhaber(name="Max")
    kuendbar = Deal(
        kontoart="Girokonto",
        kontonummer="DE1",
        zugangsdaten_gespeichert=True,
        bank=Bank(name="Kuendbar-Bank"),
        inhaber=max_,
    )
    kuendbar.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=True))

    ueberfaellig = Deal(
        kontoart="Girokonto",
        kontonummer="DE2",
        zugangsdaten_gespeichert=True,
        bank=Bank(name="Frist-Bank"),
        inhaber=max_,
    )
    ueberfaellig.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=True))
    ueberfaellig.bedingungen.append(
        Bedingung(
            beschreibung="Gehaltseingang",
            erfuellt=False,
            faellig_bis=datetime.date.today() - datetime.timedelta(days=3),
        )
    )
    db.add_all([kuendbar, ueberfaellig])
    db.commit()

    html = client.get("/overview").text
    assert "überfällig" in html
    assert html.index('href="todos?tab=bedingungen"') < html.index('href="todos?tab=kuendigen"')


def test_overview_ohne_offene_punkte_sagt_das_ausdruecklich(db):
    """Ohne Aufgaben soll die Seite das sagen, statt eine Reihe Nullen zu
    zeigen."""
    fertig = Deal(
        kontoart="Girokonto",
        kontonummer="DE3",
        gekuendigt=True,
        gekuendigt_im_monat="2025-03",
        kuendigung_bestaetigt=True,
        zugangsdaten_gespeichert=True,
        bank=Bank(name="Fertig-Bank"),
        inhaber=Inhaber(name="Max"),
    )
    fertig.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=True))
    db.add(fertig)
    db.commit()

    html = client.get("/overview").text
    assert "Nichts zu tun" in html
    assert 'class="akt-liste"' not in html


def test_deals_tabelle_bricht_um_statt_zu_scrollen(db):
    """Lange Bank- und Kontonamen sollen umbrechen, nicht die Tabelle über
    den Rand schieben: der Wrapper der Deals-Tabelle scrollt bewusst nicht
    mehr waagerecht, und die geerbte nowrap-Regel ist dort aufgehoben.

    Geprüft wird das CSS, weil sich Textumbruch ohne echtes Layout nicht aus
    dem HTML ablesen lässt - die Breiten selbst sind im Browser gemessen."""
    from praemien_tracker.templating import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    assert ".deals-tabelle .tabelle-wrapper {\n  overflow-x: visible;\n}" in css
    assert "white-space: normal;" in css
    assert "overflow-wrap: anywhere;" in css


def test_deals_tabelle_haelt_betraege_und_datum_einzeilig(deal):
    """Zahlen sind umbrochen schwerer zu lesen - Geld- und Datumsspalte
    tragen deshalb eine eigene Klasse, an der das nowrap hängt."""
    html = client.get("/deals").text
    assert 'class="geld"' in html
    assert 'class="datum"' in html
