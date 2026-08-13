from __future__ import annotations

import datetime
from decimal import Decimal
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from praemien_tracker.main import app
from praemien_tracker.models import Aufgabe, Bank, Bedingung, Deal, Inhaber, Praemie

client = TestClient(app)

def test_todos_sorting_and_filtering(db):
    # Setup test data
    bank = Bank(name="Test Bank")
    inhaber = Inhaber(name="Max Mustermann")
    db.add_all([bank, inhaber])
    db.commit()

    # Deal 1: Spartanien Deal with a premium waiting
    deal_spartanien = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Giro",
        kontonummer="DE1111",
        zugangsdaten_gespeichert=True
    )
    # This premium is from Spartanien, next check in 5 days
    p_spartanien = Praemie(
        quelle="spartanien",
        betrag=Decimal("50.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=5)
    )
    deal_spartanien.praemien.append(p_spartanien)

    # Deal 2: Bank Deal with a premium waiting (earlier check date)
    deal_bank = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Depot",
        kontonummer="DE2222",
        zugangsdaten_gespeichert=True
    )
    # This premium is from Bank, next check in 2 days
    p_bank = Praemie(
        quelle="bank",
        betrag=Decimal("100.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=2)
    )
    deal_bank.praemien.append(p_bank)

    db.add_all([deal_spartanien, deal_bank])
    db.commit()

    # 1. Test Sorting: Earlier check date should come first
    antwort = client.get("/todos")
    assert antwort.status_code == 200
    html = antwort.text

    # "Bank" premium is 2 days out, "Spartanien" is 5 days out.
    # Therefore, "Bank" should appear before "Spartanien" in the HTML.
    idx_bank = html.find("Prämie prüfen (Bank, 100.00 €)")
    idx_spartanien = html.find("Prämie prüfen (Spartanien, 50.00 €)")
    assert idx_bank != -1
    assert idx_spartanien != -1
    assert idx_bank < idx_spartanien, "Bank (2 days) should be listed before Spartanien (5 days)"

    # 2. Test Filtering by "spartanien"
    antwort_spartanien = client.get("/todos?quelle=spartanien")
    assert antwort_spartanien.status_code == 200
    html_spartanien = antwort_spartanien.text
    assert "Prämie prüfen (Spartanien, 50.00 €)" in html_spartanien
    assert "Prämie prüfen (Bank, 100.00 €)" not in html_spartanien

    # 3. Test Filtering by "bank"
    antwort_bank = client.get("/todos?quelle=bank")
    assert antwort_bank.status_code == 200
    html_bank = antwort_bank.text
    assert "Prämie prüfen (Spartanien, 50.00 €)" not in html_bank
    assert "Prämie prüfen (Bank, 100.00 €)" in html_bank


def test_todos_filtering_by_new_statuses(db):
    # Setup test data
    bank = Bank(name="Test Bank 2")
    inhaber = Inhaber(name="Max Mustermann 2")
    db.add_all([bank, inhaber])
    db.commit()

    # Deal 1: "Prämienauszahlung prüfen" because check date is reached
    deal_pruefen = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Giro",
        kontonummer="DE3333",
        zugangsdaten_gespeichert=True
    )
    p_pruefen = Praemie(
        quelle="spartanien",
        betrag=Decimal("150.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() - datetime.timedelta(days=1)  # reached (yesterday)
    )
    deal_pruefen.praemien.append(p_pruefen)

    # Deal 2: "Auf Prämie warten" because check date is in the future
    deal_warten = Deal(
        bank_id=bank.id,
        inhaber_id=inhaber.id,
        kontoart="Depot",
        kontonummer="DE4444",
        zugangsdaten_gespeichert=True
    )
    p_warten = Praemie(
        quelle="bank",
        betrag=Decimal("200.00"),
        erhalten=False,
        auszahlung_erwartet="2026-08",
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=10)  # in future
    )
    deal_warten.praemien.append(p_warten)

    db.add_all([deal_pruefen, deal_warten])
    db.commit()

    # Get /todos
    antwort = client.get("/todos")
    assert antwort.status_code == 200
    html = antwort.text

    # Verify both categories show up as tabs / panels
    assert "Prämienauszahlung prüfen" in html
    assert "Auf Prämie warten" in html

    # Verify the specific texts are present in the HTML response
    assert "Prämie prüfen (Spartanien, 150.00 €)" in html
    assert "Prämie prüfen (Bank, 200.00 €)" in html

    # Test filtering by source: Spartanien
    antwort_spartanien = client.get("/todos?quelle=spartanien")
    html_spartanien = antwort_spartanien.text
    assert "Prämie prüfen (Spartanien, 150.00 €)" in html_spartanien
    assert "Prämie prüfen (Bank, 200.00 €)" not in html_spartanien

    # Test filtering by source: Bank
    antwort_bank = client.get("/todos?quelle=bank")
    html_bank = antwort_bank.text
    assert "Prämie prüfen (Spartanien, 150.00 €)" not in html_bank
    assert "Prämie prüfen (Bank, 200.00 €)" in html_bank


