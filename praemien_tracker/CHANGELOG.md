# Changelog

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
