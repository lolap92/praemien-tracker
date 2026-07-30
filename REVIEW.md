# Fachliches Review – Prämien-Tracker 1.7.1

Stand: Commit `b59b65a`. Geprüft wurden Fachlogik, Frontend, der Importweg
und Inkonsistenzen zwischen Code, UI und Dokumentation. Alle mit **[V]**
markierten Punkte wurden gegen die laufende App bzw. eine echte SQLite-DB
verifiziert, nicht nur aus dem Code abgeleitet.

Die Findings sind nach Umsetzbarkeit nummeriert:

- **A1–A17** – sofort umsetzbar, keine Änderung an der Fachlogik.
- **B1–B15** – vorher anschauen, weil eine fachliche Entscheidung,
  eine Datenmigration oder eine spürbare Verhaltensänderung dranhängt.

Die Spalte *Prio* in den Übersichtstabellen gibt den Schweregrad an:
**hoch** = Datenverlust oder falsche fachliche Aussage, **mittel** =
spürbar falsches Verhalten, **niedrig** = Politur.

---

## Umsetzungs-Übersicht

### A – sofort umsetzbar (keine Logikänderung)

| # | Prio | Finding | Stelle | Warum unbedenklich |
|---|---|---|---|---|
| A1 | mittel | Erster Pipeline-Balken farblos: Template rendert `pipe-bar-bedingungen`, CSS kennt nur `.pipe-bar-cond` | `style.css:264` | Reiner Namensdreher, ein Wort |
| A2 | mittel | Fortschrittsbalken hat 5 statt 6 Segmente, „Abgeschlossen" zeigt nie eine Position | `deals_list.html:51` | `range(5)` → `range(status_order\|length)` |
| A3 | mittel | „+"-Sprunglink der Vollständigkeit zeigt auf nicht existierende ID | `deal_form.html:149` | `id="praemie_{{p.id}}_auszahlung_erwartet"` ergänzen |
| A4 | mittel | „spartanien" statt „Spartanien" in der Vollständigkeit | `derived.py:267` | `quelle_label()` anwenden, existiert bereits |
| A5 | mittel | Doppelte DOM-ID `kuendigung_hinweis` (div + textarea) | `deal_form.html:84` | ID am `div` entfernen |
| A6 | mittel | `?inhaber_id=abc` → 500 | `deals.py:42` | `int()` absichern, nicht-numerisch ignorieren |
| A7 | niedrig | Nav-Aktivmarkierung greift unter Ingress nie, Regeln uneinheitlich | `base.html:15-21` | `aktiver_tab` aus der Route übergeben |
| A8 | niedrig | `deal_new_create()` nimmt 4 Felder entgegen, die das Formular nie sendet | `deals.py:109` | Toter Code, ersatzlos raus |
| A9 | niedrig | „Formular / JSON einfügen" sieht aus wie ein Umschalter, ist aber Reload + Ankersprung | `deal_form.html:29` | Reine UI-Politur |
| A10 | niedrig | `<a>` direkt in `<ul>`, `onclick` auf `<tr>` (nicht tastaturbedienbar), 500 statt 404 bei unbekannter Deal-ID, Protokoll ohne Paginierung | mehrere Templates, `deals.py:170` | Markup/Robustheit, kein Verhalten betroffen |
| A11 | niedrig | `@app.on_event("startup")` deprecated | `main.py:81` | 1:1-Ersatz durch `lifespan` |
| A12 | mittel | `PRAGMA foreign_keys` ist aus → Waisen-Datensätze möglich | `database.py:6` | Verhindert nur neue Verstöße. Vorher einmal auf vorhandene Waisen prüfen |
| A13 | hoch | `kontoart` wird im Importpfad nicht getrimmt, im Formularpfad schon | `helpers.py:58` | Gleicht Import an das bereits bestehende Verhalten an |
| A14 | hoch | Eingabe aus lauter Leerzeichen legt Deal mit leerer Bank an | `deals.py:123` | Vor der Prüfung strippen, Leeres ablehnen. Braucht eine kleine Fehlermeldung im Formular |
| A15 | niedrig | `uebersprungene_felder` nicht importierbar | `schemas.py:36` | Rein additives Feld |
| A16 | mittel | Import nimmt nur ein Objekt (Liste → 400); Fehler kommt als roher Pydantic-Dump | `deals.py:139`, `deal_form.html:125` | Additiv, bestehendes Verhalten bleibt gültig |
| A17 | niedrig | Keine Tests | – | Ergänzt nur, ändert nichts |