def test_manuelle_aufgaben_tab_bleibt_ohne_offene_aufgabe_erreichbar(db):
    """Ohne jede offene manuelle Aufgabe (und ohne Deals) muss der Tab
    trotzdem existieren - er ist die einzige Stelle, an der sich die erste
    Aufgabe anlegen lässt (siehe todos.py: gruppen.setdefault)."""
    antwort = client.get("/todos")
    assert antwort.status_code == 200
    assert 'id="todotab-manuell"' in antwort.text
    assert 'id="panel-manuell"' in antwort.text
    # Ohne echten Inhalt sonst nirgendwo ist "Manuelle Aufgaben" der Default-Tab.
    assert 'id="todotab-manuell" checked' in antwort.text


def test_default_tab_ist_erste_kategorie_mit_inhalt_nicht_manuelle_aufgaben(db):
    """Gibt es woanders echten Inhalt, gewinnt der (in der Reihenfolge erste)
    damit - nicht die leere 'Manuelle Aufgaben'-Kachel, obwohl sie zuerst in
    KATEGORIE_REIHENFOLGE steht und jetzt immer sichtbar ist."""
    bank = Bank(name="Default-Tab-Testbank")
    inhaber = Inhaber(name="Default-Tab-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer="DE1", zugangsdaten_gespeichert=True)
    deal.bedingungen.append(Bedingung(beschreibung="offen", erfuellt=False))
    db.add(deal)
    db.commit()

    antwort = client.get("/todos")
    assert 'id="todotab-bedingungen" checked' in antwort.text
    assert 'id="todotab-manuell" checked' not in antwort.text


def test_neue_aufgabe_und_erledigte_aufgaben_stecken_im_manuell_tab(db):
    """Beide Blöcke tragen die CSS-Klasse, die sie an den 'manuell'-Tab
    bindet (siehe body:has(#todotab-manuell:checked) in style.css) - das
    HTML selbst liefert der Server immer, die Sichtbarkeit regelt reines CSS.
    "Neue Aufgabe" ist zusätzlich ein <details> hinter einem Button-Umschalter
    (per default eingeklappt, kein dauerhaft offenes Formular mehr)."""
    db.add(Aufgabe(beschreibung="Erledigt", erledigt=True))
    db.commit()

    antwort = client.get("/todos")
    assert '<details class="neue-aufgabe-card">' in antwort.text
    assert "+ Neue Aufgabe" in antwort.text
    assert 'class="card erledigte-aufgaben-card"' in antwort.text
    assert "Erledigte Aufgaben" in antwort.text


def test_quelle_filter_traegt_css_klasse_fuer_praemien_tabs(db):
    """Der Quelle-Filter bekommt dieselbe Bindung wie die Aufgaben-Karten,
    nur an die beiden Prämien-Tabs statt an 'manuell' (siehe style.css). Es
    gibt zwei Formulare - je eins pro Prämien-Tab, siehe
    test_filtern_bleibt_auf_dem_jeweiligen_praemien_tab für den Grund."""
    antwort = client.get("/todos")
    assert 'class="filterleiste todo-quelle-filter todo-quelle-filter-praemie"' in antwort.text
    assert 'class="filterleiste todo-quelle-filter todo-quelle-filter-praemie_pruefen"' in antwort.text


def test_quelle_filter_steht_hinter_den_kacheln_vor_den_todos(db):
    """Der Filter soll unter der Status-Kachel-Navigation stehen, aber über
    dem eigentlichen ToDo-Inhalt - also im Markup nach .todo-tabs-nav und vor
    .todo-panels. Geprüft am ersten der beiden Filter-Formulare."""
    antwort = client.get("/todos")
    html = antwort.text
    idx_kacheln = html.index('class="todo-tabs-nav"')
    idx_filter = html.index('class="filterleiste todo-quelle-filter todo-quelle-filter-praemie"')
    idx_panels = html.index('class="todo-panels"')
    assert idx_kacheln < idx_filter < idx_panels


def test_neue_aufgabe_button_steht_hinter_den_kacheln_vor_den_todos(db):
    """Analog zum Quelle-Filter: der "+ Neue Aufgabe"-Umschalter steht unter
    der Status-Kachel-Navigation und über dem eigentlichen ToDo-Inhalt, nicht
    mehr ganz oben vor den Kacheln."""
    antwort = client.get("/todos")
    html = antwort.text
    idx_kacheln = html.index('class="todo-tabs-nav"')
    idx_neue_aufgabe = html.index('<details class="neue-aufgabe-card">')
    idx_panels = html.index('class="todo-panels"')
    assert idx_kacheln < idx_neue_aufgabe < idx_panels


# ---------------------------------------------------------------------------
# Bug 1: eine Prämien-Kachel verschwand komplett, sobald der Quelle-Filter
# ihren einzigen Eintrag ausblendete - obwohl die Kategorie ungefiltert
# durchaus existierte. Von dort aus ließ sich der Filter dann nicht mehr
# zurücksetzen. Fix: die Kachel bleibt (mit Zähler 0) sichtbar, wenn es dafür
# OHNE den Quelle-Filter Einträge gäbe (siehe todos.py:
# kategorien_mit_inhalt_ungefiltert). Nachschlag: das gilt inzwischen für
# ALLE Kategorien, nicht nur die beiden Prämien-Tabs - siehe
# test_alle_kacheln_bleiben_ohne_jeden_inhalt_sichtbar_und_ausgegraut unten.
# ---------------------------------------------------------------------------


def test_praemien_kachel_bleibt_bei_quelle_filter_auf_null_sichtbar(db):
    bank = Bank(name="Kachel-Testbank")
    inhaber = Inhaber(name="Kachel-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()

    # Einzige faellige Praemie kommt von Spartanien.
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", zugangsdaten_gespeichert=True)
    deal.praemien.append(Praemie(
        quelle="spartanien", betrag=Decimal("42.00"), erhalten=False,
        naechste_pruefung_am=datetime.date.today() - datetime.timedelta(days=1),
    ))
    db.add(deal)
    db.commit()

    ohne_filter = client.get("/todos")
    assert 'id="todotab-praemie_pruefen"' in ohne_filter.text

    # quelle=bank blendet den einzigen (Spartanien-)Eintrag aus - die Kachel
    # selbst darf dabei nicht verschwinden.
    mit_filter = client.get("/todos?quelle=bank")
    assert mit_filter.status_code == 200
    assert 'id="todotab-praemie_pruefen"' in mit_filter.text
    assert "Prämienauszahlung prüfen" in mit_filter.text
    assert "Nichts für diese Quelle." in mit_filter.text
    assert "42.00" not in mit_filter.text


def test_praemien_kachel_bleibt_auch_bei_wirklich_leerer_kategorie_sichtbar(db):
    """Existiert die Kategorie auch ungefiltert nicht (keine einzige
    fällige/wartende Prämie), bleibt die Kachel trotzdem sichtbar - nur als
    ausgegraut markiert (todo-tab-leer), statt ganz zu verschwinden."""
    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")

    assert soup.select_one("#todotab-praemie_pruefen") is not None
    assert soup.select_one("#todotab-praemie") is not None

    label = soup.select_one('label[for="todotab-praemie_pruefen"]')
    assert label is not None
    assert "todo-tab-leer" in label.get("class", [])

    panel = soup.select_one("#panel-praemie_pruefen")
    assert panel is not None
    assert "Aktuell nichts offen." in panel.get_text()


def test_praemien_kachel_nicht_ausgegraut_wenn_nur_gefiltert_leer(db):
    """Hat die Kategorie ungefiltert Inhalt und wird nur durch den
    Quelle-Filter geleert, bleibt sie normal (nicht ausgegraut) - das
    unterscheidet "wirklich leer" von "nur gerade rausgefiltert"."""
    bank = Bank(name="Ausgrau-Testbank")
    inhaber = Inhaber(name="Ausgrau-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", zugangsdaten_gespeichert=True)
    deal.praemien.append(Praemie(
        quelle="spartanien", betrag=Decimal("33.00"), erhalten=False,
        naechste_pruefung_am=datetime.date.today() - datetime.timedelta(days=1),
    ))
    db.add(deal)
    db.commit()

    antwort = client.get("/todos?quelle=bank")
    soup = BeautifulSoup(antwort.text, "html.parser")
    label = soup.select_one('label[for="todotab-praemie_pruefen"]')
    assert label is not None
    assert "todo-tab-leer" not in label.get("class", [])


def test_filtern_leert_nur_die_betroffene_praemien_kachel_nicht_beide(db):
    """Zwei Deals mit unterschiedlicher Quelle in je einer der beiden
    Prämien-Kategorien: quelle=bank filtern darf nur die Spartanien-Kategorie
    leeren (Kachel bleibt aber da), die Bank-Kategorie behält ihren Inhalt."""
    bank = Bank(name="Gemischt-Testbank")
    inhaber = Inhaber(name="Gemischt-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()

    faellig_spartanien = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", zugangsdaten_gespeichert=True)
    faellig_spartanien.praemien.append(Praemie(
        quelle="spartanien", betrag=Decimal("77.00"), erhalten=False,
        naechste_pruefung_am=datetime.date.today() - datetime.timedelta(days=1),
    ))
    wartend_bank = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Depot", zugangsdaten_gespeichert=True)
    wartend_bank.praemien.append(Praemie(
        quelle="bank", betrag=Decimal("88.00"), erhalten=False,
        naechste_pruefung_am=datetime.date.today() + datetime.timedelta(days=10),
    ))
    db.add_all([faellig_spartanien, wartend_bank])
    db.commit()

    antwort = client.get("/todos?quelle=bank")
    assert 'id="todotab-praemie_pruefen"' in antwort.text  # Kachel bleibt trotz leerem Inhalt
    assert 'id="todotab-praemie"' in antwort.text
    assert "77.00" not in antwort.text  # Spartanien rausgefiltert
    assert "88.00" in antwort.text  # Bank bleibt


# ---------------------------------------------------------------------------
# Bug 2: "Filtern" sprang immer auf "Manuelle Aufgaben", weil das versteckte
# tab-Feld den beim SEITENAUFRUF aktiven Tab enthielt - ein Tab-Wechsel ist
# aber rein clientseitig (CSS-Radio ohne Navigation), sodass dieser Wert beim
# Absenden meist nicht mehr dem gerade sichtbaren Tab entsprach. Fix: zwei
# eigene Formulare mit je fest eingetragenem tab_slug (siehe
# todos.html: quelle_filter-Makro).
# ---------------------------------------------------------------------------


def test_filter_formulare_tragen_je_ihren_eigenen_tab_fest_eingetragen(db):
    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")

    form_praemie = soup.select_one("form.todo-quelle-filter-praemie")
    form_praemie_pruefen = soup.select_one("form.todo-quelle-filter-praemie_pruefen")
    assert form_praemie is not None
    assert form_praemie_pruefen is not None

    tab_feld_praemie = form_praemie.select_one('input[name="tab"]')
    tab_feld_pruefen = form_praemie_pruefen.select_one('input[name="tab"]')
    assert tab_feld_praemie["value"] == "praemie"
    assert tab_feld_pruefen["value"] == "praemie_pruefen"


def test_alle_kacheln_bleiben_ohne_jeden_inhalt_sichtbar_und_ausgegraut(db):
    """Nicht nur die beiden Prämien-Kacheln, sondern alle acht Kategorien
    bleiben immer als Kachel da - ganz ohne Deals/Aufgaben sind sie alle
    wirklich leer und deshalb alle ausgegraut (todo-tab-leer), auch
    'Manuelle Aufgaben'. Der "+ Neue Aufgabe"-Button steckt ohnehin dahinter
    und bleibt unabhängig davon normal nutzbar."""
    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")

    alle_slugs = {"manuell", "pflegen", "bedingungen", "praemie", "praemie_pruefen", "kuendigen", "bestaetigung", "pruefen"}
    for slug in alle_slugs:
        assert soup.select_one(f"#todotab-{slug}") is not None, slug
        label = soup.select_one(f'label[for="todotab-{slug}"]')
        assert label is not None, slug
        assert "todo-tab-leer" in label.get("class", []), slug


def test_filtern_bleibt_auf_dem_jeweiligen_praemien_tab(db):
    """Sendet man genau das Formular ab, das zum Tab 'Prämienauszahlung
    prüfen' gehört (fester tab=praemie_pruefen), zeigt die Antwort wieder
    genau diesen Tab aktiv - unabhängig davon, welcher Tab beim vorherigen
    Seitenaufruf berechnet worden wäre."""
    bank = Bank(name="Filtern-Testbank")
    inhaber = Inhaber(name="Filtern-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", zugangsdaten_gespeichert=True)
    deal.praemien.append(Praemie(
        quelle="bank", betrag=Decimal("5.00"), erhalten=False,
        naechste_pruefung_am=datetime.date.today() - datetime.timedelta(days=1),
    ))
    db.add(deal)
    db.commit()

    antwort = client.get("/todos?tab=praemie_pruefen&quelle=bank")
    assert 'id="todotab-praemie_pruefen" checked' in antwort.text


# ---------------------------------------------------------------------------
# "Deal pflegen": Zusammenführung der früheren Vollständigkeits-Seite mit der
# alten "Zugangsdaten"-ToDo-Kategorie zu einer einzigen ToDo-Kategorie mit
# Feld-Chips (+ befüllen, × nicht nötig) statt einer einzelnen Checkbox.
# ---------------------------------------------------------------------------


def test_deal_pflegen_zeigt_alle_offenen_felder_als_chips(db):
    bank = Bank(name="Pflegen-Testbank")
    inhaber = Inhaber(name="Pflegen-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer=None, zugangsdaten_gespeichert=False)
    deal.praemien.append(Praemie(quelle="bank", betrag=Decimal("50.00"), erhalten=False, auszahlung_erwartet=None))
    db.add(deal)
    db.commit()

    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")

    panel = soup.select_one("#panel-pflegen")
    assert panel is not None
    chips = {mf.get_text(strip=True).rstrip("+×") for mf in panel.select(".miss .mf")}
    assert any("Kontonummer" in c for c in chips)
    assert any("Zugangsdaten sichern" in c for c in chips)
    assert any("Erwartete Auszahlung" in c for c in chips)

    plus_link = panel.select_one('a.plus[href*="kontonummer"]')
    assert plus_link is not None
    assert plus_link["href"] == f"deals/{deal.id}/edit#kontonummer"


def test_deal_pflegen_skip_field_entfernt_den_chip_und_bleibt_beim_pflegen_tab(db):
    bank = Bank(name="Skip-Testbank")
    inhaber = Inhaber(name="Skip-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer=None, zugangsdaten_gespeichert=True)
    db.add(deal)
    db.commit()

    antwort = client.post(f"/deals/{deal.id}/skip-field", data={"feld": "kontonummer"}, follow_redirects=False)
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/todos?tab=pflegen"

    folgeantwort = client.get(antwort.headers["location"])
    assert 'id="todotab-pflegen" checked' in folgeantwort.text
    assert "Kontonummer" not in (BeautifulSoup(folgeantwort.text, "html.parser").select_one("#panel-pflegen").get_text())


def test_deal_pflegen_gekuendigter_deal_braucht_keine_zugangsdaten(db):
    """Isoliert von der Kontonummer, die für sich schon 'offen' wäre."""
    bank = Bank(name="Gekuendigt-Testbank")
    inhaber = Inhaber(name="Gekuendigt-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(
        bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro",
        kontonummer="DE1", zugangsdaten_gespeichert=False, gekuendigt=True,
    )
    db.add(deal)
    db.commit()

    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")
    label = soup.select_one('label[for="todotab-pflegen"]')
    assert "todo-tab-leer" in label.get("class", [])


def test_deal_pflegen_renders_feld_filter(db):
    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")

    form_pflegen = soup.select_one("form.todo-feld-filter-pflegen")
    assert form_pflegen is not None

    tab_feld_pflegen = form_pflegen.select_one('input[name="tab"]')
    assert tab_feld_pflegen["value"] == "pflegen"

    options = {opt.get("value") for opt in form_pflegen.select('input[name="feld"]')}
    assert "" in options
    assert "kontonummer" in options
    assert "zugangsdaten_gespeichert" in options
    assert "auszahlung_erwartet" in options


def test_deal_pflegen_filtering_by_feld(db):
    bank = Bank(name="FilterFeld-Bank")
    inhaber = Inhaber(name="FilterFeld-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()

    # Create a deal that needs maintaining of all three fields
    deal = Deal(bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro", kontonummer=None, zugangsdaten_gespeichert=False)
    deal.praemien.append(Praemie(quelle="bank", betrag=Decimal("100.00"), erhalten=False, auszahlung_erwartet=None))
    db.add(deal)
    db.commit()

    # 1. Unfiltered: should show all three chips
    antwort_all = client.get("/todos")
    soup_all = BeautifulSoup(antwort_all.text, "html.parser")
    panel_all = soup_all.select_one("#panel-pflegen")
    chips_all = {mf.get_text(strip=True).rstrip("+×") for mf in panel_all.select(".miss .mf")}
    assert "Kontonummer" in chips_all
    assert "Zugangsdaten sichern" in chips_all
    assert "Erwartete Auszahlung (Bank, 100.00 €)" in chips_all

    # 2. Filtered by kontonummer
    antwort_kto = client.get("/todos?feld=kontonummer")
    soup_kto = BeautifulSoup(antwort_kto.text, "html.parser")
    panel_kto = soup_kto.select_one("#panel-pflegen")
    chips_kto = {mf.get_text(strip=True).rstrip("+×") for mf in panel_kto.select(".miss .mf")}
    assert "Kontonummer" in chips_kto
    assert "Zugangsdaten sichern" not in chips_kto
    assert "Erwartete Auszahlung (Bank, 100.00 €)" not in chips_kto

    # 3. Filtered by zugangsdaten_gespeichert
    antwort_zd = client.get("/todos?feld=zugangsdaten_gespeichert")
    soup_zd = BeautifulSoup(antwort_zd.text, "html.parser")
    panel_zd = soup_zd.select_one("#panel-pflegen")
    chips_zd = {mf.get_text(strip=True).rstrip("+×") for mf in panel_zd.select(".miss .mf")}
    assert "Kontonummer" not in chips_zd
    assert "Zugangsdaten sichern" in chips_zd
    assert "Erwartete Auszahlung (Bank, 100.00 €)" not in chips_zd

    # 4. Filtered by auszahlung_erwartet
    antwort_ae = client.get("/todos?feld=auszahlung_erwartet")
    soup_ae = BeautifulSoup(antwort_ae.text, "html.parser")
    panel_ae = soup_ae.select_one("#panel-pflegen")
    chips_ae = {mf.get_text(strip=True).rstrip("+×") for mf in panel_ae.select(".miss .mf")}
    assert "Kontonummer" not in chips_ae
    assert "Zugangsdaten sichern" not in chips_ae
    assert "Erwartete Auszahlung (Bank, 100.00 €)" in chips_ae


def test_deal_pflegen_abgeschlossener_deal_erscheint_nicht(db):
    bank = Bank(name="Abgeschlossen-Testbank")
    inhaber = Inhaber(name="Abgeschlossen-Inhaber")
    db.add_all([bank, inhaber])
    db.commit()
    deal = Deal(
        bank_id=bank.id, inhaber_id=inhaber.id, kontoart="Giro",
        kontonummer=None, gekuendigt=True, kuendigung_bestaetigt=True,
    )
    db.add(deal)
    db.commit()

    antwort = client.get("/todos")
    soup = BeautifulSoup(antwort.text, "html.parser")
    label = soup.select_one('label[for="todotab-pflegen"]')
    assert "todo-tab-leer" in label.get("class", [])
