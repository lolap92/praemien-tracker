# Fachliches Review – Prämien-Tracker 1.7.1

Stand: Commit `b59b65a`. Geprüft wurden Fachlogik, Frontend, der Importweg
und Inkonsistenzen zwischen Code, UI und Dokumentation. Alle mit **[V]**
markierten Punkte wurden gegen die laufende App bzw. eine echte SQLite-DB
verifiziert, nicht nur aus dem Code abgeleitet.

Priorisierung: **A** = Datenverlust/falsche fachliche Aussage,
**B** = spürbar falsches Verhalten, **C** = Politur.

---

## 0. Vorbemerkung zum CSV-Import

Es gibt **keinen CSV-Import** – weder im Code noch in der UI. Der einzige
laufende Importweg ist das Textfeld „Deal per JSON anlegen"
(`/deals/json-import`, Schema `DealImport`), und das nimmt **genau einen
Deal** je Einfügevorgang entgegen.

Der Export läuft dagegen über `.xlsx` (`export.py`). Damit ist der
Round-Trip gebrochen: Was die App ausgibt, kann sie nicht wieder einlesen –
und was sie einliest, kann sie nicht ausgeben. Das ist die größte
strukturelle Inkonsistenz der App.

Das folgende Kapitel 2 bewertet daher den bestehenden Importweg und
beschreibt am Ende, was ein CSV-Import zusätzlich braucht.

---

## 1. Fachlogik

### A1 – Fehlendes „Kündbar ab" bedeutet „sofort kündigen"
`derived.ist_kuendbar()` gibt bei `kuendbar_ab is None` **True** zurück.
Sobald alle Prämien als erhalten markiert sind, springt so ein Deal auf
Status *Kündigen* und erzeugt das ToDo „jetzt kündbar – kündigen" – obwohl
die Mindesthaltedauer schlicht nicht erfasst ist. Gleichzeitig listet der
Tab *Vollständigkeit* denselben Deal unter „Kündbar ab fehlt".

Die App fordert also an einer Stelle das Datum ein und behauptet an anderer
Stelle, es sei egal. Fachlich ist das der teuerste Fehler der App: Beim
Prämien-Hopping führt zu frühes Kündigen zum Verfall der Prämie.

*Empfehlung:* unbekanntes `kuendbar_ab` → eigener Zustand („Kündigungsdatum
klären") statt „kündigen".

### A2 – Status-Pipeline ist strikt sequenziell, die Realität nicht [V]
`derived.status()` prüft in fester Reihenfolge. Ein Deal, der bereits
`gekuendigt=True` **und** `kuendigung_bestaetigt=True` trägt, aber noch eine
nicht abgehakte Bedingung hat, ergibt:

```
status: bedingungen
ToDos:  [('Bedingungen', 'Comdirect · Max: 3 Trades'), ('Zugangsdaten', …)]
Sperrfristen: erscheint dort (Filter ist nur gekuendigt == True)
```

Derselbe Deal gilt also gleichzeitig als „in Bearbeitung" (Pipeline,
ToDo-Liste) und als „gekündigt" (Sperrfristen). Das passiert regelmäßig,
weil beim Abschluss eines Deals typischerweise Bedingungen offen bleiben,
die nie mehr abgehakt werden.

*Empfehlung:* `kuendigung_bestaetigt` als Abbruchbedingung ganz an den
Anfang von `status()` ziehen.

### A3 – Deal ohne Prämien ist eine unsichtbare Sackgasse [V]
`alle_praemien_erhalten()` liefert bei leerer Prämienliste bewusst `False`.
Der Deal bleibt damit dauerhaft in *Auf Prämie warten*. Aber:

```
praemien: []          status: praemie_warten
ToDos:    [nur 'Zugangsdaten']
offene Felder (Vollständigkeit): ['Kontonummer', 'Kündbar ab', 'Freibetrag']
```

`deal_todos()` bildet für diesen Status `offene = [p for p in deal.praemien
if not p.erhalten]` – bei leerer Liste entsteht kein ToDo. Und
`offene_felder()` prüft nur Felder am Deal und an vorhandenen Prämien, nie
„es ist überhaupt keine Prämie erfasst". Der Deal hängt also sichtbar in der
Pipeline, ohne dass irgendein Tab sagt, was zu tun ist.