### B – vorher anschauen (fachliche Entscheidung)

| # | Prio | Finding | Was zu entscheiden ist |
|---|---|---|---|
| B1 | niedrig | Vollständigkeit mahnt „Kündbar ab" an, obwohl ein leeres Feld eine gültige Aussage ist („keine Sperrfrist") | Feld aus `WUENSCHENSWERTE_FELDER` nehmen, oder die Erinnerung bewusst behalten? |
| B2 | hoch | Gekündigt + bestätigt, aber offene Bedingung → gilt gleichzeitig als „in Bearbeitung" und „gekündigt" | **Entschieden**, siehe „Beschlossen: Bereich Zu prüfen". Noch nicht umgesetzt |
| B3 | hoch | Deal ohne Prämien hängt unsichtbar in „Auf Prämie warten" – kein ToDo, keine Meldung | **Entschieden**, siehe „Beschlossen: Bereich Zu prüfen". Noch nicht umgesetzt |
| B4 | hoch | `auszahlung_erwartet` wird eingefordert, aber nie ausgewertet – keine Überfälligkeit | Ab wann gilt eine Prämie als überfällig? Neue ToDo-Kategorie oder Markierung? |
| B5 | hoch | Freibetragssumme zählt gekündigte Deals mit, kein Bezug zum Sparer-Pauschbetrag | Nur aktive Deals? Grenze 1.000/2.000 € je Person pflegbar machen? Jahresbezug? |
| B6 | mittel | „Stornieren" setzt `gekuendigt=True` und überschreibt Prämienbeträge mit 0 | Eigenes Feld `storniert`? Migration + Sperrfristen-Filter betroffen |
| B7 | mittel | Zugangsdaten-ToDo erscheint auch für abgeschlossene Deals | Ab welchem Status entfällt es – ab „gekündigt" oder ab „bestätigt"? |
| B8 | mittel | Abhak-Routen invertieren; Doppelklick/Zurück-Button kippt „Prämie erhalten" zurück | Zielzustand mitschicken heißt auch: Checkboxen sollen den Ist-Zustand zeigen. Ändert die Bedienung spürbar |
| B9 | mittel | Kündigungs-Hinweise greifen nur beim App-Start (neuer Deal bleibt leer) und überschreiben bewusst geleerte Felder | Beim Anlegen anwenden? Und wie „bewusst leer" von „nie gesetzt" unterscheiden? |
| B10 | hoch | Bank/Inhaber case-sensitiv → „Comdirect"/„comdirect", „Max"/„max" werden zu je zwei Einträgen | Bestehende Dubletten müssen zusammengeführt werden – Datenmigration, nicht rückholbar |
| B11 | hoch | `quelle` unvalidiert; „Bank" wird beim nächsten Speichern still zu „Spartanien" | Normalisierung ist trivial, aber vorhandene Zeilen müssen einmalig bereinigt werden – und unbekannte Werte künftig ablehnen heißt, Importe abzuweisen |
| B12 | mittel | Zwei Monatsformate (`MM.YY` vs. `YYYY-MM`), beide ungeprüft | Auf ein Format vereinheitlichen? Betrifft bestehende Daten |
| B13 | mittel | Kein Duplikat-Schutz – zweimal dasselbe JSON = zwei Deals | Warnen oder blocken? Ist `(Bank, Kontoart, Inhaber)` wirklich eindeutig, oder gibt es legitim zwei gleiche Konten? |
| B14 | mittel | Zeitstempel in UTC, Fälligkeiten lokal → Protokoll zeigt 2 h falsch | Nur die Anzeige umrechnen oder künftig lokal speichern? Bestehende Zeilen sind UTC |
| B15 | niedrig | `praemien.db.bak` wird bei jedem Start überschrieben, nicht nur vor Migrationen | Wie viele Stände aufheben – Platz auf dem Green ist begrenzt |

---

## Beschlossen: Bereich „Zu prüfen" (noch nicht umgesetzt)

Abgestimmter Entwurf, der **B2** und **B3** gemeinsam auflöst. Hier nur
festgehalten – im Code ist davon noch nichts geändert.

