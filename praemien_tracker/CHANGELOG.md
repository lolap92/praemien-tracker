# Changelog

## 2.47.0

Automatischer Sync von Prämien-Auszahlungen in den Budget-Tracker.

- **Jede Auszahlung wird jetzt als Forecast im Budget-Tracker nachgeführt:** Wird eine Prämie angelegt, im Betrag oder im erwarteten Auszahlungsmonat geändert oder gelöscht, meldet der Prämien-Tracker das automatisch per Home-Assistant-Event an das Budget-Tracker-Add-on, das daraus einen Forecast-Eintrag im Topf "Sonderausgaben" anlegt, aktualisiert oder wieder entfernt (siehe `app/praemien_tracker/auszahlungs_sync.py`). Wird eine Prämie als "erhalten" markiert oder ist kein erwarteter Monat gepflegt, entfernt der Budget-Tracker einen zuvor angelegten Forecast-Eintrag wieder - eine bereits erhaltene Auszahlung soll die Prognose nicht länger belasten.
- Da `auszahlung_erwartet` nur einen Monat kennt, wird für den Forecast-Termin der 15. dieses Monats als Näherung verwendet.
- Setzt voraus, dass das Budget-Tracker-Add-on ab Version 1.34.0 läuft (dort neu: der Empfang dieser Events).

## 2.46.1

Neue ToDo-Kategorie "Deal pflegen": führt die bisherige eigene
"Vollständigkeit"-Seite und die alte "Zugangsdaten"-Kategorie in "Zu
erledigen" zusammen.

- Die Seite "Vollständigkeit" (Menüpunkt unter "Mehr") entfällt komplett -
  ihr Inhalt steckt jetzt als eigene Kategorie "Deal pflegen" direkt hinter
  "Manuelle Aufgaben" in "Zu erledigen", noch vor "Bedingungen". Jeder Deal
  mit einer fehlenden Kontonummer, ungesicherten Zugangsdaten oder einer
  offenen Prämie ohne erwartetes Auszahlungsdatum landet dort als eigener
  Eintrag mit einem Feld-Chip je offener Angabe - "+" springt zum jeweiligen
  Feld im Bearbeiten-Formular, "×" markiert es als "nicht nötig" (wie bisher
  auf der Vollständigkeits-Seite). Freibetrag ist bewusst nicht mehr Teil
  davon.
- Die alte "Zugangsdaten"-Kategorie mit ihrer Einzel-Checkbox entfällt - das
  Feld wird jetzt genauso wie Kontonummer/Auszahlung über "Deal pflegen"
  gepflegt.
- "Deal pflegen" ist bewusst kein siebter Pipeline-Status: ein Deal kann
  gleichzeitig einen der sechs echten Status UND offene Angaben haben. Auf
  der Übersicht bekommt es deshalb eine eigene Kachel neben der
  Pipeline-Kachel, nicht ein zusätzliches Pipeline-Segment.
- Migrations-Hinweis für bestehende Add-on-Installationen: keine, die
  zugrunde liegenden Datenbank-Felder (kontonummer, zugangsdaten_gespeichert,
  auszahlung_erwartet, uebersprungene_felder) bleiben unverändert.

## 2.46.0

Deal-Detailseite wird standardmäßig im Read-only Modus geöffnet.

- **Detailseite statt Bearbeiten-Formular beim Navigieren:** Jeder Navigationslink, der bisher direkt zur Bearbeitungsseite (`/deals/{id}/edit`) geführt hat (unter anderem aus der ToDo-Liste, der Vollständigkeit, den Sperrfristen und dem Änderungsprotokoll), öffnet nun standardmäßig die schreibgeschützte Detailseite (`/deals/{id}`).
- **Sicherheit vor versehentlichen Änderungen:** Damit wird ein versehentliches Ändern oder Löschen von Daten beim bloßen Anschauen von Deals zuverlässig verhindert. Über den dortigen “Bearbeiten”-Button kann die Bearbeitungsseite weiterhin gezielt aufgerufen werden.

## 2.45.2

Beim Löschen eines Elements auf der Deal Detailseite wird die Seite nicht mehr neu geladen und andere gemachte Änderungen an Texten gehen nicht mehr verloren.

- Das Löschen von Prämien, Bedingungen, Aufgaben und Links auf der Bearbeitungsseite eines Deals erfolgt nun asynchron im Hintergrund über die Fetch-API.
- Die gelöschte Zeile wird direkt aus der Ansicht entfernt, ohne die Seite neu zu laden. Dadurch bleiben alle noch nicht gespeicherten Eingaben in anderen Textfeldern erhalten.

## 2.45.1

Nach dem Speichern der Deal-Detailseite wechselt die Ansicht wieder automatisch in den Nur-Lese-Modus (Read-Only-Modus).

- Bisher verblieb die App nach dem Klicken auf „Speichern” auf der Bearbeitungs-Seite im Editier-Modus.
- Nun wird der Nutzer direkt auf die Nur-Lese-Detailansicht des Deals weitergeleitet, um versehentliche Änderungen zu vermeiden.

## 2.45.0

Layout der Deal-Bearbeitungsseite optimiert und Sicherheitsabfragen über Modal-Dialoge eingeführt.

- **Speichern-Button ganz nach unten verschoben:** Auf der Bearbeitungsseite eines Deals wurde der “Speichern”-Button ganz an das Ende der Seite verschoben.
- **Buttons für Löschen und Abbrechen/Stornieren platziert:** Direkt über dem Speichern-Button befinden sich nun die Buttons “Deal abbrechen (stornieren)” und “Deal löschen”.
- **Einführung von Modal-Dialogen zur Bestätigung:** Statt der bisherigen einfachen Browser-Bestätigung öffnen diese Buttons nun moderne, benutzerfreundliche Modal-Dialoge zur Bestätigung der Aktionen.

## 2.44.4

Übersicht: Kachel „Abgeschlossen" in der Pipeline-Karte verlinkt nun auf die Deals-Liste und zeigt dort alle abgeschlossenen Deals an.

- Wenn ein Nutzer auf die Kachel „Abgeschlossen" in der Pipeline der Übersichtskarte klickt, wird er nun auf `/deals?status=abgeschlossen` weitergeleitet.
- Dadurch lassen sich die bereits erfolgreich beendeten Deals direkt und gefiltert betrachten, anstatt auf die leere ToDo-Seite geführt zu werden.

## 2.44.3

Übersicht: Pipeline-Kacheln verlinken nun auf den zugehörigen Bereich in „Zu erledigen" (ToDos) statt auf die Deals-Liste.

- Wenn ein Nutzer auf eine Pipeline-Kachel der Übersicht klickt, gelangt er nun direkt zu der entsprechenden ToDo-Kategorie im Tab-System der „Zu erledigen"-Seite.
- Bisher führten diese Kacheln fälschlicherweise auf die gefilterte Deals-Liste.

## 2.44.2

Beim Abbrechen/Stornieren eines Deals werden nun auch alle zugehörigen
Aufgaben automatisch geschlossen (erledigt) und nicht nur die Bedingungen.

## 2.44.1

Schönere Benennung und Beschreibung der Option für den nächtlichen Kündigungshinweis-Batch in den Übersetzungstabellen.

- Die Option `kuendigung_hinweise_batch_aktiv` wird nun im Home Assistant Konfigurations-Interface unter dem Namen "Kündigungshinweis-Batch aktiv" mitsamt einer verständlichen Beschreibung angezeigt.

## 2.44.0

„Zu erledigen": das Ausgrauen-statt-Verstecken aus 2.43.0 gilt jetzt für
alle Kacheln, nicht nur für die beiden Prämien-Bereiche.

- Bisher blieben nur "Auf Prämie warten" und "Prämienauszahlung prüfen"
  immer sichtbar. Alle anderen Kategorien - auch "Manuelle Aufgaben" -
  verschwanden weiterhin komplett aus der Navigation, sobald es dort gerade
  nichts gab. Jetzt sind alle acht Kacheln immer da: mit Inhalt normal, ganz
  ohne Inhalt sichtbar ausgegraut statt versteckt - inklusive "Manuelle
  Aufgaben", die weiterhin normal anklickbar bleibt und dahinter unverändert
  den "+ Neue Aufgabe"-Button zeigt.

## 2.43.0

„Zu erledigen": die beiden Prämien-Kacheln verschwinden nie mehr, sondern
werden ausgegraut, wenn es dort wirklich nichts gibt.

- Bislang blieben "Auf Prämie warten" und "Prämienauszahlung prüfen" nur
  sichtbar, solange sie ohne Quelle-Filter Inhalt hätten (2.42.0) - gab es die
  Kategorie auch ungefiltert gar nicht, verschwand die Kachel weiterhin
  komplett. Jetzt sind beide Kacheln immer da: mit Inhalt normal, ohne
  jeglichen Inhalt (auch ungefiltert) sichtbar ausgegraut (gestrichelter
  Rand, gedimmt) statt versteckt. Bleibt weiterhin anklickbar und zeigt dann
  "Aktuell nichts offen."
- Der Hinweistext im Panel unterscheidet jetzt zwei Fälle: "Aktuell nichts
  offen." bei wirklich leerer Kategorie, "Nichts für diese Quelle." wenn nur
  der Filter gerade alles ausblendet.

## 2.42.0

„Zu erledigen": zwei Bugs beim Filtern nach Quelle behoben.

