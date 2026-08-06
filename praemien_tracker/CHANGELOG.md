# Changelog

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
  geladen wurden, wie viele davon neu sind, wie viele wegen Fehlern
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
- "Pro Inhaber" in der Übersicht ist jetzt eine echte Tabelle mit den
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
- Excel-Export aller Deals (Deals → Export) mit Sheets für Deals, Prämien,
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