*Empfehlung:* „keine Prämie erfasst" als offenes Feld in
`WUENSCHENSWERTE_FELDER`-Logik aufnehmen.

### A4 – `auszahlung_erwartet` wird eingefordert, aber nie ausgewertet
Das Feld wird in *Vollständigkeit* aktiv angemahnt, in der ToDo-Liste
angezeigt – und sonst nirgends verwendet. Es gibt **keine
Überfälligkeitsprüfung**: Eine für `2025-03` erwartete, im Juli 2026 immer
noch offene Prämie sieht in der App exakt aus wie eine für `2026-12`
erwartete.

Fachlich ist genau das das zentrale Signal beim Prämien-Hopping („Prämie
ist nicht gekommen → nachhaken, bevor die Frist der Bank abläuft").
Bedingungen und manuelle Aufgaben haben eine `ueberfaellig`-Kennzeichnung,
Prämien nicht – auch das ist eine Inkonsistenz innerhalb der ToDo-Liste.

### A5 – Freibetrag ohne fachlichen Bezugsrahmen
`overview.py` summiert `freibetrag` pro Inhaber als „genutzter Freibetrag".
Zwei Probleme:

1. **Abgeschlossene und gekündigte Deals zählen mit.** Ein 2024 gekündigtes
   Konto belegt in der Anzeige weiterhin Freibetrag.
2. **Kein Abgleich mit dem Sparer-Pauschbetrag** (1.000 € / 2.000 € bei
   Zusammenveranlagung) und kein Jahresbezug. Über alle Banken hinweg mehr
   Freistellungsaufträge zu erteilen als zulässig ist der klassische Fehler
   in diesem Anwendungsfall – die App könnte ihn erkennen, warnt aber nicht.

### B6 – „Stornieren" missbraucht `gekuendigt` und überschreibt Fakten
`deal_stornieren()` setzt `gekuendigt=True`, `kuendigung_bestaetigt=True`
und **überschreibt offene Prämienbeträge mit 0**. Folgen:

- Der ursprünglich zugesagte Betrag ist aus dem Deal verschwunden (nur noch
  im Protokoll rekonstruierbar).
- Der Deal erscheint dauerhaft im Sperrfristen-Tab unter „Gekündigt, aber
  ohne Kündigungsmonat" – obwohl er nie gekündigt, sondern nie zustande
  gekommen ist. Das verfälscht genau die Auswertung, die entscheidet, wann
  eine Bank wieder als Neukunden-Ziel taugt.

*Empfehlung:* eigenes Feld `storniert` statt Umdeutung von `gekuendigt`;
Beträge stehen lassen und in den Kennzahlen ausblenden.

### B7 – Zugangsdaten-ToDo auch für abgeschlossene Deals [V]
```
status: abgeschlossen | ToDos: [('Zugangsdaten', '… Zugangsdaten sichern')]
```
`deal_todos()` hängt das ToDo unabhängig vom Status an. Für ein gekündigtes
und bestätigtes Konto ist es gegenstandslos und bläht die Liste dauerhaft
auf.

### B8 – Toggle-Routen sind nicht idempotent
Alle Abhak-Routen in `routers/todos.py` invertieren (`a.erledigt = not
a.erledigt`). Zusammen mit den Checkboxen in `todos.html`, die **immer
unchecked gerendert** werden und per `requestSubmit()` abschicken, heißt
das: Ein Doppelklick, ein „Zurück"-Button oder ein Reload nach dem Redirect
kippt „Prämie erhalten" wieder auf `false` – ohne jede Rückmeldung. Die
Checkbox zeigt außerdem nie den tatsächlichen Zustand an.

*Empfehlung:* Zielzustand mitschicken (`wert=on|off`) statt invertieren.

### B9 – Kündigungs-Hinweise: greifen zu spät und überschreiben Geleertes [V]
Zwei getrennte Defekte in `kuendigung_hinweise.py`:

1. `backfill_kuendigung_hinweise()` läuft **ausschließlich beim Start** der
   App (`main.run_migrations()`). Ein per Formular oder JSON angelegter Deal
   bekommt seinen Hinweis daher erst beim nächsten Add-on-Neustart –
   verifiziert: direkt nach dem Import steht `hinweis=False`, obwohl
   `("Comdirect", "Depot")` hinterlegt ist. Genau dann, wenn der Hinweis
   gebraucht wird (neuer Deal), ist er nicht da.
2. Der Docstring verspricht, „vom Nutzer bearbeitete Werte werden nie
   überschrieben" – der Filter ist aber `kuendigung_hinweis.is_(None)`.
   Leert der Nutzer das Feld (die Route setzt es dann auf `None`), steht
   beim nächsten Start der Standardtext wieder drin.

Zusätzlich ist der Lookup ein exakter Tupel-Match auf
`(bank.name, kontoart)`. Schreibweisen wie `BforBank` statt des hinterlegten
`Bfor` oder `Girokonto ` mit Leerzeichen führen stillschweigend dazu, dass
gar kein Hinweis gesetzt wird (siehe A10).

---

## 2. Importweg (JSON-Textfeld)

### A10 – Keine Normalisierung: Dubletten und tote Zuordnungen [V]
Zwei Einfügevorgänge über `/deals/json-import`, einmal
`"Comdirect"/"Depot"/"Max"`, einmal `"comdirect "/" Depot"/"max"`:

```
Banken : ['Comdirect', 'comdirect']
Inhaber: ['Max', 'max']
Deal 1: bank='Comdirect' kontoart='Depot'   hinweis=False
Deal 2: bank='comdirect' kontoart=' Depot'  hinweis=False
```

Drei getrennte Defekte:

- `get_or_create_bank/-inhaber` vergleichen **case-sensitiv**. „Comdirect",
  „comdirect", „ComDirect" werden zu drei Banken, „Max" und „max" zu zwei
  Personen. Das zerlegt die Sperrfristen-Auswertung (deren ganzer Zweck der
  Vergleich pro Bank ist), die Pro-Inhaber-Tabelle inklusive
  Freibetragssumme und den Bank-Filter.
- `build_deal_from_import()` übernimmt `kontoart` **ungetrimmt**, während
  der Formularpfad (`deals.py`) `.strip()` aufruft. Zwei Anlagewege, zwei
  Ergebnisse für dieselbe Eingabe.
- Folgefehler: Der Kündigungs-Hinweis findet `(' Depot')` nicht mehr.

*Empfehlung:* Normalisierung (`strip()`, Vergleich über
`func.lower(Bank.name)`) zentral in `helpers.py`, damit sie für beide
Anlagewege gilt.

### A11 – Formularpfad validiert praktisch gar nicht [V]
```
POST /deals/new  bank='   '  inhaber='  '  kontoart='   '
→ 303, Deal angelegt: bank='' kontoart=''
```
Das HTML-`required` lässt Leerzeichen durch, und die Route strippt erst
**nach** der Prüfung (die es nicht gibt). Ergebnis: eine Bank mit leerem
Namen in der `banks`-Tabelle, die wegen `unique` von da an alle weiteren
Leereingaben einsammelt. Der JSON-Pfad validiert immerhin Typen – die
beiden Anlagewege haben also unterschiedliche Qualitätsansprüche an
dieselben Daten.

### A12 – `quelle` ist unvalidiert und wird beim Speichern still umgeschrieben [V]
`PraemieIn.quelle: str` akzeptiert jeden String; die Route
`POST /deals/{id}/praemien` ebenso. Verifiziert: `{"quelle": "Bank"}` landet
unverändert als `'Bank'` in der Datenbank.

Das `<select>` in `deal_form.html` kennt aber nur `spartanien` und `bank`.
Bei einem abweichenden Wert ist **keine** Option selektiert, der Browser
zeigt und sendet die erste Option. Wer also eine Prämie mit `"quelle":
"Bank"` importiert und den Deal danach einmal speichert, hat still und
leise eine **Spartanien**-Prämie – die Zuordnung, an der die Auswertung
hängt, kippt ohne Meldung.

*Empfehlung:* `Literal["spartanien","bank"]` im Schema, Normalisierung
(`.strip().lower()`) im Import, Ablehnung unbekannter Werte in der Route.

### B13 – Zwei Monatsformate, beides ungeprüfter Freitext
| Feld | Format | Geprüft? |
|---|---|---|
| `gekuendigt_im_monat` | `MM.YY` (`07.26`) | nur beim Lesen, `parse_gekuendigt_monat()` |
| `auszahlung_erwartet` | `YYYY-MM` (`2026-07`) | nie |

Zwei Formate für dieselbe fachliche Größe (ein Monat) in derselben Maske.
Gibt der Nutzer bei `gekuendigt_im_monat` „2026-05" ein, liefert
`parse_gekuendigt_monat()` `None` und der Deal verschwindet kommentarlos in
die Liste „Gekündigt, aber ohne Kündigungsmonat" – ohne Hinweis, dass die
Eingabe nur falsch formatiert war.

### B14 – Kein Massenimport, und die Fehlermeldung hilft nicht weiter [V]
`/deals/json-import` akzeptiert ausschließlich ein einzelnes Deal-Objekt.
Eine Liste ergibt:

```
POST json_text=[{"bank":"X","kontoart":"Depot","inhaber":"Max"}] → 400
```

Für mehrere Deals muss der Vorgang also n-mal wiederholt werden. Angezeigt
wird dabei der rohe `str(exc)` von Pydantic (`deal_form.html:125`) – ein
technischer Dump mit englischen Feldnamen und Link auf errors.pydantic.dev,
mitten in einer sonst durchgängig deutschen Oberfläche.

*Empfehlung:* zusätzlich eine Liste akzeptieren (`list[DealImport]`) und
Validierungsfehler als lesbare Zeilenliste ausgeben („Deal 2: kontoart
fehlt").

### B15 – Kein Duplikat-Schutz
Der Import prüft nicht, ob `(bank, kontoart, inhaber)` bereits existiert.
Zweimaliges Einfügen desselben JSON erzeugt zwei identische Deals, die sich
in Pipeline und Kennzahlen doppelt niederschlagen. Es gibt auch keinen
Unique-Constraint auf dieser Kombination.

### B16 – Fremdschlüssel werden nicht durchgesetzt [V]
```
PRAGMA foreign_keys = 0
→ Prämie mit deal_id=99999 (nicht existent) lässt sich anlegen
```
SQLite prüft Fremdschlüssel nur bei explizit gesetztem Pragma; `database.py`
setzt es nicht. `praemie_add()`, `bedingung_add()` u. a. prüfen ebenfalls
nicht, ob der Deal existiert. Waisen-Datensätze sind damit möglich und
tauchen in keiner Ansicht mehr auf.

### C17 – `uebersprungene_felder` ist nicht importierbar
`DealImport` kennt das Feld nicht. Wer die App neu aufsetzt oder Deals
zwischen Instanzen bewegt, muss alle „nicht nötig"-Häkchen aus dem
Vollständigkeits-Tab erneut setzen.

### Was ein CSV-Import zusätzlich bräuchte
Falls CSV das eigentliche Ziel ist, sind über die obigen Punkte hinaus
nötig: Trennzeichen- und Encoding-Erkennung (Excel-DE schreibt `;` und
CP1252), deutsches Dezimalkomma (`parse_decimal` kann das bereits, die
Pydantic-Schemas nicht), Spalten-Mapping-Vorschau, und vor allem eine
Entscheidung, wie 1:n-Daten (mehrere Prämien/Bedingungen je Deal) in einer
flachen Zeile abgebildet werden – die xlsx-Exportstruktur mit fünf Sheets
und `Deal-ID` als Klammer wäre dafür die naheliegende Vorlage und würde den
Round-Trip schließen.

---

## 3. Frontend

### B18 – Erster Pipeline-Balken ist farblos [V]
`overview.html` rendert `pipe-bar-{{ s }}`, also `pipe-bar-bedingungen`.
`style.css:264` definiert aber `.pipe-bar-cond`. Verifiziert am gerenderten
HTML – die Klasse existiert im CSS schlicht nicht, das erste Segment der
Pipeline bleibt ungefärbt. Die Status-Chips (`.chip.status-bedingungen`,
`style.css:304`) verwenden dagegen den korrekten Schlüssel: derselbe Status
heißt im CSS an zwei Stellen unterschiedlich.

### B19 – Fortschrittsbalken hat ein Segment zu wenig [V]
`deals_list.html:51` iteriert `range(5)`, es gibt aber **sechs** Status
(`STATUS_ORDER`). Für einen abgeschlossenen Deal ist `status_index == 5` –
die Bedingung `i == zeile.status_index` wird nie wahr:

```
segmente: 5 | done: 0 | on: 1     (Status „Bedingungen")
segmente: 5 | done: 1 | on: 1     (Status „Auf Prämie warten")
```
Ein abgeschlossener Deal zeigt fünf graue/grüne Segmente und **keine**
aktuelle Position. Sollte `range(status_order | length)` sein.

### B20 – „+"-Link in der Vollständigkeit führt ins Leere [V]
`completeness.html:26` verlinkt auf `deals/{id}/edit#{{ feld.feld }}`.
Gerendert wird u. a. `edit#praemie_1_auszahlung_erwartet` – ein Element mit
dieser ID gibt es in `deal_form.html` nicht (das Input trägt nur ein
`name`). Ausgerechnet das mit Abstand häufigste offene Feld hat also einen
toten Sprunglink. `#kontonummer`, `#kuendbar_ab` und `#freibetrag`
funktionieren.

### B21 – Rohe Quellen-Bezeichnung in der Vollständigkeit
`derived.offene_felder()` baut das Label mit `f"… ({p.quelle}, …)"` – roh,
also „spartanien" statt „Spartanien". Genau dieser Fix wurde in 1.6.1 für
die ToDo-Liste gemacht (`quelle_label()`), die Vollständigkeit wurde dabei
vergessen.

### B22 – Doppelte DOM-ID [V]
`deal_form.html:84/86`: `<div class="feld" id="kuendigung_hinweis">` und
darin `<textarea id="kuendigung_hinweis">`. Verifiziert am gerenderten HTML
(`2 × id="kuendigung_hinweis"`). Ungültiges HTML; `document.getElementById`
und der Anker-Sprung treffen das `div`, nicht das Eingabefeld.

### B23 – Filter wirft 500 statt zu ignorieren [V]
`GET /deals?inhaber_id=abc` → **500**. `deals_list()` macht `int(v)` ohne
Absicherung. Der Fix aus 1.7.0 hat nur den leeren Wert abgefangen
(`if v.strip()`), nicht den nicht-numerischen. Erreichbar über einen alten
Lesezeichen-Link oder manuelle URL-Eingabe.

### C24 – Aktiv-Markierung der Navigation
`base.html:15` prüft `request.url.path.endswith('tracker/')`. Unter Ingress
lautet der Pfad `/api/hassio_ingress/<token>/` – die Bedingung greift dort
nie, die Startseite markiert also keinen Tab. Zusätzlich sind die Regeln
uneinheitlich (`endswith('/overview')` vs. `'/todos' in path` vs.
`endswith('/deals')`), und Detailseiten wie `deals/3/edit` markieren gar
nichts. Sauberer wäre ein an die Templates übergebener `aktiver_tab`.

### C25 – Neuer-Deal-Route akzeptiert Felder, die das Formular nicht hat
`deal_new_create()` nimmt `kuendbar_ab`, `freibetrag`, `kommentar` und
`praemien_auf_sparkonto` entgegen. Das Neu-Formular rendert diese Felder
nicht (`{% if deal %}` ab `deal_form.html:63`) – sie sind auf diesem Weg tot
und suggerieren beim Lesen des Codes eine Funktion, die es nicht gibt.

### C26 – „Formular / JSON einfügen" ist kein Umschalter
Die beiden Buttons (`deal_form.html:29-30`) sind ein Seitenreload bzw. ein
Ankersprung; beide Blöcke sind immer sichtbar. Als Segmented Control gestylt
verhalten sie sich nicht wie eines.

### C27 – Markup und Bedienbarkeit
- `deals_list.html:38-58` und `sperrfristen.html:33-43`: `<a>` liegt direkt
  in `<ul>` ohne `<li>` – ungültiges HTML.
- `overview.html:46` / `deals_list.html:72`: `onclick="window.location=…"`
  auf `<tr>` – nicht per Tastatur erreichbar, kein Fokus, kein
  Mittelklick/„in neuem Tab öffnen".
- Die Quellen-Labels „Spartanien"/„Bank" sind dreifach gepflegt
  (`QUELLE_LABELS` sowie zwei `<select>` in `deal_form.html`).
- Kein 404-Handling: `deal_edit_form()` nutzt `.one()` → `NoResultFound` →
  Stacktrace/500 statt einer Fehlerseite. `deal_update()` ruft
  `db.get(...)` und dereferenziert ohne `None`-Prüfung.
- `protokoll.html` rendert bis zu 1000 Zeilen inklusive vollem JSON-Snapshot
  je Zeile, ohne Paginierung oder Filter – auf dem Handy die mit Abstand
  schwerste Seite der App.

---

## 4. Querschnitt

### B28 – Zeitstempel in UTC, Fälligkeiten lokal [V]
Mit `TZ=Europe/Berlin`:
```
SQLite CURRENT_TIMESTAMP (erstellt_am, protokoll.zeitpunkt): 16:31:39
Python datetime.now() (Anzeigeerwartung):                    18:31:39
```
`models.py` nutzt `server_default=func.now()` → SQLite `CURRENT_TIMESTAMP`
ist **immer UTC**, unabhängig von der Container-Zeitzone. `protokoll.html`
und der Excel-Export formatieren diese Werte ohne Umrechnung. `derived.py`
rechnet dagegen mit `datetime.date.today()`, also lokal. Das Protokoll zeigt
im Sommer 2 Stunden falsch, und Fälligkeitsvergleiche laufen auf einer
anderen Zeitbasis als die Zeitstempel.

### C29 – Sicherheitskopie wird bei jedem Start überschrieben
`run_migrations()` kopiert `praemien.db` → `praemien.db.bak` bei **jedem**
Start, auch wenn keine Migration ansteht. Wird ein Datenverlust erst nach
zwei Neustarts bemerkt, ist die Sicherung längst mit dem kaputten Stand
überschrieben. README/DOCS.md beschreiben sie als Absicherung „vor jeder
Schema-Migration" – tatsächlich ist sie an den Start gekoppelt.
*Empfehlung:* nur kopieren, wenn `command.upgrade` wirklich etwas zu tun
hat, und mit Zeitstempel im Dateinamen.

### C30 – Keine Tests
Kein einziger Test im Repo. Bei einer App, deren Kern (`derived.py`) reine,
sehr gut testbare Funktionen sind – Status, Sperrfristen, ToDo-Ableitung,
Vollständigkeit – ist das die günstigste offene Absicherung. Die Befunde
A2, A3, B7 und B19 wären mit je drei Zeilen Test aufgefallen.

### C31 – Veraltete FastAPI-API
`@app.on_event("startup")` (`main.py:81`) ist in FastAPI 0.115 deprecated;
der Nachfolger ist der `lifespan`-Kontextmanager.

---

## Empfohlene Reihenfolge

1. **A12 / A10 / A11** – Eingaben normalisieren und validieren
   (`quelle`, Bank/Inhaber case-insensitiv, `strip()`, Leereingaben).
   Hier gehen still und ohne Meldung Daten kaputt.
2. **A1 / A2** – Status-Pipeline korrigieren
3. **B18 / B19 / B20 / B21 / B23** – Frontend-Fehler; alle klein und isoliert
4. **A4 / A5** – überfällige Prämien und Freibetragsgrenze: die zwei
   fachlichen Funktionen, die dem Anwendungsfall am meisten fehlen
5. **B9 / B14** – Kündigungs-Hinweise beim Anlegen statt beim Start,
   Massenimport und lesbare Fehlermeldungen
6. **B28 / C29 / C30** – Zeitbasis, Backup-Strategie, Tests