- **Verschwindende Kachel:** Blendete der Quelle-Filter alle Einträge einer
  der beiden Prämien-Kategorien aus, verschwand die zugehörige Kachel
  komplett - von dort aus ließ sich der Filter then nicht mehr zurücksetzen.
  Die Kachel bleibt jetzt (mit Zähler 0 und dem Hinweis "Nichts für diese
  Quelle.") sichtbar, solange es für sie ohne den Filter Einträge gäbe; nur
  wenn eine Kategorie wirklich komplett leer ist, bleibt sie weiterhin weg.
- **"Filtern" sprang auf "Manuelle Aufgaben":** Ein Tab-Wechsel läuft rein
  clientseitig über CSS (kein Seitenaufruf), das versteckte tab-Feld im
  Filterformular enthielt deshalb weiterhin den beim letzten Laden aktiven
  Tab, nicht den gerade sichtbaren. Der Quelle-Filter besteht jetzt aus zwei
  eigenen Formularen - je eines pro Prämien-Tab mit fest eingetragenem
  Tab-Wert - sodass "Filtern" immer auf dem sichtbaren Tab bleibt.
- Neue Tests für beide Fehlerbilder.

## 2.41.1

**Kontoart** in der ToDo-Liste und bei manuellen Aufgaben: Die Kontoart
(z. B. Giro, Depot) wird nun sichtbar zwischen Banknamen und Inhabernamen
angezeigt – auch im Auswahl-Dropdown „Deal" beim Anlegen einer neuen manuellen
Aufgabe (z. B. `Testbank · Depot · Max`).

## 2.41.0

„Zu erledigen": Der „+ Neue Aufgabe"-Button steht jetzt an derselben Stelle
wie der Quelle-Filter.

- Analog zum Quelle-Filter (2.40.0) steht auch „+ Neue Aufgabe" jetzt unter
  der Status-Kachel-Navigation und über dem eigentlichen ToDo-Inhalt, statt
  wie bisher ganz oben vor den Kacheln. Sichtbar bleibt er weiterhin nur auf
  dem Tab „Manuelle Aufgaben".

## 2.40.0

„Zu erledigen": „Neue Aufgabe" hinter einem Button verborgen, Quelle-Filter
unter die Status-Kacheln verschoben.

- „Neue Aufgabe" stand bisher als dauerhaft offenes Formular über den
  Status-Kacheln. Es ist jetzt ein `<details>`-Umschalter ("+ Neue Aufgabe"),
  standardmäßig eingeklappt - reines HTML/CSS wie die übrigen
  Aufklapp-Elemente im Projekt, kein JavaScript.
- Der Quelle-Filter stand bisher ganz oben, unabhängig vom gewählten Tab.
  Er steht jetzt unterhalb der Status-Kacheln und oberhalb des eigentlichen
  ToDo-Inhalts - weiterhin nur sichtbar auf „Auf Prämie warten" und
  „Prämienauszahlung prüfen" (siehe 2.39.0).

## 2.39.0

„Zu erledigen": „Neue Aufgabe"/„Erledigte Aufgaben" und der Quelle-Filter
erscheinen jetzt nur noch dort, wo sie inhaltlich hingehören.

- „Neue Aufgabe" und „Erledigte Aufgaben" waren bisher immer sichtbar,
  unabhängig vom gewählten Tab - dabei gehören beide fachlich zu „Manuelle
  Aufgaben". Sie erscheinen jetzt ausschließlich, wenn dieser Tab aktiv ist.
- Der Quelle-Filter (Spartanien/Bank) ergibt nur auf den beiden Prämien-Tabs
  „Auf Prämie warten" und „Prämienauszahlung prüfen" einen Sinn und wird
  jetzt auch nur dort angezeigt.
- Umgesetzt über CSS (`body:has(#todotab-<slug>:checked) ...`), dieselbe
  Technik wie die bestehende Tab-Umschaltung - kein JavaScript nötig.
- „Manuelle Aufgaben" bleibt jetzt immer als Tab wählbar, auch ganz ohne
  offene Aufgabe - sonst gäbe es keine Möglichkeit mehr, die erste Aufgabe
  anzulegen. Der Tab, der beim Öffnen der Seite automatisch aktiv ist, bleibt
  aber weiterhin die erste Kategorie mit tatsächlichem Inhalt.
- **Kontoart** in der ToDo-Liste („Zu erledigen") und bei manuellen Aufgaben:
  Bei allen abgeleiteten Aufgaben sowie bei manuellen Aufgaben wird die Kontoart
  (z. B. Giro, Depot) gut sichtbar zwischen dem Banknamen und dem Inhabernamen
  angezeigt (z. B. `Testbank · Depot · Max`). Auch im Auswahl-Dropdown „Deal"
  beim Anlegen einer neuen manuellen Aufgabe wird die Kontoart nun konsequent
  zwischen Bank und Inhaber aufgeführt.

## 2.38.1

Test-Benachrichtigung entfernt: Button und Endpoint gelöscht.

## 2.38.0

„Zu erledigen": Status-Navigation von einer scrollenden Pillen-Reihe auf ein
Kachel-Grid umgestellt.

- Bei 6-8 Kategorien mit teils langen Labels (z. B. "Prämienauszahlung
  prüfen") lief die bisherige Pillen-Reihe seitlich aus dem Bildschirm und
  musste horizontal gescrollt werden; die unterschiedlich breiten Pillen
  wirkten zudem unruhig aneinandergereiht.
- Jetzt ein zweispaltiges Kachel-Grid: gleich breite, ausgerichtete Kacheln,
  kein Scrollen mehr nötig (wächst nach unten statt zur Seite). Jede Kachel
  zeigt einen farbigen Punkt in derselben Kategoriefarbe wie der Tag in der
  Gruppen-Überschrift darunter - eine durchgängige Farbsprache zwischen
  Navigation und Inhalt. Ab 560px Breite wächst das Grid automatisch auf mehr
  Spalten.

## 2.37.1

Keine Verhaltensänderung.

## 2.37.0

Neuer Status **"Prämienauszahlung prüfen"**: der bisherige Status "Auf Prämie
warten" trennt jetzt danach, ob das nächste Prüfdatum schon erreicht ist.

- Der bisherige Status `"Auf Prämie warten"` deckte zwei fachlich
  unterschiedliche Situationen ab: "wartet noch" und "sollte jetzt geprüft
  werden". Ein Deal ist jetzt in `"Prämienauszahlung prüfen"`, sobald das
  Prüfdatum einer offenen Prämie erreicht oder überschritten ist - solange
  alle offenen Prämien noch in der Zukunft liegen, bleibt er in
  `"Auf Prämie warten"`.
- Der neue Status erscheint in der Pipeline-Karte der Übersicht und ist auf
  der "Zu erledigen"-Seite voll integriert (eigener Tab, Sortierung nach
  Prüfdatum, Filterung nach der Quelle der Prämie).
- Die Zuordnung der ToDo-Zeilen erfolgt je Einzelprämie nach ihrem eigenen
  Prüfdatum, nicht pauschal nach dem Deal-Status - ein Deal mit mehreren
  offenen Prämien kann dadurch gleichzeitig in beiden Kategorien auftauchen,
  jede Prämie an der fachlich richtigen Stelle. Der Deal-Status selbst bleibt
  eindeutig: er zeigt "Prämienauszahlung prüfen", sobald irgendeine offene
  Prämie fällig ist.

## 2.36.0

„Alle neu analysieren" frischt jetzt gezielt nur die handlungsrelevanten Karten
auf, entfernt veraltete Dubletten und erklärt sich im Bestätigungsdialog.

- **Nur vorgeschlagen/zu prüfen wird neu analysiert.** Funde, die aktuell keine
  vorgeschlagene oder zu prüfende Karte haben, werden übersprungen -
  automatisch abgelehnte Karten bleiben unangetastet (keine ungewollte
  Wiederbelebung), übernommene und verworfene ohnehin. Nebeneffekt: deutlich
  weniger API-Aufrufe, weil nur die wirklich gemeinten Karten erneut extrahiert
  werden. Neue, noch nicht vorgeschlagene Angebote sucht weiterhin „Jetzt
  suchen".
- **Keine Dubletten mehr.** Findet die Neuanalyse mehr oder andere Bedingungen
  (dadurch anderer Inhalts-Hash), ersetzt die aufgefrischte Karte die alte
  automatisch - die veraltete, noch offene Zeile derselben URL/Person wird
  entfernt statt daneben stehen zu bleiben. Damit lassen sich bestehende
  Vorschläge auf die neue Struktur (Bedingungs-Kennzahlen, Teilprämien-
  Zuordnung, Prämienzweck) heben, ohne vorher „Zurücksetzen" zu brauchen.
- **Erklärender Bestätigungsdialog.** Der Dialog hinter „Alle neu analysieren"
  benennt jetzt ausdrücklich, was aufgefrischt wird, was unangetastet bleibt
  und dass neue Angebote über „Jetzt suchen" kommen.

## 2.35.2

- **Optimierung der ToDo-Liste ("Zu erledigen"):**
  - Sortierung der Kategorie "Auf Prämie warten" nach dem Datum der nächsten Prüfung aufsteigend (frühestes Datum ganz oben).
  - Neuer Filter oben in der ToDo-Liste für die Quelle der Prämie (Spartanien oder Bank). Der Filter bleibt bei allen Aktionen (Abhaken, Verschieben, Löschen) erhalten.

## 2.35.1

- **Fehlerbehebung bei "Auf Prämie warten":**
  - Das erwartete Auszahlungsdatum korrigiert nun automatisch das nächste Prüfdatum, falls dieses in der Vergangenheit oder vor dem erwarteten Monat liegt.
  - Beim Ändern des erwarteten Auszahlungsdatums wird das manuelle Prüfdatum zurückgesetzt.
  - Mehrere offene Prämien desselben Deals werden nun als separate Zeilen angezeigt statt in einem modalen Dialog gruppiert zu werden.

## 2.35.0

Teilprämien und ihre Bedingungen beim Anlegen sichtbar - und der Prämienzweck
bleibt am Deal erhalten.

**A) Zuordnung in der Anlegen-Vorschau sichtbar.** Der „Übernehmen bestätigen"-
Dialog zeigt jetzt zu jeder Teilprämie ihren Zweck („für den
Kontowechselservice") und zu jeder Bedingung, falls zutreffend, die
Teilbetrags-Zuordnung („nur für 250 € von Santander"). So ist schon beim
Anlegen erkennbar, welche Auflage zu welchem Teilbetrag gehört und welche
Zeilen sich weglassen lassen, wenn ein Teilbetrag nicht mitgenommen wird
(bisher lief das nur verdeckt mit).

**B) Prämienzweck wird am Deal gespeichert.** Die reale Prämie kannte bisher nur
Quelle und Betrag; der Zweck-Text aus dem Angebot ging beim Übernehmen
verloren. Jede Prämie trägt jetzt ein optionales Feld `zweck` - die Extraktion
füllt es aus der Prämien-Aufteilung, es wandert über die Vorschau bis zum Deal
und erscheint auf der Deal-Detailseite hinter dem Betrag. Neue Migration `0018`
ergänzt die Spalte `zweck` auf `praemien`.

## 2.34.0

Bedingungen werden auf der Vorschlagskarte jetzt nach Teilprämie gruppiert
dargestellt.

- Sind einer oder mehreren Bedingungen Teilbeträge zugeordnet (`gilt_fuer`,
  siehe 2.33.0), zeigt die Karte je Teilbetrag eine eigene Gruppe mit
  Überschrift: zuerst **„Für alle Teilbeträge"** (Grundvoraussetzungen ohne
  Zuordnung), darunter je eine Gruppe **„Nur für &lt;Teilprämie&gt;"** mit den
  Auflagen, die genau diesen Teilbetrag freischalten. So ist auf einen Blick
  erkennbar, welche Bedingungen sich erübrigen, wenn ein Teilbetrag bewusst
  nicht mitgenommen wird.
- Gibt es keine Teilbetrags-Zuordnung, bleibt die Bedingungsliste wie bisher
  schlicht (flach, ohne Überschriften). Der Inline-Hinweis „nur für …" bleibt
  auf der Deal-Detailseite erhalten; keine Datenbank- oder Schemaänderung
  nötig, reine Anzeige.

## 2.33.0

Bedingungen lassen sich jetzt einzelnen Teilprämien zuordnen - sichtbar, welche
Auflage zu welchem Teilbetrag gehört.

**Warum:** Angebote teilen die Prämie oft in Teilbeträge mit je eigenen
Auflagen auf (z. B. Santander BestGiro: 50 € nur für die Kontoeröffnung, 250 €
nur für den Kontowechselservice). Wer einen aufwendigen Teilbetrag bewusst
nicht mitnehmen will, konnte bisher nicht erkennen, welche Bedingungen dafür
überhaupt nötig sind und welche zum ganzen Angebot gehören.

- Jede Bedingung trägt jetzt ein optionales Feld **`gilt_fuer`**: den Label der
  Teilprämie, die sie freischaltet (z. B. „250 € für den Kontowechselservice").
  Die KI-Extraktion füllt es nur, wenn sich die Prämie in Teilbeträge mit je
  eigenen Auflagen zerlegt; Grundvoraussetzungen fürs ganze Angebot (Neukunde
  sein, Konto online eröffnen) bleiben ohne Label.
- Auf der Vorschlagskarte und in der Deal-Detailansicht erscheint diese
  Zuordnung als dezenter Hinweis („nur für 250 € für den Kontowechselservice")
  unter der jeweiligen Bedingung. Beim Übernehmen wandert der Label über die
  Vorschau bis zur angelegten Bedingung mit.
- Neue Datenbank-Migration `0017` ergänzt die Spalte `gilt_fuer` auf
  `bedingungen` und `vorschlag_bedingungen`.

## 2.32.0

KI-Deal-Finder erkennt jetzt deutlich mehr Bedingungen - und stellt sie
strukturiert dar.

**Warum:** Bei Angeboten wie der awa7® Visa Kreditkarte tauchte auf der
Vorschlagskarte nur "1 Bedingung: Kontoeröffnung" auf, obwohl der Deal in
Wahrheit verlangt, die Karte *innerhalb von vier Wochen mindestens zweimal
für insgesamt 50 €* einzusetzen. Ursache war nicht das KI-Modell, sondern der
**Eingabetext**: dealdoktor und mydealz liefern im RSS-Feed pro Beitrag zwei
Felder - einen gekürzten Anreißer (`<description>`) und den vollständigen
Artikel (`<content:encoded>`). Der Finder las bisher nur den Anreißer, in dem
die eigentliche Auflage (Fußnoten, "Bonusbedingungen") gar nicht steht.

- **Volltext statt Anreißer:** `finder/quellen.py` bevorzugt jetzt
  `<content:encoded>` und fällt nur, wenn es fehlt, auf `<description>`
  zurück. Damit sieht die KI-Extraktion die kompletten Bonusbedingungen.
  Nebenwirkung: Der Rohtext ändert sich, weshalb bereits gecachte Funde beim
  nächsten Lauf **einmalig neu analysiert** werden (danach wie gewohnt aus dem
  Cache).
- **Bessere Prompts:** Der Extraktions-Prompt fordert nun ausdrücklich *alle*
  Bedingungen inklusive Fußnoten/Kleingedrucktem, verlangt die konkreten
  Zahlen (Anzahl, Betrag, Frist) wörtlich in der Beschreibung und weist an,
  abgelaufene Alt-Aktionen sowie fremde, nur nebenbei verlinkte Deals zu
  ignorieren. Der Themen-Check bewertet ebenfalls nur noch das Hauptangebot.
  Die beiden Websuche-Prompts (Kündigungsweg, Kunden-werben-Kunden) bevorzugen
  jetzt offizielle Quellen bzw. die konkrete Programm-Seite.
- **Strukturierte Bedingungen:** Jede Bedingung trägt jetzt optionale
  Kennzahlen (Anzahl, Betrag in €, Frist in Wochen). Auf der Vorschlagskarte
  und in der Deal-Detailansicht erscheinen sie als kompakte Kurzform
  ("2× · 50 € · 4 Wochen"); beim Übernehmen wandern sie über die Vorschau bis
  zur angelegten Bedingung mit. Die Freitext-Beschreibung bleibt die
  verbindliche Quelle - fehlt eine Kennzahl im Angebot, bleibt sie leer
  (kein geratener Wert).
- Neue Datenbank-Migration `0016` ergänzt die Spalten `anzahl`,
  `betrag_euro` und `frist_wochen` auf `bedingungen` und
  `vorschlag_bedingungen`.

## 2.31.0

Erwachsene werden jetzt auch von reinen Kinderdeals ausgeschlossen -
symmetrisch zur bisherigen Regel für Kinder bei Erwachsenen-Deals - und
lassen sich über einen einklappbaren Button ergänzen.

- Bisher schloss die Fachlogik nur Minderjährige von reinen
  Erwachsenen-Angeboten aus; umgekehrt bekamen Erwachsene auch einen echten
  Kinderdeal (z. B. ein Junior-Depot) ganz normal vorgeschlagen, weil die
  Bewertung selbst keine Altersprüfung kennt. Jetzt gilt dieselbe Prüfung in
  beide Richtungen (`_ist_anwendbar`): ein Kinderdeal bekommt nur
  minderjährige Inhaber, ein reines Erwachsenen-Angebot nur volljährige -
  jeweils inklusive der automatischen Bereinigung stehen gebliebener
  Alt-Zeilen (inline und im pauschalen Vorablauf, vormals nur für Kinder).
- Der "Für wen übernehmen?"-Dialog zeigt die dadurch ausgeschlossene Gruppe
  nicht mehr direkt als Checkbox, sondern hinter einem einklappbaren
  **"+ Kinder"**- bzw. **"+ Eltern"**-Button - Übernehmen bleibt damit
  bewusst möglich, drängt sich aber nicht mehr auf.

## 2.30.1

Keine Verhaltensänderung, nur zusätzliche Testabsicherung: bestätigt per
Test, dass ein reiner Erwachsenen-Deal nach Übernahme durch beide
Erwachsenen vollständig aus den Vorschlägen verschwindet - sowohl bei nur
den Erwachsenen als auch mit beiden Kindern zusätzlich über "trotzdem
hinzufügen" (2.30.0).

## 2.30.0

"Für wen übernehmen?"-Dialog: ausgeschlossene Kinder trotzdem hinzufügen
können.

- Ein minderjähriger Inhaber ohne eigene Zeile zu einem Fund (weil das
  Angebot laut KI-Extraktion kein Kinderdeal ist, siehe 2.28.0/2.29.0) war
  bisher endgültig außen vor - stellt sich die automatische Einschätzung im
  Einzelfall als falsch heraus, gab es keinen Weg zurück außer über die neue
  Inhaber-Seite oder direkten Datenbankzugriff.
- Der Dialog zeigt jetzt unterhalb der vorgeschlagenen Personen zusätzlich
  alle minderjährigen Inhaber ohne eigene Zeile zu diesem Fund als
  **"trotzdem hinzufügen"**-Option (unangehakt). Wird eine davon ausgewählt
  und übernommen, entsteht für sie ein Deal mit denselben Prämien-/
  Bedingungen-/Aufgaben-Angaben wie für die übrigen ausgewählten Personen -
  Bank, Kontoart und Prämienbetrag werden vom ersten ausgewählten Mitglied
  übernommen.

## 2.29.0

Neue Seite **Inhaber**: einzige Stelle, an der sich "minderjährig" setzen
lässt.

- Bisher gab es dafür keine Oberfläche - ein neuer Inhaber entsteht
  automatisch beim Anlegen des ersten Deals für diesen Namen
  (`helpers.get_or_create_inhaber`) und gilt dabei immer als erwachsen, egal
  ob es sich tatsächlich um ein Kind handelt. Ergebnis: die ganze
  Kinder-Logik aus 2.28.0 (Kinder nur bei Kinderdeals auswählbar, Karte
  verschwindet nach Übernahme durch alle Erwachsenen) griff für ein so
  angelegtes Kind nie, weil die App es intern von einem Erwachsenen gar
  nicht unterscheiden konnte - im "Übernehmen"-Dialog blieben alle
  Haushaltsmitglieder gleichberechtigt und vorausgewählt.
- Über "Mehr → Inhaber" lässt sich jetzt für jedes Haushaltsmitglied ein
  Häkchen "minderjährig" setzen und mit einem gemeinsamen
  Speichern-Button übernehmen. Wirkt sofort auf neue Vorschläge sowie beim
  nächsten Lauf auf schon bestehende (siehe 2.28.0).

## 2.28.0

Kinder in Vorschlags-Gruppen: nur noch auswählbar, wenn sie wirklich
zutreffen, und verworfene Vorschläge lassen sich doch noch übernehmen.

- Ein minderjähriger Inhaber wird einem Angebot seit 2.24.0 nur noch
  vorgeschlagen, wenn es laut KI-Extraktion (auch) für Kinder abschließbar
  ist. Bereits vorher angelegte, noch offene Kinder-Zeilen zu reinen
  Erwachsenen-Deals blieben davon aber unberührt und hingen für immer offen:
  im "Übernehmen"-Dialog standen weiterhin alle Haushaltsmitglieder inkl.
  Kinder, und selbst nachdem alle Erwachsenen übernommen hatten, blieb die
  Vorschlags-Karte wegen der liegen gebliebenen Kinder-Zeile sichtbar. Der
  Lauf räumt eine solche Alt-Zeile jetzt automatisch weg, sobald er
  feststellt, dass sie für dieses Kind gar nicht zutrifft - sowohl beim
  Verarbeiten desselben Funds als auch pauschal vorab für Funde, die gar
  nicht mehr erneut geladen werden (z.B. weil der Deal inzwischen abgelaufen
  ist), rein anhand des schon vorhandenen lokalen Caches, ohne neuen
  API-Aufruf. Die Zeile wird dabei **gelöscht statt verworfen** - für ein
  Kind bei einem reinen Erwachsenen-Angebot ist weder Übernehmen noch
  Verwerfen eine sinnvolle Handlung, das Angebot gilt schlicht nicht.
- Jede Karte in der "Verworfen"-Sektion zeigt jetzt zusätzlich, für welche(n)
  Inhaber der Fund verworfen wurde, und hat einen **"Doch
  übernehmen"**-Button - bewusstes Überstimmen einer eigenen
  Fehlentscheidung (z.B. ein Vorschlag, der nur verworfen wurde, um eine
  lästig offen bleibende Karte loszuwerden, obwohl der Deal eigentlich
  zutraf), genau wie "Trotzdem übernehmen" bereits bei automatisch
  abgelehnten Funden funktioniert. Ein automatisch (s.o.) bereinigter
  Kinder-Vorschlag taucht dort nicht auf, weil er gelöscht statt verworfen
  wird.

## 2.27.1

Zwei Anpassungen am nächtlichen Kündigungshinweis-Batch (siehe 2.27.0):

- Läuft jetzt um **02:00 Uhr** statt 05:00 Uhr.
- Neue eigene Option `kuendigung_hinweise_batch_aktiv`, um ihn unabhängig
  vom KI-Deal-Finder ein-/auszuschalten - bisher hing er an
  `taeglicher_lauf_aktiv` und ließ sich nicht getrennt deaktivieren.

## 2.27.0

Kündigungsweg-Recherche komplett vom Anlegen eines Deals entkoppelt: der
API-Aufruf lief bisher überall dort synchron mit, wo ein Deal entsteht
(Formular, JSON-Import, Übernehmen eines Vorschlags) und konnte für eine
noch nie recherchierte Bank+Kontoart-Kombination spürbar verzögern (der
DB-Cache greift erst ab dem zweiten Mal). Jetzt prüft das Anlegen nur noch
die feste Tabelle (kostenlos, sofort) - findet sie nichts, bleibt das Feld
zunächst leer.

Stattdessen läuft nachts um 05:00 Uhr (eine Stunde vor dem KI-Deal-Finder)
ein neuer Batch, der für alle offenen Deals ohne Kündigungshinweis einen
nachträgt: zuerst wieder die feste Tabelle, sonst per KI-Websuche mit
demselben Cache wie bisher - eine Bank+Kontoart-Kombination wird dabei über
alle betroffenen Deals hinweg nur einmal recherchiert. Stornierte Deals
werden übersprungen, ein bereits gesetzter oder von Hand eingetragener
Hinweis nie überschrieben. Steuerbar über dieselbe Option wie der
KI-Deal-Finder (`taeglicher_lauf_aktiv`).

## 2.26.1

"Übernehmen" hing beim Klick auf "Jetzt anlegen" trotz der Hintergrund-KwK-
Recherche (siehe 2.24.1) weiterhin spürbar - Ursache war eine zweite, bisher
unangetastete synchrone KI-Websuche: die Kündigungsweg-Recherche
(helpers.kuendigung_vorschlag), die für jede noch nie recherchierte
Bank+Kontoart-Kombination ganz ohne Zeitlimit lief (ihr DB-Cache greift erst
ab dem zweiten Mal). Läuft jetzt wie die KwK-Recherche schon beim Öffnen der
Vorschau im Hintergrund (siehe uebernehmen_vorschau), statt erst beim
Bestätigen synchron zu starten. Beide Recherchen teilen sich außerdem ein
gemeinsames Zeitbudget von jetzt 2 Sekunden (vorher 4 Sekunden nur für KwK)
- die Wartezeiten addieren sich nicht, "Übernehmen" wartet also insgesamt
nie länger als 2 Sekunden auf beide zusammen. Ist die Kündigungsweg-
Recherche dann noch nicht fertig oder findet nichts Verlässliches, bleibt
das Feld einfach leer (wie bisher schon bei fehlendem API-Key).

## 2.26.0

Deal bearbeiten (Todoist "Ki/Prämien webapp", Prio 1): ein Speichern-Button
statt vieler.

- Die Bearbeiten-Seite eines Deals hatte bisher für jede Prämien-,
  Bedingungen- und Aufgaben-Zeile einen eigenen "Speichern"-Button, dazu
  einen weiteren für die Kontodaten - leicht zu übersehen, wenn nach einer
  Änderung an mehreren Stellen nicht überall gespeichert wurde. Jetzt hängen
  Kontodaten, Kündigung, Steuer/Notiz sowie alle Prämien-/Bedingungen-/
  Aufgaben-Zeilen an einem gemeinsamen Formular mit **einem** Speichern-Button
  ganz unten, der alles auf einmal sichert. Zeilen hinzufügen/löschen bleibt
  weiterhin sofort wirksam (kein Speichern nötig). Links sowie Stornieren/
  Löschen bleiben unverändert eigene, sofort wirksame Aktionen.

## 2.25.0

Vier kleinere Verbesserungen (Todoist "Ki/Prämien webapp", Prio 4):

- **Test-Benachrichtigung:** Auf der Vorschläge-Seite gibt es unter
  "Weitere Aktionen" jetzt einen Button "Test-Benachrichtigung senden" -
  schickt sofort eine Testnachricht an die konfigurierten Geräte, unabhängig
  vom täglichen Lauf und ohne dass dafür erst ein neuer Fund auftauchen
  muss. So lässt sich die Konfiguration (`benachrichtigungsgeraete` etc.)
  gezielt prüfen ("Funktioniert die Benachrichtigung?"), statt bis zum
  nächsten echten Fund oder 06:00 Uhr zu warten. Das Ergebnis (angekommen
  oder nicht) wird direkt auf der Seite angezeigt.
- **mydealz-Feed "konto-kreditkarten" ergänzt:** Die Add-on-Option
  `mydealz_gruppe` akzeptiert jetzt wie `dealdoktor_feed_url` mehrere
  kommagetrennte Gruppen statt nur einer einzigen. Vorgabe ist jetzt
  `vertraege-finanzen,konto-kreditkarten` statt nur `vertraege-finanzen` -
  der KI-Deal-Finder deckt damit zusätzlich die mydealz-Gruppe
  "Konto/Kreditkarten" ab. Eine nicht erreichbare Gruppe blockiert die
  anderen nicht (gleiches Verhalten wie bei den dealdoktor-Feeds).
- **Vollständigkeits-Seite ohne erledigte Deals:** Abgeschlossene Deals
  (storniert oder bestätigt gekündigt) tauchen auf `/completeness` nicht
  mehr auf und zählen auch nicht mehr mit - an ihren Daten ändert sich
  nichts mehr, sie gehörten dort nicht mehr hin und verwässerten den
  "gepflegt"-Anteil unnötig.
- **"KwK möglich?" auch bei manueller Anlage:** Schlägt die automatische
  Kunden-wirbt-Kunden-Recherche beim manuellen Anlegen eines Deals fehl
  (Formular `/deals/new` or JSON-Import), legt die App jetzt wie beim
  Übernehmen eines Vorschlags eine Erinnerungs-Aufgabe "KwK möglich?
  Kunden-wirbt-Kunden-Programm manuell prüfen." an, statt den Fehlschlag
  stillschweigend zu verwerfen.

## 2.24.5

Die Übernehmen-Vorschau (siehe 2.24.1) zeigte bisher nur Bank und Kontoart
editierbar an, alle übrigen Felder read-only. Auf Nutzerwunsch jetzt genauer
abgestimmt:

- Bank, Inhaber und Kontoart werden weiterhin angezeigt, aber nur noch
  read-only (auch Bank/Kontoart waren zwischenzeitlich editierbar, das ist
  jetzt zurückgenommen) - sie bestimmen u. a., ob jemand als Neukunde gilt,
  und sollen unverändert aus der KI-Extraktion stammen.
- Stattdessen jetzt editierbar: Kündbar ab, Kommentar, sowie Prämien
  (Quelle/Betrag/erwartete Auszahlung/erhalten), Bedingungen (Beschreibung/
  fällig bis), freie Aufgaben (neu hinzufügbar) und Links (Bezeichnung/URL) -
  jeweils als Zeilen mit ein paar zusätzlichen leeren Zeilen zum Ergänzen.
  Alle anderen Detailfelder der normalen Deal-Seite (Kontonummer,
  Zugangsdaten, weitere Kündigungsfelder, Freibetrag, Prämien auf Sparkonto)
  werden auf dieser Seite gar nicht erst angezeigt, da sie bei KI-Vorschlägen
  ohnehin nie befüllt sind.

## 2.24.3

Fehlerbehebung Deal-Detailansicht (siehe 2.24.0): lange Werte wie die
Kündigungs-Anweisungen samt Link liefen über den rechten Kartenrand hinaus,
statt innerhalb des Feldes umzubrechen - Ursache war eine Flexbox-Falle
(Wert-Spalte hatte kein `min-width: 0`, wodurch sie sich nicht unter ihre
Inhaltsbreite schrumpfen ließ). Die Wert-Spalte bricht lange Wörter/Links
jetzt bei Bedarf um und bleibt sichtbar innerhalb der Karte.

## 2.24.2

Die vier Kacheln der "Vorschläge"-Übersicht auf der Startseite (Vorgeschlagen/
Zu prüfen/Abgelehnt/Verworfen, siehe 2.24.0) brachen auf schmalen
Bildschirmen (Handy) in zwei Zeilen um, weil sie dieselbe Flex-Regel wie die
sechsteilige Pipeline-Kachel nutzten, die absichtlich umbricht. Die
Vorschläge-Kachel hat jetzt eine eigene Regel (`pipe-4`), die alle vier
Segmente per `flex-wrap: nowrap` in einer Zeile hält und Schrift/Abstände
dafür etwas verkleinert - die sechsteilige Pipeline-Kachel bleibt unverändert
zweizeilig.

## 2.24.1

Vier Verbesserungen am "Übernehmen"-Ablauf für KI-Vorschläge:

- Im Übernehmen-Dialog sind jetzt standardmäßig nur erwachsene Inhaber
  angehakt - ein minderjähriger Inhaber taucht als Option nur auf, wenn das
  Angebot laut KI-Extraktion überhaupt für Kinder geeignet ist, wurde bisher
  aber trotzdem automatisch mitausgewählt. Jetzt muss man ihn bewusst
  anhaken, damit nicht versehentlich ein Deal für ein Kind mit übernommen
  wird.
- Neu angelegte Bedingungen starten jetzt immer unabgehakt ("nicht
  erfüllt"), auch beim Übernehmen eines Vorschlags. Bisher konnte die
  KI-Einschätzung einer Bedingung ("erfüllt") direkt in den fertigen Deal
  übernommen werden, ohne dass sie/er das je bestätigt hat - eine
  Einschätzung ist keine bestätigte Erfüllung.
- "Übernehmen" konnte bei mehreren ausgewählten Inhabern spürbar hängen: die
  Kunden-wirbt-Kunden-Recherche (KI-Websuche ohne Zeitlimit) lief bisher
  synchron und pro Inhaber einzeln. Sie läuft jetzt einmal je Bank+Kontoart
  im Hintergrund, während die neue Vorschau (siehe nächster Punkt) offen
  ist; wartet beim Bestätigen höchstens noch 4 Sekunden auf das Ergebnis und
  legt sonst statt eines Hinweis-Banners direkt eine Erinnerungs-Aufgabe
  "KwK möglich?" an.
- Vor dem eigentlichen Anlegen zeigt "Übernehmen" jetzt zunächst eine
  Vorschau mit Bank und Kontoart in einem Bearbeitungsformular - Felder, die
  für alle ausgewählten Inhaber ohnehin identisch sind (derselbe Fund).
  Prämien und Bedingungen bleiben unverändert aus dem Vorschlag und werden
  nur zur Kontrolle mit angezeigt. Erst das Bestätigen dieser Vorschau legt
  die Deals wirklich an.

## 2.24.0

Sechs kleinere Verbesserungen an Vorschläge, Deals und ToDos:

- **Verwerfen behält den Filter:** Wird ein Vorschlag aus einer gefilterten
  Ansicht heraus (z. B. nur Quelle "mydealz", Status "zu prüfen") verworfen,
  führt der Redirect jetzt in dieselbe gefilterte Ansicht zurück statt die
  Filterleiste unbemerkt zurückzusetzen. Betrifft sowohl das Verwerfen
  einzelner Vorschläge als auch "Alle verwerfen" bei Duplikat-Kacheln.
- **Übersicht zeigt alle vier Vorschläge-Zahlen:** Die Kachel "Vorschläge"
  auf der Startseite fasste "Automatisch abgelehnt" und "Verworfen" bisher
  zu einer Zahl zusammen. Jetzt stehen dort wie auf der Vorschläge-Seite
  selbst vier eigene Segmente (Vorgeschlagen, Zu prüfen, Abgelehnt,
  Verworfen), jedes verlinkt auf die passend gefilterte Ansicht.
- **Automatische Aufgabe "Spartanien Tracking überprüfen":** Sobald ein Deal
  eine Prämie mit Quelle "Spartanien" trägt - egal ob per KI-Vorschlag
  übernommen, per JSON importiert, manuell angelegt oder nachträglich
  hinzugefügt/geändert - legt die App automatisch diese Aufgabe an (einmalig,
  keine Duplikate bei mehreren Spartanien-Prämien am selben Deal).
- **Deal-Detailansicht vor dem Bearbeiten:** Ein Klick auf einen Deal in der
  Deals-Liste öffnet jetzt zuerst eine Nur-Lese-Übersicht aller erfassten
  Daten (Konto, Kündigung, Prämien, Bedingungen, Aufgaben, Links) statt
  direkt das Bearbeiten-Formular - mit eigenem "Bearbeiten"-Button, wenn
  wirklich etwas geändert werden soll. Verhindert versehentliche Änderungen
  beim bloßen Nachschauen.
- **Neuer Verwerfen-Grund "Nicht anwendbar":** Ergänzt die bisherigen vier
  Gründe (Duplikat, Bedingungen zu aufwendig, noch nicht wieder Neukunde,
  Prämie zu niedrig) für Fälle, die in keine der bestehenden Kategorien
  passen.
- **Prüfdatum bei "Auf Prämie warten":** Jede offene Prämie zeigt in der
  ToDo-Liste jetzt an, bis wann sie zuletzt/als nächstes auf Eingang geprüft
  wurde (Startwert: erwartetes Auszahlungsdatum, sonst heute) - ein Klick auf
  "+2 Wochen" schiebt das Datum weiter. Reiner Merkposten fürs
  Prämien-Hopping, damit klar bleibt, welche Prämie schon gecheckt wurde und
  welche als nächstes dran ist.

## 2.23.3

Fehlerbehebung: bei aktivem Status-Filter (z. B. nur "Zu prüfen") konnte
eine quellenübergreifende Duplikat-Kachel angezeigt werden, obwohl der
Chip darüber "0 zu prüfen" zeigte. Ursache: die Kachel-Liste wurde bei
aktivem Filter aus den nach Status vorgefilterten Einzel-Fundstellen neu
gebündelt, der Zähler-Chip dagegen aus der ungefilterten Bündelung (bester
Status je Deal gewinnt) - ein Deal mit einer besseren und einer
schlechteren Fundstelle zählte deshalb z. B. als "vorgeschlagen", tauchte
beim Filtern auf "zu prüfen" aber trotzdem mit den übrigen, schlechteren
Fundstellen als eigene Karte auf. Jetzt wird nur noch einmal gebündelt und
der Filter danach auf dasselbe Ergebnis angewendet - Zähler und
angezeigte Karten sind damit immer konsistent.

## 2.23.2

"Alle verwerfen" bei quellenübergreifend gebündelten Duplikat-Kacheln
(z. B. mydealz + Spartanien derselbe Deal) fragt jetzt wie beim einzelnen
Vorschlag per Dialog nach dem Grund (Mehrfachauswahl, "Duplikat"
voreingestellt) statt ihn fest auf "Duplikat" zu setzen - z. B. wenn beide
Fundstellen tatsächlich an einer zu niedrigen Prämie scheitern. Unverändert:
wählt man stattdessen über "Ausgewählte übernehmen" eine einzelne Fundstelle
aus, werden die übrigen weiterhin automatisch mit Grund "Duplikat" verworfen.

## 2.23.1

Neuer Grund "Prämie zu niedrig" bei den Verwerfen-Optionen (bisher:
Duplikat, Bedingungen zu aufwendig, noch nicht wieder Neukunde) - deckt
den Fall ab, dass ein Fund zwar durchgeht (z. B. knapp über der
Mindestprämie), sich aber trotzdem nicht lohnt.

## 2.23.0

Automatisch abgelehnte Vorschläge zeigen jetzt oben auf der Kachel, direkt
unter den Tags, gut sichtbar die konkrete(n) Begründung(en) (z. B. "Prämie
liegt unter der Mindestprämie", "Bedingung nicht erfüllbar: Gehaltseingang
nötig", "bereits Neukunde in der Sperrfrist") - bisher stand das nur
versteckt im "Übernehmen"-Dialog. Betrifft sowohl einzelne Vorschläge als
auch quellenübergreifend gebündelte Duplikat-Kacheln (mydealz + Spartanien
etc.); haben mehrere Empfänger einer Gruppe unterschiedliche Gründe (z. B.
Sperrfrist nur für eine Person), werden alle vereint gezeigt, doppelte
Gründe nur einmal.

## 2.22.2

Die Lauf-Zusammenfassungstabelle ("Letzter Lauf erfolgreich" aufgeklappt)
sprengte auf schmalen Handy-Bildschirmen die Breite - "SPARTANIEN" und
"DEALDOKTOR" liefen ins horizontale Scrollen. Auf Bildschirmen bis 600px
Breite heißen die Quellen-Spalten jetzt MD/SP/DD statt ausgeschrieben,
Abstände und Schrift sind enger, die Zeilenbeschriftung darf umbrechen -
auf größeren Bildschirmen unverändert die vollen Quellennamen. Keine
Änderung an den Zahlen selbst.

## 2.22.1

"Alle neu analysieren" und "Zurücksetzen" stecken jetzt standardmäßig
eingeklappt hinter einem neuen Dropdown "Weitere Aktionen" neben "Jetzt
suchen" - im Alltag wird praktisch nur "Jetzt suchen" gebraucht, die beiden
anderen sind seltener nötig und lösen bei Fehlklick teuren Neu-Abgleich
bzw. unwiderrufliches Löschen aus. Keine Verhaltensänderung an den Buttons
selbst, nur an ihrer Sichtbarkeit.

## 2.22.0

"Jetzt suchen" und "Alle neu analysieren" liefen bisher synchron im
Request - bei vielen Funden dauerte das spürbar, ohne dass währenddessen
irgendein Feedback sichtbar war. Beide Buttons starten den Lauf jetzt in
einem Hintergrund-Thread und laden die Seite danach automatisch neu: der
grüne Status-Text zeigt sofort orange "Suche läuft ..." mit dem neuen
Zeitstempel an, die Seite lädt alle drei Sekunden neu und zeigt automatisch
das fertige Ergebnis, sobald der Lauf durch ist. Ein zeitgleicher Klick auf
beide Buttons oder ein Zusammentreffen mit dem geplanten 06:00-Lauf startet
keinen zweiten parallelen Lauf mehr (gemeinsame Sperre), da zwei gleichzeitige
Läufe sonst konkurrierend in dieselbe SQLite-Datenbank geschrieben hätten.
Außerdem entfernt: das Wort "Details" beim aufklappbaren Status-Text - der
grüne/orange Text selbst ist bereits der Klick-Bereich zum Auf-/Zuklappen.

## 2.21.0

Der KI-Deal-Finder liest bei dealdoktor jetzt zusätzlich zur Rubrik
"Bonus-Deals" auch die Themenwelt "Banken & Versicherung"
(`https://www.dealdoktor.de/themenwelten/banken-versicherung/feed/`) - dort
laufen teils andere Konto-/Depot-/Versicherungs-Prämien auf, die im
Bonus-Deals-Feed nicht auftauchen. Die Add-on-Option `dealdoktor_feed_url`
akzeptiert dafür jetzt mehrere, durch Komma getrennte Feed-URLs (analog zu
`benachrichtigungsgeraete`) statt nur einer einzelnen - bestehende
Installationen mit einer einzelnen URL laufen unverändert weiter. Fällt
einer der Feeds aus (z. B. geändertes URL-Schema), wird nur dieser eine
übersprungen, die übrigen Quellen laufen normal weiter.

## 2.20.3

Klarstellung: the Dialog von "Zurücksetzen" hieß "...und neu starten?" und
sprach von "danach beginnt 'Jetzt suchen' komplett frisch" - das ließ sich
so lesen, als würde der Button selbst eine neue Suche anstoßen. Tatsächlich
löscht er nur (kein Aufruf des Finder-Laufs) - der Dialogtitel heißt jetzt
schlicht "Alle Vorschläge löschen?" und der Text sagt ausdrücklich, dass
danach zusätzlich "Jetzt suchen" geklickt werden muss. Keine
Verhaltensänderung.

## 2.20.2

Klarstellung: der Bestätigungsdialog von "Zurücksetzen" im Vorschläge-Tab
sprach nur von "offen oder manuell verworfen" - das ließ sich missverstehen,
als würden "zu prüfen" und "automatisch abgelehnt" nicht mitgelöscht.
Tatsächlich löscht die Funktion schon immer alle vier nicht-übernommenen
Status, der Text nennt sie jetzt einzeln. Keine Verhaltensänderung, nur
Text/Doku klargestellt und mit einem Test abgesichert, der ausdrücklich
alle vier Status abdeckt.

## 2.20.1

Fehlerbehebung: der JSON-Import (auch beim Übernehmen eines
KI-Deal-Finder-Vorschlags) kannte bisher kein `freibetrag_jahr` - ein
importierter Freibetrag landete deshalb ohne Jahresangabe in der Datenbank
und erschien in der Freibetrag-Übersicht in keiner der beiden Jahresspalten,
war also praktisch unsichtbar, bis man ihn einmal manuell auf der
Bearbeiten-Seite nachträgt. Der JSON-Import setzt jetzt - wie die
Bearbeiten-Seite schon immer - bei einem gesetzten Freibetrag ohne
Jahresangabe automatisch das laufende Jahr.

## 2.20.0

**Kunden-wirbt-Kunden-Recherche.** Beim Anlegen eines Deals (Formular,
JSON-Import oder aus dem KI-Deal-Finder übernommen) prüft die App
zusätzlich - nur mit konfiguriertem Anthropic-API-Key - per Websuche, ob die
Bank für diese Kontoart ein "Kunden wirbt Kunden"-Programm anbietet.

- Wird eines gefunden, legt die App automatisch eine **Aufgabe** unter "Zu
  erledigen" an sowie einen **Link** zur zugehörigen Seite der Bank in den
  Deal-Links.
- Bewusst **ohne Cache** (anders als die Kündigungsweg-Recherche):
  Empfehlungsprogramme sind oft befristete Marketing-Aktionen, die sich
  häufiger ändern als ein Kündigungsweg - ein veraltetes "gibt es nicht"
  wäre riskanter als der zusätzliche API-Aufruf pro neu angelegtem Deal.
- Schlägt die Recherche selbst fehl (z. B. kein auswertbares Ergebnis von
  der KI-Websuche), blockiert das die Deal-Anlage **nicht** - beim
  Übernehmen eines KI-Deal-Finder-Vorschlags erscheint dann ein Hinweis im
  Vorschläge-Tab, das Empfehlungsprogramm bei Interesse manuell zu prüfen.

## 2.19.0

**Strikterer Schutz vor Duplikaten und unnötigen API-Kosten.** Existiert für
eine Quelle-URL schon ein Vorschlag (für irgendeinen Inhaber, egal welcher
Status), gilt sie jetzt dauerhaft als geprüft: geringfügig schwankender
Rohtext derselben URL (z. B. Kommentar-/Bewertungszahlen im RSS-Feed) löst
keinen erneuten API-Aufruf mehr aus - selbst dann nicht, wenn sich das
Angebot dabei tatsächlich ändert (z. B. eine höhere Prämie oder andere
Bedingungen). Bewusste Entscheidung: zuverlässig keine Duplikate und keine
unnötigen API-Kosten mehr, zulasten davon, eine echte spätere Änderung am
selben Angebot nicht mehr automatisch mitzubekommen. **"Alle neu
analysieren"** überstimmt das weiterhin gezielt und erzwingt eine frische
Prüfung.

**Neuer Button "Zurücksetzen"** im Vorschläge-Tab: löscht unwiderruflich
alle noch nicht übernommenen Vorschläge (offen oder manuell verworfen)
sowie den Rohtext-Cache, damit "Jetzt suchen" wieder komplett frisch
beginnt - z. B. um nach einer Häufung von Duplikaten sauber neu zu starten.
Bereits übernommene Vorschläge (schon echte Deals) bleiben davon unberührt.

## 2.18.1

Fehlerbehebung: derselbe mydealz-/Spartanien-/DealDoktor-Link konnte über die
Zeit mehrfach als eigener Vorschlag auftauchen (sichtbar u.a. als mehrere
gleichlautende Quellen-Einträge mit identischem "Deal öffnen"-Link in einer
Duplikat-Karte). Ursache: schwankt der Rohtext derselben Quelle-URL
geringfügig (z.B. Kommentar-/Bewertungszahlen im RSS-Feed), löst das eine
erneute KI-Extraktion aus, die eine inhaltlich gleiche Bedingung nicht immer
wortgleich formuliert - das allein zählte bisher als "geänderter Fund" und
erzeugte fälschlich einen weiteren Datensatz. Die Dedup-Prüfung
berücksichtigt bei den Bedingungen jetzt nur noch Anzahl und Einschätzung
(erfüllt/zu prüfen/nicht erfüllt), nicht mehr den exakten Wortlaut - eine
wirklich geänderte Bedingung erzeugt weiterhin bewusst einen neuen Vorschlag.

Bereits entstandene doppelte Datensätze aus der Vergangenheit werden davon
nicht rückwirkend bereinigt - lassen sich aber über die Duplikat-Karte
(Version 2.16.0) einmalig per "Alle verwerfen" aufräumen.

## 2.18.0

**Täglicher Lauf abschaltbar.** Der automatische KI-Deal-Finder-Lauf um
06:00 Uhr lässt sich jetzt über die neue Add-on-Option
`taeglicher_lauf_aktiv` deaktivieren - z. B. um API-Kosten zu vermeiden, wenn
der Lauf ausschließlich manuell über "Jetzt suchen" angestoßen werden soll.

## 2.17.0

**Dritte Deal-Quelle: DealDoktor.** Der KI-Deal-Finder durchsucht jetzt
zusätzlich zu mydealz und Spartanien auch DealDoktor - über den offiziellen
WordPress-RSS-Feed (Standard: Rubrik „Bonus-Deals"), also den gleichen
stabilen Weg wie mydealz, ohne HTML-Scraping.

- **Neue Add-on-Option `dealdoktor_feed_url`** (Standard
  `https://www.dealdoktor.de/bonus-deals/feed/`) - hier lässt sich bei Bedarf
  ein anderer DealDoktor-Feed (z. B. eine andere Kategorie) hinterlegen.
- **Prämien-Quelle:** DealDoktor-Funde verlinken auf das Angebot der Bank -
  die Prämie wird deshalb (wie bei mydealz) standardmäßig der **Bank** als
  Geber zugeordnet, nicht dem Portal.
- Die Lauf-Statistik im Tab **Vorschläge** und der Quelle-Filter zeigen
  DealDoktor as eigene Spalte bzw. Auswahl.

## 2.16.0

**Quellenübergreifende Duplikat-Erkennung im KI-Deal-Finder.** Meldet eine
Bank+Kontoart-Kombination in mehreren unabhängigen Fundstellen (z. B. einmal
auf mydealz, einmal auf Spartanien), erscheint jetzt eine gemeinsame
Duplikat-Karte statt mehrerer einzelner Vorschlags-Karten - funktioniert für
beliebig viele beteiligte Quellen, nicht nur mydealz/Spartanien.

- Jede Fundstelle steht in der Karte mit eigener Prämienhöhe, Sperrfrist und
  Link zur Auswahl (Radio-Buttons) - die Prämie selbst ist bewusst kein
  Erkennungskriterium, da sie sich je Quelle unterscheiden kann.
- **"Ausgewählte übernehmen"** übernimmt die gewählte Version und verwirft
  die übrigen Fundstellen automatisch mit Grund "Duplikat" - kein separater
  Bestätigungsschritt nötig.
- **"Alle verwerfen"** lehnt die ganze Gruppe auf einmal ab, falls keine der
  gefundenen Versionen passt.
- Die Zähler-Chips ("vorgeschlagen", "zu prüfen", "abgelehnt") zählen eine
  Duplikat-Gruppe wie bisher schon bei mehreren Inhabern nur einmal, nicht je
  Fundstelle einzeln.

## 2.15.0

Notify-Konfiguration überarbeitet: mehrere Geräte statt nur eines möglich.

- **Add-on-Option umbenannt** von `notify_dienst` in `benachrichtigungsgeraete`
  (angezeigt als **"Benachrichtigungsgeräte"** in der Home-Assistant-
  Konfiguration, inkl. Erklärungstext, wie das Feld auszufüllen ist).
  ⚠️ Da sich der interne Schlüssel geändert hat, übernimmt Home Assistant
  einen zuvor unter `notify_dienst` gesetzten Wert **nicht** automatisch -
  bitte nach dem Update einmalig unter Einstellungen des Add-ons neu
  eintragen.
- **Mehrere Geräte gleichzeitig möglich:** Gerätenamen durch Komma getrennt
  in dasselbe Feld eintragen, z. B. `mobile_app_pixel_8,
  mobile_app_iphone_anna`. Jedes konfigurierte Gerät wird einzeln
  benachrichtigt; schlägt der Versand an eines fehl (z. B. Tippfehler),
  bekommen die übrigen Geräte die Benachrichtigung trotzdem.

## 2.14.0

**Neue Option `demo_modus`.** Zeigt die App mit frei erfundenen Testdaten
statt der echten - zum Vorführen, ohne echte Daten offenzulegen. Läuft auf
einer eigenen Datenbankdatei, die bei jedem Start frisch aus denselben
Testdaten neu aufgebaut wird; die echten Daten werden dabei nie berührt.
Ein Hinweisbalken oben in der App macht den Demo-Modus jederzeit sichtbar,
und der KI-Deal-Finder (Hintergrundlauf und manuelle Buttons) bleibt dabei
komplett deaktiviert, damit auch bei hinterlegtem API-Key keine echten
Anfragen ausgelöst werden.

## 2.13.0

Die vier Zähler-Chips oberhalb der Vorschläge-Liste ("vorgeschlagen",
"zu prüfen", "abgelehnt") sind jetzt klickbar und filtern direkt auf den
jeweiligen Status - die passende Sektion klappt dabei automatisch auf.

- **Neuer vierter Chip "Verworfen".** Bisher gab es keine Möglichkeit,
  gezielt nach manuell verworfenen Vorschlägen zu filtern - jetzt über den
  Chip oder die Status-Filterleiste (neue Option "Verworfen").
- Die Chips zeigen dabei immer die **Gesamtzahl** je Status (unter
  Berücksichtigung von Quelle/Typ), unabhängig vom gerade aktiven
  Status-Filter - vorher zeigten sie z. B. "0 vorgeschlagen", sobald nach
  einem anderen Status gefiltert wurde.

## 2.12.2

Fehlerbehebung: der Bestätigungsdialog von "Alle neu analysieren" blieb
sichtbar offen stehen, solange die Anfrage lief (kann je nach Anzahl der
Funde eine Weile dauern) - wirkte dadurch wie eingefroren. Der Dialog
schließt sich jetzt sofort bei Bestätigung, unabhängig davon, wie lange die
Anfrage im Hintergrund noch braucht.

## 2.12.1

Fehlerbehebung: ein Bank-Name mit leicht abweichender Schreibweise (z. B.
"SMARTBROKER" im Angebot vs. selbst als "Smart Broker" angelegt) ließ die
App fälschlich einen Neukunden-Deal statt einer bereits bestehenden
Kundenbeziehung erkennen. Der Abgleich ignoriert jetzt Groß-/
Kleinschreibung, Leerzeichen und Interpunktion - sowohl bei der
Sperrfrist-/Neukunden-Prüfung im KI-Deal-Finder als auch beim Übernehmen
eines Vorschlags (verhindert zusätzlich doppelte Bank-Datensätze für
dieselbe Bank).

Außerdem die Tabelle "Dieser Lauf je Quelle" überarbeitet: die
Abschnittsüberschrift entfällt, die vier Kategorien stehen wieder als
Zeilen mit mydealz/Spartanien/**Summe** als Spalten - passt jetzt ohne
horizontales Scrollen auf den Bildschirm.

## 2.12.0

Neuer Button **"Alle neu analysieren"** neben "Jetzt suchen" im
Vorschläge-Tab.

- Erzwingt für jeden aktuell gelisteten Fund einen frischen KI-Aufruf,
  auch wenn der Rohtext unverändert ist und normalerweise aus dem Cache
  bedient würde. Bestehende, noch offene Vorschläge werden dabei mit dem
  frischen Ergebnis überschrieben (z. B. um nachträglich eine
  Prämien-Aufschlüsselung zu bekommen, die es bei der ersten Prüfung noch
  nicht gab) - bereits übernommene oder verworfene Vorschläge bleiben
  unangetastet.
- Ein Klick öffnet zuerst einen Bestätigungsdialog, der auf die spürbar
  höheren API-Kosten hinweist; erst ein zweiter, expliziter Klick löst den
  Lauf aus.

## 2.11.0

Begründungspflicht beim manuellen Verwerfen eines Vorschlags. Enthält eine
Schema-Migration (neue Spalte `deal_vorschlaege.verwerfen_gruende`) - vorher
wird automatisch eine Sicherheitskopie angelegt.

- **Verwerfen öffnet jetzt einen Dialog** mit Mehrfachauswahl-Checkboxen für
  den Grund: **Duplikat**, **Bedingungen zu aufwendig**, **Noch nicht wieder
  Neukunde**. Ohne ausgewählten Grund lässt sich nicht verwerfen (client- und
  serverseitig abgesichert).
- **Manuell verworfene Vorschläge** erscheinen jetzt in einer eigenen,
  eingeklappten Sektion ganz unten im Vorschläge-Tab, mit den gewählten
  Gründen als Kennzeichnung - bisher waren sie komplett unsichtbar.

## 2.10.0

Weitere Überarbeitung der Vorschlags-Karten. Reine Anzeige-Änderung, keine
Migration.

- **Übernehmen als Dialog:** Ein Klick auf **Übernehmen** öffnet einen
  Dialog mit den Namen zum Auswählen und den zugehörigen Hinweisen je Person.
  In der Kachel selbst gibt es keine Checkboxen mehr.
- **Übernehmen-Button wird orange**, wenn es für einzelne Inhaber Hinweise
  gibt (abweichender Status oder Begründung), sonst grün.
- **Verwerfen** verwirft die ganze Karte (alle Namen), da die Einzelauswahl
  in den Übernehmen-Dialog gewandert ist.
- **Bedingungen sind immer sichtbar** (nicht mehr einklappbar).
- **Übernehmen / Verwerfen / Deal öffnen** stehen nebeneinander in einer Reihe.
- **Kontoart und "Auch für Kinder" wieder als Tags**.

## 2.9.0

Kompakteres, übersichtlicheres Design der Vorschlags-Karten mit mehr
Entscheidungs-Infos auf einen Blick. Reine Anzeige-Änderung, keine Migration.

- **Kompaktere Karten:** dichter Kopf (Bank + Kontoart als Untertitel +
  Prämie), Empfänger als umbrechende Zeile statt gestapelt, engere Abstände.
- **Mehr Infos sichtbar:** Fund-Datum und - falls vorhanden - Sperrfrist in
  einer Fakten-Zeile.
- **Bedingungen mit Ampel-Zusammenfassung:** eine Zeile zeigt Anzahl und
  Status ("alle erfüllbar" / "1 zu prüfen" / "nicht erfüllbar"); die volle
  Liste ist standardmäßig ausgeklappt und lässt sich einklappen.
- **"Deal öffnen" als Button** unten rechts, im Stil von Übernehmen/Verwerfen.
- **"Spartanien" wird durchgängig groß geschrieben** (Anzeige).

## 2.8.0

Übersichtlichere Vorschlags-Karten. Enthält eine Schema-Migration (neue
Tabelle `vorschlag_praemien`) - vorher wird automatisch eine Sicherheitskopie
angelegt.

- **Mehrere Teilprämien je Angebot werden einzeln ausgewiesen.** Setzt sich
  die Gesamtprämie aus mehreren Teilen mit unterschiedlichen Voraussetzungen
  zusammen (z. B. 50 EUR von Spartanien für die Kontoeröffnung plus 250 EUR
  von der Bank für den Kontowechselservice), zeigt die Karte jede Teilprämie
  mit Betrag, Geber und Bedingung. Beim Übernehmen entsteht daraus je
  Teilprämie ein Eintrag mit der richtigen Quelle (Spartanien/Bank). Bei nur
  einer Prämie bleibt die Karte schlicht wie bisher.
- **Einleitungstext im Vorschläge-Tab entfernt.**

Hinweis: Beides greift nur für **neu extrahierte** Angebote (neue Funde oder
solche mit geändertem Text). Bereits im Cache liegende Angebote behalten ihre
alte, einteilige Prämie, bis sich ihr Text ändert.

## 2.7.0

Vorschlags-Karten mit Direktlink und mehr Tags, sowie eine gezieltere
Behandlung von Angeboten für Minderjährige.

- **„Deal öffnen"-Link je Karte** (oben rechts) öffnet die zugehörige
  mydealz-/spartanien-Seite in einem neuen Browser-Tab.
- **Mehr Tags je Karte:** zusätzlich zur Quelle nun auch die Kontoart
  (z. B. Depot, Tagesgeld) und - falls zutreffend - „Auch für Kinder".
- **Kinder bekommen nur Kinderdeals vorgeschlagen.** Einem minderjährigem
  Inhaber wird ein Angebot nur noch dann vorgeschlagen, wenn es laut
  Angebotstext (auch) für Kinder abschließbar ist (z. B. Junior-Depot,
  Kinderkonto). Steht nichts dergleichen im Text, gilt der Deal als reines
  Erwachsenen-Angebot und das Kind erscheint gar nicht erst als Auswahl. Der
  frühere Filter/Tag „Kinderdepot" heißt jetzt „Für Kinder" bzw. „Auch für
  Kinder".

## 2.6.0

Die Statusanzeige im Vorschläge-Tab wurde überarbeitet, damit die Zahlen
nachvollziehbar zusammenpassen. Enthält eine Schema-Migration (acht neue
Zähler-Spalten auf `finder_laeufe`) - vorher wird automatisch eine
Sicherheitskopie angelegt.

- **Statuskarte ist jetzt einklappbar.** Standardmäßig steht nur noch
  „Letzter Lauf erfolgreich" mit Zeitpunkt; die Details erscheinen erst per
  Klick auf den Statustext.
- **Aufschlüsselung je Quelle als Tabelle.** Aufgeklappt zeigt eine kleine
  Tabelle je Quelle (mydealz, Spartanien), wie viele Funde neue Vorschläge,
  schon vorhanden, aktualisiert oder aussortiert (kein Bankdeal, doppelt,
  Fehler) waren. Jeder geladene Fund landet in genau einer Kategorie, die
  Summe je Quelle geht wieder auf die geladene Zahl auf - die frühere
  Verwirrung „oben 73, darunter 72" entfällt.
- **„Neue Vorschläge" zählt jetzt je Angebot, nicht je Inhaber.** Ein neuer
  Deal, der zu mehreren Inhabern passt, steht in der Liste als eine Karte
  und zählt entsprechend einmal - nicht mehr einmal pro Person.

## 2.5.1

Fehlerbehebung, die im echten Betrieb aufgefallen ist: mydealz-Läufe konnten
mit einem Datenbankfehler komplett abbrechen, sobald der Feed einen Deal
doppelt listete.

- **mydealz-RSS wird jetzt nach Link dedupliziert.** Listete der Feed
  denselben Deal zweimal (z. B. nach einem Bump), versuchte die App, zwei
  Cache-Einträge mit derselben (eindeutigen) Quelle-URL anzulegen - das
  brach den kompletten Lauf mit `UNIQUE constraint failed` ab, auch für
  alle anderen, unproblematischen Funde. Zusätzlich zur Behebung im
  RSS-Parser schützt eine zweite Sperre direkt im Lauf davor, dass ein
  doppelter Fund - unabhängig von der Ursache - je wieder den ganzen Lauf
  mitreißt.
- **Standard-URL für spartanien korrigiert** auf `https://www.spartanien.de/`
  (statt der nicht mehr existierenden Unterseite `/themen/bankprodukte/`) -
  betrifft nur Neuinstallationen ohne eigene Einstellung, wer die Option
  bereits manuell gesetzt hat, ist davon nicht betroffen.

## 2.5.0

Kündigungsweg-Recherche per KI, wenn die fest hinterlegte Tabelle keinen
Eintrag kennt. Enthält eine Schema-Migration (eine neue Tabelle, eine neue
Spalte auf `deals`) - vorher wird automatisch eine Sicherheitskopie angelegt.

- Findet die App beim Anlegen eines Deals keinen fest hinterlegten
  Kündigungsweg für Bank+Kontoart, recherchiert sie einmalig per
  Websuche (Claude, `web_search`-Tool) - nur mit konfiguriertem
  Anthropic-API-Key, sonst bleibt das Feld wie bisher leer.
- Das Ergebnis wird je Bank+Kontoart gecacht, um wiederholte API-Aufrufe zu
  vermeiden - dieselbe Idee wie beim KI-Deal-Finder-Cache.
- Ein KI-recherchierter Kündigungshinweis wird auf der Deal-Seite deutlich
  als **"KI-recherchiert, bitte prüfen"** markiert, da er - anders als die
  elf fest hinterlegten, von Hand geprüften Wege - ungeprüft ist. Die
  Markierung verschwindet, sobald der Hinweis von Hand bearbeitet wird.

## 2.4.0

Vorschläge-Tab: Filter, Dedup über Inhaber hinweg und Mehrfach-Übernehmen.
Keine Schema-Migration nötig.

- **spartanien-Parser an die echte Seitenstruktur angepasst.** Jede Karte
  ist ein `<article itemtype="http://schema.org/LocalBusiness">`
  (schema.org-Microdata) und verlinkt zusätzlich über einen unsichtbaren
  Anker ganz ohne Text - der bisherige Code nahm dessen leeren Titel und
  überspringt dadurch jede Karte. Titel, Link und Beschreibung werden jetzt
  gezielt aus `[itemprop="name"]`/`.description` gelesen, mit Rückfall auf
  die bisherigen generischen Selektoren, falls sich das Markup erneut
  ändert.
- **Filter nach Quelle, Typ und Status.** Die Liste lässt sich nach
  mydealz/spartanien, Erwachsene/Kinderdepot und Vorgeschlagen/Zu prüfen/
  Abgelehnt eingrenzen.
- **Ein Fund erscheint nur noch einmal**, auch wenn er für mehrere Inhaber
  infrage kommt - vorher gab es eine Karte je Person. Die Karte zeigt jetzt
  eine Checkbox je Name; ist der Fund für eine Person besser bewertet als
  für eine andere (z. B. echter Neukunde vs. bereits Kundin), zählt beim
  Einsortieren der bessere Fall, die abweichende Person zeigt ihren eigenen
  Status mit Begründung direkt daneben.
- **Übernehmen und Verwerfen wirken jetzt auf die ausgewählten Namen**, nicht
  mehr zwingend auf alle: ein Fund lässt sich für mehrere Personen auf einmal
  übernehmen (je ein Deal pro Auswahl), nicht ausgewählte bleiben offen
  stehen.

## 2.3.1

Fehlerbehebung, die im echten Betrieb aufgefallen ist: spartanien war beim
Live-Lauf nicht erreichbar, obwohl der Lauf als "erfolgreich" markiert
wurde - beides ist jetzt korrigiert.

- **spartanien-Abruf folgt jetzt Redirects.** `httpx` folgt
  Weiterleitungen standardmäßig nicht; die reale Seite leitet
  `/themen/bankprodukte/` auf `/themen` um, was bisher als Fehler
  ("spartanien nicht erreichbar") protokolliert wurde. Relative Links auf
  der Seite werden nach dem Redirect korrekt gegen die tatsächlich
  geladene Ziel-URL aufgelöst (nicht mehr gegen die ursprünglich
  konfigurierte). Betrifft auch den mydealz-Abruf, vorsorglich.
- **Status-Anzeige unterscheidet jetzt "erfolgreich" von "teilweise
  erfolgreich".** Bisher stand bei einem erfolgreichen Lauf mit einer
  fehlgeschlagenen Einzelquelle (z. B. nur spartanien nicht erreichbar,
  mydealz aber schon) trotzdem "✓ Letzter Lauf erfolgreich" direkt über der
  Fehlermeldung - das war widersprüchlich. Ein Lauf mit Fehlertext zeigt
  jetzt "⚠ Letzter Lauf teilweise erfolgreich"; komplett fehlgeschlagene
  Läufe (Rollback) weiterhin "✗ Letzter Lauf fehlgeschlagen".

## 2.3.0

Push-Benachrichtigung des KI-Deal-Finders ist jetzt konfigurierbar - keine
Schema-Migration nötig, nur zwei neue Add-on-Optionen.

- **`benachrichtigungen_aktiv`** (Standard: an) schaltet die Push-
  Benachrichtigung bei neuen Vorschlägen komplett ab, ohne den Lauf selbst
  oder den Vorschläge-Tab zu beeinflussen.
- **`notify_dienst`** (Standard: `notify`, also alle Geräte) adressiert
  gezielt ein einzelnes Smartphone statt aller Geräte/Personen - der Name
  ist der Home-Assistant-Dienst ohne `notify.`-Präfix, z. B.
  `mobile_app_pixel_8`.

## 2.2.0

Zwei Erweiterungen des KI-Deal-Finders (2.1.0): eine Status-Übersicht zum
letzten Lauf und eine deutliche Reduktion der Anthropic-API-Nutzung.
Enthält eine Schema-Migration (zwei neue Tabellen, eine neue Spalte) -
vorher wird automatisch eine Sicherheitskopie angelegt.

- **Status-Übersicht im Vorschläge-Tab.** Zeigt zum letzten Lauf: erfolgreich
  oder fehlgeschlagen, wie viele Funde je Quelle (mydealz/spartanien)
  geladen wurden, wie many davon neu sind, wie viele wegen Fehlern
  übersprungen wurden - inklusive Klartext-Fehlermeldung, falls welche
  auftraten (z. B. eine Quelle nicht erreichbar). `taeglicher_lauf()` wirft
  jetzt nie mehr nach außen: ein unerwarteter Fehler führt zu einem
  Rollback statt halb gespeicherter Vorschläge und wird als fehlgeschlagen
  protokolliert.
- **API-Nutzung deutlich reduziert.** Bevor ein Fund an Claude geschickt
  wird, prüft die App per Rohtext-Hash, ob dieselbe Quelle-URL mit
  demselben Text schon einmal geprüft wurde. Unveränderte Angebote lösen
  dann keinen erneuten API-Aufruf mehr aus; ein bereits als thematisch
  unpassend erkannter Fund wird dauerhaft übersprungen, ohne je wieder an
  die API zu gehen. Nur ein geänderter Rohtext (z. B. ein bearbeiteter
  Beitrag) löst eine erneute Prüfung aus. Die deterministische Bewertung
  (Mindestprämie, Sperrfrist, Bedingungen) läuft trotzdem bei jedem Lauf
  erneut, kostenlos und ohne API - eine inzwischen erreichte Sperrfrist
  wird dadurch weiterhin erkannt, auch wenn sich am Angebot selbst nichts
  geändert hat. Ein bereits vom Nutzer übernommener oder verworfener
  Vorschlag wird dabei nie überschrieben.
- Die Vorschläge-Übersicht zeigt zusätzlich, wie viele Funde je Lauf ganz
  ohne API-Aufruf erledigt wurden.

## 2.1.0

Erweiterung "KI-Deal-Finder" (eigenes Konzeptdokument, Ergänzung zum
Grundkonzept): ein täglicher Hintergrund-Lauf durchsucht mydealz und
spartanien nach neuen Neukunden-Prämien und schlägt echte Neuigkeiten im
neuen Tab **Vorschläge** vor. Enthält eine Schema-Migration (zwei neue
Tabellen) - vorher wird automatisch eine Sicherheitskopie angelegt.

- **Neuer Tab "Vorschläge".** Jeder gefundene, thematisch passende Fund wird
  angezeigt und nach Status gruppiert: vorgeschlagen (Kriterien eindeutig
  erfüllt), zu prüfen (unklar, z. B. keine erkennbare Sperrfrist) und
  automatisch abgelehnt (eingeklappt, mit Begründung, aber weiterhin
  sichtbar und trotzdem übernehmbar). Die KI *findet und extrahiert*, sie
  *entscheidet und speichert keine Fakten* - erst "Übernehmen" legt einen
  echten Deal an, über denselben Mechanismus wie der bestehende JSON-Import.
- **Mehrere Bedingungen pro Vorschlag**, nicht nur eine: Angebote bringen in
  der Regel mehrere unabhängig zu bewertende Bedingungen mit (Mindesteinlage,
  Gehaltseingang, Vertragslaufzeit, …) - analog zur bestehenden
  Bedingungen-Liste je Deal.
- **Push-Benachrichtigung** über die Home-Assistant-Core-API bei neuen
  vorgeschlagenen oder zu prüfenden Funden (nicht bei rein automatisch
  abgelehnten). Erfordert `homeassistant_api: true` im Add-on-Manifest
  (neu).
- **Neue Add-on-Optionen**: `anthropic_api_key`, `anthropic_model`,
  `mindestpraemie`, `mydealz_gruppe`, `spartanien_url` - alle optional, ohne
  API-Key bleibt der KI-Deal-Finder einfach inaktiv.
- Die Suche gilt für alle Inhaber, auch minderjährige.
- Ändert sich ein Angebot (z. B. eine höhere Prämie), entsteht ein neuer
  Vorschlag statt eines stillen Updates - die Historie bleibt
  nachvollziehbar. Ein inhaltlich unveränderter Fund wird nicht erneut
  vorgeschlagen.
- Ein Fund von mydealz wird beim Übernehmen als Prämien-Quelle "Bank"
  angelegt (das Kernmodell kennt nur "Spartanien" und "Bank"); die
  tatsächliche Herkunft bleibt über die mitgegebene URL nachvollziehbar.

## 2.0.0

Sammelkorrektur aus dem Fachlichkeits-Review (Teil 3 von 3): die fachliche
Logik. Enthält eine Schema-Migration - vorher wird automatisch eine
Sicherheitskopie angelegt.

- **Neue Kategorie "Zu prüfen" unter Zu erledigen.** Sammelt lose Fäden, die
  keine Stufe im Ablauf sind: Bedingungen oder Prämien, die nach der
  Kündigung noch offen stehen; Deals ohne erfasste Prämie; gekündigte Deals
  ohne auswertbaren Kündigungsmonat. Abgehakte Hinweise verschwinden, kommen
  aber zurück, wenn sich die Fakten dahinter ändern - etwa wenn eine weitere
  unbezahlte Prämie hinzukommt. Ein neu angelegter Deal wird 72 Stunden
  geschont, damit er nicht sofort wegen fehlender Prämien auftaucht.
- **Ein gekündigter und bestätigter Deal gilt als abgeschlossen.** Bisher
  hielt eine einzige nie abgehakte Bedingung ihn in "Bedingungen" - er stand
  gleichzeitig in der ToDo-Liste und in den Sperrfristen. Die offene
  Bedingung wird dabei *nicht* stillschweigend abgehakt, sie erscheint unter
  "Zu prüfen".
- **Überfällige Prämien werden markiert.** Bisher war "erwartete Auszahlung"
  nur eine Notiz. Jetzt fällt auf, wenn eine Prämie nicht gekommen ist: einen
  Monat nach dem erwarteten Monat, oder - wenn kein Monat hinterlegt ist -
  zwei Monate nach der zuletzt erfüllten Bedingung.
- **Stornieren nutzt ein eigenes Feld.** Bisher wurde ein stornierter Deal als
  "gekündigt" markiert und tauchte dadurch dauerhaft in den Sperrfristen auf,
  obwohl er nie zustande gekommen ist. Prämien werden weiterhin auf 0 gesetzt
  und Bedingungen abgehakt - ein stornierter Deal ist erledigt.
- **Freibetrag mit Jahresangabe.** Der Sparer-Pauschbetrag gilt pro
  Kalenderjahr; eine jahresübergreifende Summe beantwortete keine sinnvolle
  Frage. Die Übersicht zeigt jetzt laufendes Jahr und Vorjahr getrennt.
  Bestehende Freibeträge werden dem Jahr 2026 zugerechnet - die
  Vorjahresspalte ist deshalb zunächst leer.
- **Abhaken ist wiederholungssicher.** Die Häkchen in "Zu erledigen"
  schalteten den Wert bisher um, statt ihn zu setzen. Eine doppelt
  ankommende Anfrage machte damit die Aktion wieder zunichte. Besonders
  unangenehm beim Kündigen: ein gepflegter Kündigungsmonat wurde durch den
  heutigen ersetzt und verfälschte die Sperrfristen. Ein bereits gesetzter
  Monat bleibt jetzt stehen; beim Zurücknehmen wird er geleert.
- **Zugangsdaten-Hinweis endet mit der Kündigung.** Für ein gekündigtes Konto
  ist er gegenstandslos, blieb aber dauerhaft in der Liste stehen.
- **Hinweis auf denselben Deal.** Legt man eine Kombination aus Bank,
  Kontoart und Inhaber erneut an, weist die App auf den früheren Deal hin -
  mit Unterscheidung, ob dessen Sperrfrist schon abgelaufen ist. Bewusst nur
  ein Hinweis: nach Ablauf der Sperrfrist ist die zweite Runde der Normalfall.
- **Kündigungs-Anweisungen kommen beim Anlegen.** Bisher wurden sie erst beim
  nächsten Neustart des Add-ons eingesetzt - also gerade dann nicht, wenn man
  sie braucht. Und ein bewusst geleertes Feld füllte sich beim Start wieder
  von selbst. Jetzt wird der Vorschlag einmalig beim Anlegen gesetzt, danach
  bleibt das Feld unangetastet.
- Der Sperrfristen-Tab führt keine zweite Liste mehr für Deals ohne
  Kündigungsmonat; die stehen jetzt unter "Zu prüfen".

## 1.9.0

Sammelkorrektur aus dem Fachlichkeits-Review (Teil 2 von 3): Datenqualität
und Zeitangaben. Enthält eine Datenmigration - vorher wird automatisch eine
Sicherheitskopie angelegt.

- **Prämien-Quelle wird geprüft.** Bisher wurde jeder Wert gespeichert, auch
  "Bank" oder "Spartanien" mit großem Anfangsbuchstaben. Das Auswahlfeld im
  Formular kennt solche Werte nicht - beim nächsten Speichern wurde daraus
  stillschweigend "Spartanien", eine Bank-Prämie wechselte also unbemerkt die
  Quelle. Schreibweise und Leerzeichen werden jetzt verziehen, unbekannte
  Quellen abgelehnt. Vorhandene Einträge werden einmalig bereinigt.
- **Ein Monatsformat für beides.** "Gekündigt im Monat" verwendet jetzt
  dasselbe Format wie "Erwartete Auszahlung": `JJJJ-MM`, also z. B. `2026-07`.
  Bestehende Werte werden automatisch umgestellt. Beide Felder werden beim
  Speichern geprüft, statt eine falsch formatierte Eingabe später als
  "fehlt" zu behandeln. Alte Angaben im Format `MM.JJ` bleiben lesbar.
- **Uhrzeiten in Ortszeit.** Zeitstempel im Protokoll und im Excel-Export
  wurden in UTC angezeigt, im Sommer also zwei Stunden zu früh. Gespeichert
  bleibt UTC (eindeutig und ohne Migration), angezeigt wird Ortszeit. Beim
  Start steht die erkannte Zeitzone im Add-on-Protokoll.
- **"Kündbar ab" wird nicht mehr als fehlend angemahnt.** Ein leeres Feld
  bedeutet "keine Sperrfrist" und ist damit eine Angabe, keine Lücke. Der
  Anteil gepflegter Deals in der Vollständigkeit steigt dadurch.
- **Sicherheitskopie nur noch vor echten Migrationen.** Bisher wurde bei
  jedem Start kopiert, immer über dieselbe Datei. Ein einziger Neustart nach
  einem versehentlichen Löschen genügte, und die Kopie enthielt den kaputten
  Stand. Jetzt wird nur kopiert, wenn wirklich eine Migration ansteht, und
  der Dateiname nennt die Ziel-Version (`praemien.db.vor-0005.bak`).

## 1.8.0

Sammelkorrektur aus dem Fachlichkeits-Review (Teil 1 von 3): ausschließlich
Anzeige- und Robustheitsfehler, das fachliche Verhalten bleibt unverändert.
Keine Datenbank-Migration nötig.

- Fix: Der erste Balken der Pipeline ("Bedingungen") blieb ungefärbt - die
  CSS-Klasse hieß anders als der Status.
- Fix: Der Fortschrittsbalken in der Deal-Liste hatte nur fünf Segmente bei
  sechs Status; abgeschlossene Deals zeigten deshalb keine aktuelle Position.
- Fix: Das "+" in der Vollständigkeit sprang bei "Erwartete Auszahlung" ins
  Leere, weil das Eingabefeld keine ID trug.
- Fix: Die Vollständigkeit zeigte die Prämien-Quelle klein ("spartanien")
  statt wie überall sonst großgeschrieben.
- Fix: Ein Filter mit unsinnigem Wert (z. B. `?inhaber_id=abc`) führte zu
  einem Serverfehler statt ihn zu übergehen. Gleiches gilt jetzt für die
  Seitenangabe im Protokoll.
- Fix: Eine unbekannte Deal-ID (alter Link, zweiter Tab) zeigt eine
  Fehlerseite mit Hinweis statt eines Serverfehlers.
- Fix: Eine Eingabe aus reinen Leerzeichen legte einen Deal mit leerer Bank
  an - das Formular meldet nun, welches Feld fehlt.
- Fix: Doppelt vergebene HTML-ID im Deal-Formular entfernt.
- Fix: Die Navigation markierte hinter Ingress keinen Reiter; Unterseiten wie
  ein geöffneter Deal gehören jetzt sichtbar zum Reiter "Deals".
- JSON-Anlage: Es lässt sich jetzt auch eine **Liste** mehrerer Deals in
  einem Durchgang einfügen. Fehler werden als lesbare Liste in Deutsch
  gemeldet ("Deal 2: kontoart fehlt") statt als technischer Rohtext.
- JSON-Anlage ist ein echter Auf-/Zuschalter statt zweier Schaltflächen, die
  nur wie einer aussahen.
- Import: Randleerzeichen werden entfernt - bisher entstanden über den
  Import Kontoarten wie " Depot", die der Formularweg so nicht erzeugt hat.
- Import: Die "nicht nötig"-Häkchen aus der Vollständigkeit lassen sich
  mitgeben (`uebersprungene_felder`).
- Protokoll: Seitenweise Anzeige (200 Einträge je Seite) statt einer einzigen
  sehr langen Tabelle; ältere Einträge sind jetzt überhaupt erreichbar.
- Datenbank: Fremdschlüssel werden jetzt durchgesetzt, damit keine Prämien
  oder Bedingungen ohne zugehörigen Deal entstehen können.
- Tabellenzeilen sind per Tastatur erreichbar, Listen-Markup korrigiert.
- Intern: erste Testabdeckung für die abgeleiteten Sichten (34 Tests),
  veraltete FastAPI-Startschnittstelle ersetzt.
## 1.7.3

- Caching: zusätzlich zu Cache-Control werden jetzt auch die Legacy-Header
  Pragma und Expires gesetzt (für alle Seiten und statischen Dateien).
  Ältere Android-Webviews werten Cache-Control teilweise nicht aus und
  zeigten nach einem Update weiterhin die alte Oberfläche.

## 1.7.2

- Deals-Filter: Checkboxen im Inhaber-/Status-Dropdown im App-Design
  (abgerundet, mit Häkchen) statt native OS-Checkbox - konsistent zum
  restlichen Look, unabhängig vom Browser.

## 1.7.1

- Deals-Filter: das native Mehrfachauswahl-Feld (große, unformatierte
  Liste) durch ein kompaktes Dropdown mit Checkboxen ersetzt - passt
  wieder zum Design der App.

## 1.7.0

- Fix: Filtern im Deals-Tab führte zu einem Fehler, wenn "Alle Inhaber"
  ausgewählt war (leerer Wert konnte nicht als Zahl geparst werden).
- Deals-Filter: Inhaber und Status lassen sich jetzt per Mehrfachauswahl
  (Strg/Cmd-Klick) filtern statt nur einzeln. Neuer "Zurücksetzen"-Link,
  wenn ein Filter aktiv ist.

## 1.6.4

- Protokoll: Button "Protokoll leeren" (samt Route) wieder entfernt.

## 1.6.3

- Protokoll: neuer Button "Protokoll leeren", um alle bisherigen Einträge
  unwiderruflich zu löschen.

## 1.6.2

- Protokoll: neue Spalten Person, Bank und Kontoart pro Eintrag (auch nach
  dem Löschen eines Deals noch lesbar, da zum Zeitpunkt des Eintrags
  gespeichert statt live nachgeschlagen).
- Protokoll: neue Spalte "JSON" mit dem kompletten Stand der jeweiligen
  Zeile zu diesem Zeitpunkt - zusätzlich zu den Vorher-/Nachher-Werten je
  Feld, auch bei "geändert"-Einträgen (vorher nur bei neu/gelöscht).

## 1.6.1

- "Zu erledigen": Prämien-Quelle wird jetzt großgeschrieben angezeigt
  ("Spartanien" / "Bank" statt "spartanien" / "bank").

## 1.6.0

- Neuer Tab "Protokoll": erfasst automatisch jede Änderung an Deals,
  Prämien, Bedingungen, Aufgaben, Links, Banken und Inhabern - mit
  Vorher-/Nachher-Wert je Feld und Zeitstempel. Bei neu angelegten oder
  gelöschten Deals wird zusätzlich das komplette JSON protokolliert.
  Läuft vollautomatisch über die Datenbank-Ebene, keine Route muss dafür
  extra angepasst werden.

## 1.5.2

- Fix: Alle Seiten werden jetzt mit "Cache-Control: no-store" ausgeliefert,
  damit insbesondere die Home-Assistant-Companion-App die Seiten nicht
  mehr als Ganzes zwischenspeichert. Vorher blieb nach einem Add-on-Update
  dort teilweise noch die alte, unformatierte Seite sichtbar, obwohl der
  Server schon die neue Version auslieferte.

## 1.5.1

- Fix: CSS-Datei wird jetzt mit einer Versions-Kennung geladen, damit der
  Browser nach einem Update nicht mehr eine veraltete, gecachte Version
  anzeigt (das ließ z.B. den Sperrfristen-Tab unformatiert aussehen).
- "Pro Inhaber" in der Übersicht is jetzt eine echte Tabelle mit den
  Spalten Person, Erhalten, Offen und Freibetrag.

## 1.5.0

- Neuer Tab "Sperrfristen": zeigt für alle gekündigten Deals die Monate
  seit Kündigung je Bank, Kontoart und Inhaber - rot bei unter 6 Monaten,
  orange bis 12 Monaten, grün darüber. Älteste Kündigung steht oben.
- Übersicht zeigt jetzt pro Inhaber zusätzlich den genutzten Freibetrag.

## 1.4.0

- ToDos lassen sich jetzt direkt in "Zu erledigen" abhaken (Bedingung
  erfüllt, Prämie erhalten, gekündigt, Kündigung bestätigt, Zugangsdaten
  gesichert, Aufgabe erledigt) - kein Umweg mehr über die Deal-Seite nötig.
- Bedingungen und Prämien werden pro Deal zu einer Zeile zusammengefasst;
  bei mehreren offenen Posten öffnet ein Klick einen Dialog zum einzelnen
  Abhaken.
- Beim Abhaken von "Kündigen" wird automatisch der aktuelle Monat als
  Kündigungsdatum gesetzt.

## 1.3.0

- Neuer Pipeline-Status "Auf Kündigung warten": greift, wenn alles erledigt
  ist, aber "Kündbar ab" noch in der Zukunft liegt.
- Deals lassen sich jetzt stornieren (auf Abgeschlossen setzen) - offene
  Bedingungen gelten dann als erfüllt, noch nicht erhaltene Prämien werden
  auf 0 gesetzt.
- "Zu erledigen" zeigt die ToDo-Kategorien jetzt als Tabs statt
  untereinander.

## 1.2.0

- Automatischer Vorschlag für "Kündigung Anweisungen" bei jedem Start:
  recherchierte Kündigungswege für 10 Banken/Kontoarten (Bfor, Ferratum,
  Quirion, Traders Place, BBBank, DB Max blue, Comdirect, 1822direkt,
  C24 Bank, S Broker) werden auf noch nicht gekündigte Deals ohne eigene
  Anweisung angewendet - bereits gesetzte oder vom Nutzer bearbeitete
  Werte werden nie überschrieben (`kuendigung_hinweise.py`).

## 1.1.1

- Fix: `/deals/{id}/kuendigung-hinweis` akzeptiert jetzt auch JSON-Bodies
  (zusätzlich zu normalen Formulardaten).

## 1.1.0

- Neues Feld "Kündigung Anweisungen" je Deal (Freitext + optionaler Link,
  z. B. zu einem PDF-Kündigungsformular).
- Excel-Export aller Deals (Deals → Export) with Sheets für Deals, Prämien,
  Bedingungen, Aufgaben und Links.

## 1.0.2

- Redesign gemäß GUI-Mockups: Design-System (Farben, Space Grotesk / Inter /
  IBM Plex Mono), Hero-Kennzahlenkarte, segmentierte Pipeline, Status-Chips,
  Toggle-Switches, Vollständigkeits-Chips, Desktop-Tabellenansicht.

## 1.0.1

- Add-on-Konfigurationsordner (`addon_config`) statt `/data` für
  `seed-data.json` - macht den Ordner per Samba/Datei-Explorer sichtbar.

## 1.0.0

- Erste Version: Übersicht, Deal-Verwaltung (Formular & JSON-Import),
  abgeleitete ToDo-Liste, Vollständigkeits-Übersicht, Alembic-Migrationen.
