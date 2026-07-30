# Fachliches Review – Prämien-Tracker 1.7.1

Stand: Commit `b59b65a`. Geprüft wurden Fachlogik, Frontend, der Importweg
und Inkonsistenzen zwischen Code, UI und Dokumentation. Alle mit **[V]**
markierten Punkte wurden gegen die laufende App bzw. eine echte SQLite-DB
verifiziert, nicht nur aus dem Code abgeleitet.

Die Findings sind nach Umsetzbarkeit nummeriert:

- **A1–A17** – sofort umsetzbar, keine Änderung an der Fachlogik.
- **B1–B15** – vorher anschauen, weil eine fachliche Entscheidung,
  eine Datenmigration oder eine spürbare Verhaltensänderung dranhängt.

**B5 wurde herausgenommen** – der Freibetrag wird separat verfolgt. Die
Nummer bleibt frei, damit die übrigen IDs stabil bleiben.

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
| B1 | niedrig | Vollständigkeit mahnt „Kündbar ab" an, obwohl ein leeres Feld eine gültige Aussage ist („keine Sperrfrist") | **Entschieden:** `kuendbar_ab` raus aus `WUENSCHENSWERTE_FELDER`. Noch nicht umgesetzt |
| B2 | hoch | Gekündigt + bestätigt, aber offene Bedingung → gilt gleichzeitig als „in Bearbeitung" und „gekündigt" | **Entschieden**, siehe „Beschlossen: Bereich Zu prüfen". Noch nicht umgesetzt |
| B3 | hoch | Deal ohne Prämien hängt unsichtbar in „Auf Prämie warten" – kein ToDo, keine Meldung | **Entschieden**, siehe „Beschlossen: Bereich Zu prüfen". Noch nicht umgesetzt |
| B4 | hoch | `auszahlung_erwartet` wird eingefordert, aber nie ausgewertet – keine Überfälligkeit | **Entschieden**, siehe Detailabschnitt (nicht durch „Zu prüfen" abgedeckt). Noch nicht umgesetzt |
| B6 | mittel | „Stornieren" setzt `gekuendigt=True` → stornierte Deals verfälschen den Sperrfristen-Tab | **Entschieden**, siehe Detailabschnitt. Noch nicht umgesetzt |
| B7 | mittel | Zugangsdaten-ToDo erscheint auch für abgeschlossene Deals | **Entschieden:** entfällt ab `gekuendigt`. Noch nicht umgesetzt |
| B8 | hoch | Abhak-Routen invertieren statt zu setzen; eine doppelt ankommende Anfrage kippt den Wert zurück und überschreibt beim Kündigen den gepflegten Kündigungsmonat | **Entschieden**, siehe Detailabschnitt. Noch nicht umgesetzt |
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

**Entschieden:** `kuendbar_ab` wird aus `WUENSCHENSWERTE_FELDER` gestrichen.
Übrig bleiben dort `kontonummer` und `freibetrag`. Zusätzlich sollte die
Regel im Docstring von `ist_kuendbar()` festgehalten werden; aktuell steht
sie nirgends im Code.

Zwei erwartbare Nebenwirkungen, beide unkritisch:

- Der Fortschritt im Vollständigkeits-Tab („x/y Deals gepflegt") springt
  nach oben, weil viele Deals nur noch wegen dieses Feldes als unvollständig
  galten. Das ist die beabsichtigte Korrektur, kein Fehler.
- Deals, bei denen `kuendbar_ab` bereits von Hand auf „nicht nötig" gesetzt
  wurde, tragen den Eintrag weiterhin in `uebersprungene_felder`. Er wird
  dann nicht mehr ausgewertet – harmlose Altlast, die man beim nächsten
  Datenschnitt mit entfernen kann, aber nicht muss.

Damit ist B1 zwar formal eine fachliche Entscheidung gewesen, die Umsetzung
selbst ist aber ein Einzeiler ohne Logikänderung – sie kann zusammen mit dem
A-Block laufen.

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

**Wird das nicht schon von „Zu prüfen" erledigt? Nein.** Die dortige Regel
„Prämien nach Kündigung offen" greift nur bei `gekuendigt` – sie fängt den
Fall ab, dass das Konto schon zu ist und trotzdem Geld fehlt. Der typische
B4-Fall ist ein *laufender* Deal:

| Fall | `gekuendigt` | von „Zu prüfen" erfasst? |
|---|---|---|
| Konto gekündigt, Prämie nie erhalten | ja | ja – Regel 2 |
| Deal läuft, Prämie war für `2025-03` angekündigt, heute 07/2026 | nein | **nein** |

Die zweite Zeile ist genau die, um die es geht – und sie fällt durch. Die
beiden Befunde überschneiden sich also, decken sich aber nicht.

**Vorschlag zur Auflösung:** keine neue Kategorie, sondern das bestehende
ToDo „Auf Prämie warten" als überfällig markieren – so wie es Bedingungen
und manuelle Aufgaben schon tun. `Todo.ueberfaellig` und die CSS-Klasse
`.frist.ueberfaellig` gibt es bereits, es fehlt nur die Auswertung von
`auszahlung_erwartet`. Der Hinweis steht dann dort, wo man ohnehin
hinschaut, und „Zu prüfen" bleibt das, was es sein soll: Dinge, die man
sich *irgendwann* ansieht, statt Dinge, die *jetzt* dringend werden.

**Entschieden – Fall 1 (`auszahlung_erwartet` gesetzt):** überfällig ab
**einem Monat Karenz** nach dem erwarteten Monat. Banken zahlen
erfahrungsgemäß spät; ein ToDo, das sofort rot wird, obwohl noch alles
normal läuft, verliert seine Wirkung. Voraussetzung ist, dass
`auszahlung_erwartet` überhaupt geparst wird – heute ist es reiner
Freitext (siehe B12).

**Fall 2 (kein Datum gesetzt): 2 Monate Karenz – aber der Bezugspunkt
existiert nicht.** Gewünscht ist „2 Monate nach Erfüllung der letzten
Prämie". Das ist mit dem heutigen Datenmodell **nicht berechenbar**:

| Modell | Zustandsfeld | Datum dazu |
|---|---|---|
| `Bedingung` | `erfuellt` (Boolean) | **keins** – nur `faellig_bis` (Soll, nicht Ist) |
| `Praemie` | `erhalten` (Boolean) | **keins** |
| `Deal` | – | `erstellt_am`, `geaendert_am` |

Die App speichert also *ob* etwas erfüllt/erhalten ist, nie *wann*.
`geaendert_am` am Deal taugt nicht als Ersatz, weil es sich bei jeder
beliebigen Änderung aktualisiert.

Es gibt genau eine Stelle, an der der Zeitpunkt heute anfällt: das
Protokoll. Verifiziert – das Abhaken einer Bedingung erzeugt

```
2026-07-30 05:56:38 | geaendert | feld=erfuellt | -> True
```

Das als Quelle für eine fachliche Ableitung zu nutzen, hat aber Haken: Das
Protokoll ist ein Änderungsjournal, kein Faktenspeicher; für alles vor
Version 1.6.0 fehlen die Einträge ganz; und seine Zeitstempel sind UTC
(siehe B14). Sauberer wären eigene Felder `erfuellt_am` / `erhalten_am`
plus Migration – für Altbestand einmalig aus dem Protokoll befüllbar,
soweit vorhanden.

**Entschieden – Fall 2:** Anker ist die **zuletzt erfüllte Bedingung**;
zwei Monate danach gilt eine noch offene Prämie als überfällig. Das Datum
bekommt ein **eigenes Feld** `Bedingung.erfuellt_am` (neue Spalte +
Migration), das beim Abhaken gesetzt wird. Der Altbestand wird einmalig aus
dem Protokoll befüllt, soweit dort Einträge vorliegen.

Damit ergibt sich die Regel:

| Ausgangslage | überfällig ab |
|---|---|
| `auszahlung_erwartet` gesetzt | Ende des erwarteten Monats + 1 Monat |
| kein Datum, Bedingungen vorhanden und alle erfüllt | `erfuellt_am` der zuletzt erfüllten Bedingung + 2 Monate |
| kein Datum, **keine** Bedingungen hinterlegt | – siehe unten |

**Detail 1 – Deals ohne Bedingungen.** `bedingungen_erfuellt()` liefert für
eine leere Liste `True` („keine Bedingungen hinterlegt – gilt als erfüllt",
`deal_form.html:194`). Dann gibt es aber auch kein `erfuellt_am`, an dem die
Frist hängen könnte. Vorschlag: in diesem Fall **keine**
Überfälligkeitsmarkierung – es gibt schlicht keinen Bezugspunkt. Die
Vollständigkeit mahnt `auszahlung_erwartet` ohnehin an, der Nutzer wird also
an derselben Stelle abgeholt. `deal.erstellt_am` wäre die Alternative,
bildet aber nur ab, wann der Deal *erfasst* wurde – das kann Monate nach
der Kontoeröffnung sein.

**Detail 2 – Zurücknehmen.** Wird eine Bedingung wieder auf „offen"
gesetzt, muss `erfuellt_am` mit geleert werden. Sonst entsteht dasselbe
Muster wie bei `gekuendigt_im_monat` in B8: ein Datum, das stehen bleibt,
obwohl der Zustand dazu nicht mehr passt.

**Detail 3 – Backfill.** Aus dem Protokoll sind die Einträge mit
`tabelle='Bedingung'`, `feld='erfuellt'`, `neuer_wert='True'` zu nehmen,
je Bedingung der jüngste. Zwei Einschränkungen: Für vor Version 1.6.0
erfüllte Bedingungen gibt es keine Einträge – die bleiben `NULL` und lösen
damit keine Überfälligkeit aus (bewusst konservativ). Und die
Protokoll-Zeitstempel sind UTC, müssen beim Backfill also umgerechnet
werden (B14).

*Nicht Teil dieser Entscheidung:* Ein symmetrisches
`Praemie.erhalten_am` wird für diese Regel nicht gebraucht. Es wäre die
naheliegende Ergänzung, falls später einmal ausgewertet werden soll, wie
lange Banken tatsächlich zahlen – bis dahin bleibt es weg.


### B6 – „Stornieren" missbraucht `gekuendigt`
`deal_stornieren()` setzt `gekuendigt=True` und `kuendigung_bestaetigt=True`.
Der Deal erscheint damit dauerhaft im Sperrfristen-Tab unter „Gekündigt,
aber ohne Kündigungsmonat" – obwohl er nie gekündigt, sondern nie zustande
gekommen ist. Das verfälscht genau die Auswertung, die entscheidet, wann
eine Bank wieder als Neukunden-Ziel taugt.

**Nicht zu ändern:** Das Nullsetzen der offenen Prämienbeträge ist
beabsichtigt und fachlich richtig – ein stornierter Deal hat schlicht keine
Prämie gebracht, 0 ist der zutreffende Wert. Die ursprüngliche Zusage bleibt
im Protokoll nachvollziehbar. (Ursprüngliche Kritik an dieser Stelle
zurückgezogen.)

**Entschieden:** eigenes Feld `storniert` statt Umdeutung von `gekuendigt`.
Daraus folgt:

- `deal_stornieren()` setzt `storniert=True` und **nicht mehr** `gekuendigt`
  / `kuendigung_bestaetigt`.
- `derived.status()` behandelt `storniert` als terminal → „Abgeschlossen"
  (zusammen mit der Terminal-Regel für `kuendigung_bestaetigt` aus B2).
- Der Sperrfristen-Filter (`sperrfristen.py:21`) bekommt zusätzlich
  `storniert.is_(False)` – damit ist der Tab automatisch sauber.
- Neue Spalte + Alembic-Migration `0005`.

**Offene Bedingungen beim Stornieren – entschieden:** `deal_stornieren()`
hakt sie **weiterhin** als erfüllt ab. Ein stornierter Deal ist wirklich
erledigt und soll nicht noch einmal auftauchen.

Das ist bewusst die Ausnahme zur B2-Regel („nach Abschluss nicht
stillschweigend abhaken") und kein Widerspruch, weil sich die beiden Fälle
fachlich unterscheiden: Bei einem *gekündigten* Konto ist eine offene
Bedingung ein echter loser Faden – die Prämie könnte daran hängen. Bei
einem *stornierten* Deal ist der Vorgang nie zustande gekommen, es gibt
nichts nachzuschauen.

Für die Umsetzung heißt das: Die Regel „Bedingungen nach Kündigung offen"
aus dem Bereich *Zu prüfen* darf auf stornierte Deals nicht anspringen –
sie greift ohnehin nur bei `gekuendigt`, und das setzt `deal_stornieren()`
künftig nicht mehr. Der Ausschluss ergibt sich also von selbst.

**Altbestand:** Bereits stornierte Deals sind nachträglich nicht sicher
erkennbar – sie sehen aus wie normal gekündigte mit 0-€-Prämien. Sie müssten
nach der Migration einmal von Hand als `storniert` markiert werden.

### B7 – Zugangsdaten-ToDo auch für abgeschlossene Deals [V]
```
status: abgeschlossen | ToDos: [('Zugangsdaten', '… Zugangsdaten sichern')]
```
`deal_todos()` hängt das ToDo unabhängig vom Status an. Für ein gekündigtes
und bestätigtes Konto ist es gegenstandslos und bläht die Liste dauerhaft
auf.

**Entschieden:** Das ToDo entfällt **ab `gekuendigt`** – nicht erst ab
`kuendigung_bestaetigt`. Sobald das Konto gekündigt ist, müssen die
Zugangsdaten nicht mehr gesichert werden.

### B8 – Abhak-Routen invertieren, statt einen Zustand zu setzen [V]
Alle Abhak-Routen in `routers/todos.py` kippen den Wert um, statt ihn zu
setzen:

```python
p.erhalten = not p.erhalten          # todos.py:153
```

Dadurch hängt das Ergebnis davon ab, **wie oft** die Route aufgerufen
wurde, nicht davon, was der Nutzer wollte. Zweimal dieselbe Anfrage:

```
Ausgangslage:  praemie.erhalten=False   gekuendigt=True   gekuendigt_im_monat='03.25'
1. POST:       praemie.erhalten=True
2. POST:       praemie.erhalten=False        ← Prämie gilt wieder als offen
```

**Der teurere Fall ist `kuendigen-toggle`** (`todos.py:159`): Beim Anhaken
setzt die Route zusätzlich den aktuellen Monat, beim Abhaken räumt sie ihn
aber nicht wieder weg. Zweimal ausgelöst, landet man deshalb nicht beim
Ausgangszustand:

```
1. POST:  gekuendigt=False  gekuendigt_im_monat='03.25'   (Monat bleibt stehen)
2. POST:  gekuendigt=True   gekuendigt_im_monat='07.26'   ← manuell gepflegter Wert weg
```

Der von Hand eingetragene Kündigungsmonat wird also mit dem heutigen
überschrieben – und genau dieser Wert speist die Sperrfristen-Auswertung.
Aus „vor 16 Monaten gekündigt, grün" wird lautlos „vor 0 Monaten, rot".
Deshalb Prio **hoch** statt mittel.

**Korrektur zur ersten Fassung dieses Reviews:** Dort stand, auch ein
*Reload* nach dem Abhaken kippe den Wert zurück. Das stimmt nicht – die
Routen antworten mit `303` auf ein `GET /todos` (Post/Redirect/Get),
ein Neuladen wiederholt also nur das GET. Verifiziert:

```
POST /todos/praemien/1/toggle → 303, Location: /todos?tab=praemie
```

Realistisch bleiben: Doppel-Tap auf dem Handy, eine vom Webview oder vom
Netz wiederholte Anfrage, und der Zurück-Button, der die veraltete Liste
zeigt, in der der Posten noch offen aussieht – ein zweiter Klick darauf
macht die erste Aktion zunichte. Im normalen Ablauf funktioniert das
Abhaken; die Konstruktion ist an den Rändern fragil, nicht grundsätzlich
kaputt.

Dazu kommt: Die Checkboxen in `todos.html` werden **immer unchecked**
gerendert (`todos.html:91` u. a.). Das fällt bisher nicht auf, weil ein
erledigter Posten aus der Liste verschwindet – es sind faktisch Buttons in
Checkbox-Optik.

**Entschieden:** Zielzustand mitschicken (`wert=on|off`) statt invertieren,
beim Abhaken von „gekündigt" den Monat wieder leeren und einen bereits
gesetzten Monat beim Anhaken **nicht** überschreiben.

*Nachtrag zur Einschätzung oben:* In der Tabelle stand zunächst, das ändere
die Bedienung spürbar. Das war zu pessimistisch. Weil erledigte Posten aus
der Liste verschwinden, ist jeder angezeigte Posten immer offen – die
Checkbox sendet also konstant `wert=on`, und die Route setzt statt zu
kippen. Die Oberfläche bleibt dabei exakt wie heute; die Checkboxen dürfen
weiterhin leer gerendert werden. Einzig „Wieder öffnen" bei den erledigten
Aufgaben (`todos.html:217`) schickt `wert=off`. Erst wenn erledigte Posten
künftig angehakt stehen bleiben sollen, wird daraus eine UI-Änderung – das
ist hier ausdrücklich nicht vorgesehen.

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
5. **B4** – überfällige Prämien: die fachliche Funktion, die dem
   Anwendungsfall am meisten fehlt.
6. **B9 / A16** – Kündigungs-Hinweise beim Anlegen statt beim Start,
   Massenimport und lesbare Fehlermeldungen.
7. **B14 / B15 / A17** – Zeitbasis, Backup-Strategie, Tests.