**Grundgedanke:** „Zu prüfen" ist keine Stufe im Lebenszyklus, sondern eine
querliegende Auffälligkeit. Ein gekündigter, bestätigter Deal mit offener
Bedingung *ist* fachlich abgeschlossen – er hat nur einen losen Faden.
`status()` bleibt deshalb einwertig, und ein Deal kann gleichzeitig
„Abgeschlossen" und „zu prüfen" sein.

**Entscheidungen:**

1. **Verankerung:** neue Kategorie in *Zu erledigen*, kein eigener Tab und
   kein siebter Pipeline-Status.
2. **Status:** `kuendigung_bestaetigt` wird in `derived.status()` terminal –
   der Deal zeigt dann „Abgeschlossen". Offene Bedingungen werden dabei
   **nicht** automatisch auf erfüllt gesetzt (ausdrücklicher Wunsch), sie
   erscheinen nur noch unter „Zu prüfen". Damit verschwindet der
   Widerspruch, dass ein Deal gleichzeitig in der ToDo-Liste unter
   „Bedingungen" und in den Sperrfristen als gekündigt steht.
3. **Regeln**, alle vier aufzunehmen:

| Regel | Bedingung | Herkunft |
|---|---|---|
| Bedingungen nach Kündigung offen | `gekuendigt` und mindestens eine Bedingung `not erfuellt` | B2 |
| Prämien nach Kündigung offen | `gekuendigt` und mindestens eine Prämie `not erhalten` | neu – Konto zu, Geld nie geflossen |
| Keine Prämie erfasst | `praemien` ist leer | B3 |
| Gekündigt ohne Kündigungsmonat | `gekuendigt` und `parse_gekuendigt_monat()` liefert `None` | wandert aus dem Sperrfristen-Tab hierher |

**Was bei der Umsetzung noch zu klären ist:**

- **Abhaken braucht gespeicherten Zustand.** Damit ein geprüfter Deal die
  Liste verlässt, ohne die Bedingung abzuhaken, muss „angesehen" pro Deal
  und Regel gespeichert werden – neue Spalte + Alembic-Migration. Das weicht
  das Prinzip „nur Fakten speichern, alles andere ableiten" auf; als Muster
  bietet sich `uebersprungene_felder` an, das für die Vollständigkeit genau
  das schon tut. Die Route sollte idempotent setzen, nicht togglen (vgl. B8).
- **Frisch angelegte Deals** erfüllen „keine Prämie erfasst" sofort, weil die
  Prämien erst danach eingetragen werden. Entweder als Rauschen akzeptieren
  (abhakbar) oder die Regel erst ab einem gewissen Alter greifen lassen.
- **Wiederauftauchen:** Ändern sich die Fakten nach dem Abhaken (z. B. neue
  unbezahlte Prämie), bleibt der Marker gesetzt und die Auffälligkeit
  versteckt. Für den Anfang vertretbar, sollte aber bewusst so entschieden
  sein.
- **Sperrfristen-Tab:** Die Liste „Gekündigt, aber ohne Kündigungsmonat"
  (`sperrfristen.html:30-46`) entfällt dort, sobald die Regel greift – sonst
  lebt derselbe Hinweis an zwei Stellen.
- **CSS:** Die Tab-Umschaltung in `style.css:370-396` ist pro Slug
  ausgeschrieben; der neue Slug muss in allen drei Selektorlisten sowie bei
  `.tag-*` und `.cat-*` ergänzt werden.
- **Nebeneffekt:** Die Regel „gekündigt ohne Kündigungsmonat" fängt auch
  falsch formatierte Eingaben ab (`2026-05` statt `05.26`) und entschärft
  damit einen Teil von **B12**.

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

---

## 1. Fachlogik

### B1 – „Kündbar ab" wird angemahnt, obwohl leer eine Aussage ist [V]
**Fachliche Regel (vom Nutzer bestätigt):** Ein leeres `kuendbar_ab`
bedeutet *keine Sperrfrist* – gekündigt werden kann, sobald die Prämie da
ist. Die Ableitung setzt das korrekt um:

```
leer, Prämie noch offen  -> praemie_warten
leer, Prämie erhalten    -> kuendigen
Datum künftig, erhalten  -> wartet_auf_kuendigung
```

Damit ist am Status nichts zu ändern. Übrig bleibt eine Inkonsistenz eine
Ebene höher: `WUENSCHENSWERTE_FELDER` (`derived.py:221`) führt
`kuendbar_ab` als Pflichtangabe, der Tab *Vollständigkeit* meldet also
jeden Deal ohne Sperrfrist als lückenhaft – obwohl das Feld genau so
gemeint ist. Verifiziert: beide Deals oben mit leerem Datum listen
`kuendbar_ab` als offenes Feld.

