# Changelog

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
  DealDoktor als eigene Spalte bzw. Auswahl.

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
- **Kinder bekommen nur Kinderdeals vorgeschlagen.** Einem minderjährigen
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