Praktisch heißt das: Für jeden sperrfristfreien Deal muss der Nutzer das
Feld einmal manuell auf „nicht nötig" setzen (`skip-field`), damit der Tab
Ruhe gibt.

*Zu entscheiden:* `kuendbar_ab` aus `WUENSCHENSWERTE_FELDER` streichen (dann
verschwindet die Erinnerung ganz) – oder sie bewusst behalten, weil man
beim Anlegen eben doch kurz prüfen will, ob die Bank eine Frist vorsieht.
Unabhängig davon lohnt es, die Regel im Docstring von `ist_kuendbar()`
festzuhalten; aktuell steht sie nirgends.

### B2 – Status-Pipeline ist strikt sequenziell, die Realität nicht [V]
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

### B3 – Deal ohne Prämien ist eine unsichtbare Sackgasse [V]
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

### B4 – `auszahlung_erwartet` wird eingefordert, aber nie ausgewertet
Das Feld wird in *Vollständigkeit* aktiv angemahnt, in der ToDo-Liste
angezeigt – und sonst nirgends verwendet. Es gibt **keine
Überfälligkeitsprüfung**: Eine für `2025-03` erwartete, im Juli 2026 immer
noch offene Prämie sieht in der App exakt aus wie eine für `2026-12`
erwartete.

Fachlich ist genau das das zentrale Signal beim Prämien-Hopping („Prämie
ist nicht gekommen → nachhaken, bevor die Frist der Bank abläuft").
Bedingungen und manuelle Aufgaben haben eine `ueberfaellig`-Kennzeichnung,
Prämien nicht – auch das ist eine Inkonsistenz innerhalb der ToDo-Liste.

### B5 – Freibetrag ohne fachlichen Bezugsrahmen
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
gar kein Hinweis gesetzt wird (siehe B10/A13).

---

## 2. Importweg (JSON-Textfeld)

### B10 – Bank und Inhaber werden case-sensitiv verglichen [V]
Zwei Einfügevorgänge über `/deals/json-import`, einmal
`"Comdirect"/"Depot"/"Max"`, einmal `"comdirect "/" Depot"/"max"`:

```
Banken : ['Comdirect', 'comdirect']
Inhaber: ['Max', 'max']
Deal 1: bank='Comdirect' kontoart='Depot'   hinweis=False
Deal 2: bank='comdirect' kontoart=' Depot'  hinweis=False
```

`get_or_create_bank/-inhaber` vergleichen exakt. „Comdirect", „comdirect",
„ComDirect" werden zu drei Banken, „Max" und „max" zu zwei Personen. Das
zerlegt die Sperrfristen-Auswertung (deren ganzer Zweck der Vergleich pro
Bank ist), die Pro-Inhaber-Tabelle inklusive Freibetragssumme und den
Bank-Filter.

*Empfehlung:* Vergleich über `func.lower(Bank.name)`. **Achtung:** bereits
entstandene Dubletten müssen dabei zusammengeführt werden – das ist eine
Datenmigration und nicht ohne Weiteres rückholbar, deshalb B statt A.

### A13 – `kontoart` wird im Importpfad nicht getrimmt
Im selben Testlauf (Ausgabe siehe B10): `build_deal_from_import()` übernimmt
`kontoart` ungetrimmt (`' Depot'`), während der Formularpfad (`deals.py`)
`.strip()` aufruft. Zwei Anlagewege, zwei Ergebnisse für dieselbe Eingabe.
Folgefehler: Der Kündigungs-Hinweis findet `(' Depot')` nicht mehr.

Der Fix gleicht den Importpfad nur an das bereits bestehende Verhalten des
Formularpfads an – keine fachliche Entscheidung nötig.

### A14 – Formularpfad validiert praktisch gar nicht [V]
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

### B11 – `quelle` ist unvalidiert und wird beim Speichern still umgeschrieben [V]
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
Die Normalisierung selbst ist trivial – zu entscheiden ist, was mit
bereits gespeicherten abweichenden Werten passiert.

### B12 – Zwei Monatsformate, beides ungeprüfter Freitext
| Feld | Format | Geprüft? |
|---|---|---|
| `gekuendigt_im_monat` | `MM.YY` (`07.26`) | nur beim Lesen, `parse_gekuendigt_monat()` |
| `auszahlung_erwartet` | `YYYY-MM` (`2026-07`) | nie |

Zwei Formate für dieselbe fachliche Größe (ein Monat) in derselben Maske.
Gibt der Nutzer bei `gekuendigt_im_monat` „2026-05" ein, liefert
`parse_gekuendigt_monat()` `None` und der Deal verschwindet kommentarlos in
die Liste „Gekündigt, aber ohne Kündigungsmonat" – ohne Hinweis, dass die
Eingabe nur falsch formatiert war.

### A16 – Kein Massenimport, und die Fehlermeldung hilft nicht weiter [V]
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
fehlt"). Rein additiv – bestehende Einfügevorgänge funktionieren
unverändert weiter.

### B13 – Kein Duplikat-Schutz
Der Import prüft nicht, ob `(bank, kontoart, inhaber)` bereits existiert.
Zweimaliges Einfügen desselben JSON erzeugt zwei identische Deals, die sich
in Pipeline und Kennzahlen doppelt niederschlagen. Es gibt auch keinen
Unique-Constraint auf dieser Kombination.

### A12 – Fremdschlüssel werden nicht durchgesetzt [V]
```
PRAGMA foreign_keys = 0
→ Prämie mit deal_id=99999 (nicht existent) lässt sich anlegen
```
SQLite prüft Fremdschlüssel nur bei explizit gesetztem Pragma; `database.py`
setzt es nicht. `praemie_add()`, `bedingung_add()` u. a. prüfen ebenfalls
nicht, ob der Deal existiert. Waisen-Datensätze sind damit möglich und
tauchen in keiner Ansicht mehr auf.

Das Einschalten wirkt nur auf neue Schreibvorgänge; bestehende Zeilen
werden nicht nachträglich geprüft. Vorher einmal auf vorhandene Waisen
schauen.

### A15 – `uebersprungene_felder` ist nicht importierbar
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

### A1 – Erster Pipeline-Balken ist farblos [V]
`overview.html` rendert `pipe-bar-{{ s }}`, also `pipe-bar-bedingungen`.
`style.css:264` definiert aber `.pipe-bar-cond`. Verifiziert am gerenderten
HTML – die Klasse existiert im CSS schlicht nicht, das erste Segment der
Pipeline bleibt ungefärbt. Die Status-Chips (`.chip.status-bedingungen`,
`style.css:304`) verwenden dagegen den korrekten Schlüssel: derselbe Status
heißt im CSS an zwei Stellen unterschiedlich.

### A2 – Fortschrittsbalken hat ein Segment zu wenig [V]
`deals_list.html:51` iteriert `range(5)`, es gibt aber **sechs** Status
(`STATUS_ORDER`). Für einen abgeschlossenen Deal ist `status_index == 5` –
die Bedingung `i == zeile.status_index` wird nie wahr:

```
segmente: 5 | done: 0 | on: 1     (Status „Bedingungen")
segmente: 5 | done: 1 | on: 1     (Status „Auf Prämie warten")
```
Ein abgeschlossener Deal zeigt fünf graue/grüne Segmente und **keine**
aktuelle Position. Sollte `range(status_order | length)` sein.

### A3 – „+"-Link in der Vollständigkeit führt ins Leere [V]
`completeness.html:26` verlinkt auf `deals/{id}/edit#{{ feld.feld }}`.
Gerendert wird u. a. `edit#praemie_1_auszahlung_erwartet` – ein Element mit
dieser ID gibt es in `deal_form.html` nicht (das Input trägt nur ein
`name`). Ausgerechnet das mit Abstand häufigste offene Feld hat also einen
toten Sprunglink. `#kontonummer`, `#kuendbar_ab` und `#freibetrag`
funktionieren.

### A4 – Rohe Quellen-Bezeichnung in der Vollständigkeit
`derived.offene_felder()` baut das Label mit `f"… ({p.quelle}, …)"` – roh,
also „spartanien" statt „Spartanien". Genau dieser Fix wurde in 1.6.1 für
die ToDo-Liste gemacht (`quelle_label()`), die Vollständigkeit wurde dabei
vergessen.

### A5 – Doppelte DOM-ID [V]
`deal_form.html:84/86`: `<div class="feld" id="kuendigung_hinweis">` und
darin `<textarea id="kuendigung_hinweis">`. Verifiziert am gerenderten HTML
(`2 × id="kuendigung_hinweis"`). Ungültiges HTML; `document.getElementById`
und der Anker-Sprung treffen das `div`, nicht das Eingabefeld.

### A6 – Filter wirft 500 statt zu ignorieren [V]
`GET /deals?inhaber_id=abc` → **500**. `deals_list()` macht `int(v)` ohne
Absicherung. Der Fix aus 1.7.0 hat nur den leeren Wert abgefangen
(`if v.strip()`), nicht den nicht-numerischen. Erreichbar über einen alten
Lesezeichen-Link oder manuelle URL-Eingabe.

### A7 – Aktiv-Markierung der Navigation
`base.html:15` prüft `request.url.path.endswith('tracker/')`. Unter Ingress
lautet der Pfad `/api/hassio_ingress/<token>/` – die Bedingung greift dort
nie, die Startseite markiert also keinen Tab. Zusätzlich sind die Regeln
uneinheitlich (`endswith('/overview')` vs. `'/todos' in path` vs.
`endswith('/deals')`), und Detailseiten wie `deals/3/edit` markieren gar
nichts. Sauberer wäre ein an die Templates übergebener `aktiver_tab`.

### A8 – Neuer-Deal-Route akzeptiert Felder, die das Formular nicht hat
`deal_new_create()` nimmt `kuendbar_ab`, `freibetrag`, `kommentar` und
`praemien_auf_sparkonto` entgegen. Das Neu-Formular rendert diese Felder
nicht (`{% if deal %}` ab `deal_form.html:63`) – sie sind auf diesem Weg tot
und suggerieren beim Lesen des Codes eine Funktion, die es nicht gibt.

### A9 – „Formular / JSON einfügen" ist kein Umschalter
Die beiden Buttons (`deal_form.html:29-30`) sind ein Seitenreload bzw. ein
Ankersprung; beide Blöcke sind immer sichtbar. Als Segmented Control gestylt
verhalten sie sich nicht wie eines.

### A10 – Markup und Bedienbarkeit
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

### B14 – Zeitstempel in UTC, Fälligkeiten lokal [V]
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

### B15 – Sicherheitskopie wird bei jedem Start überschrieben
`run_migrations()` kopiert `praemien.db` → `praemien.db.bak` bei **jedem**
Start, auch wenn keine Migration ansteht. Wird ein Datenverlust erst nach
zwei Neustarts bemerkt, ist die Sicherung längst mit dem kaputten Stand
überschrieben. README/DOCS.md beschreiben sie als Absicherung „vor jeder
Schema-Migration" – tatsächlich ist sie an den Start gekoppelt.
*Empfehlung:* nur kopieren, wenn `command.upgrade` wirklich etwas zu tun
hat, und mit Zeitstempel im Dateinamen.

### A17 – Keine Tests
Kein einziger Test im Repo. Bei einer App, deren Kern (`derived.py`) reine,
sehr gut testbare Funktionen sind – Status, Sperrfristen, ToDo-Ableitung,
Vollständigkeit – ist das die günstigste offene Absicherung. Die Befunde
B2, B3, B7 und A2 wären mit je drei Zeilen Test aufgefallen.

### A11 – Veraltete FastAPI-API
`@app.on_event("startup")` (`main.py:81`) ist in FastAPI 0.115 deprecated;
der Nachfolger ist der `lifespan`-Kontextmanager.

---

## Empfohlene Reihenfolge

1. **A1–A6** – die sechs isolierten Frontend-/Robustheitsfehler; zusammen
   ein kleiner Diff, sofort sichtbarer Effekt.
2. **A13 / A14** – Eingaben trimmen und Leereingaben ablehnen; stoppt das
   Entstehen weiterer kaputter Datensätze.
3. **B11 / B10** – `quelle` und Namensvergleich normalisieren, inklusive
   einmaliger Bereinigung der bestehenden Daten. Hier gehen bis dahin still
   und ohne Meldung Daten kaputt.
4. **B2** – Status-Pipeline korrigieren.
5. **B4 / B5** – überfällige Prämien und Freibetragsgrenze: die zwei
   fachlichen Funktionen, die dem Anwendungsfall am meisten fehlen.
6. **B9 / A16** – Kündigungs-Hinweise beim Anlegen statt beim Start,
   Massenimport und lesbare Fehlermeldungen.
7. **B14 / B15 / A17** – Zeitbasis, Backup-Strategie, Tests.
