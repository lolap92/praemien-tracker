# Prämien-Tracker

Private Web-App zur Verwaltung von Bank-Prämien-Deals. Läuft ausschließlich
im Heimnetz und wird über die Home-Assistant-Ingress-Funktion aufgerufen -
es ist keine zusätzliche Portfreigabe oder Anmeldung nötig.

## Grundprinzip

Du erfasst nur Fakten (Bank, Kontoart, Inhaber, Prämien, Bedingungen,
Kündigungsdaten). Status, Kennzahlen und die ToDo-Liste berechnet die App
automatisch daraus - sie werden nirgends redundant gepflegt.

## Zu erledigen

Die Liste ist nach Kategorien getrennt. Ganz rechts steht **Zu prüfen** -
das sind keine Aufgaben, sondern Auffälligkeiten zum Nachsehen: Bedingungen
oder Prämien, die nach der Kündigung noch offen stehen, Deals ohne erfasste
Prämie, gekündigte Deals ohne Kündigungsmonat. Hakst du einen Hinweis ab,
verschwindet er - er kommt aber zurück, wenn sich die Fakten dahinter
ändern, etwa wenn eine weitere unbezahlte Prämie hinzukommt.

Eine Prämie gilt als **überfällig**, wenn sie einen Monat nach dem
erwarteten Auszahlungsmonat noch nicht da ist. Ist kein Monat hinterlegt,
zählen zwei Monate ab der zuletzt erfüllten Bedingung.

## Stornieren

Ein Deal, der nicht zustande gekommen ist, wird über **Stornieren**
abgeschlossen: offene Prämien werden auf 0 gesetzt, Bedingungen abgehakt.
Ein stornierter Deal zählt *nicht* als gekündigt und erscheint deshalb auch
nicht in den Sperrfristen - dort geht es darum, wann eine Bank wieder
Neukunden-Ziel ist.

## Freibetrag

Der Freibetrag wird einem Kalenderjahr zugeordnet, weil der
Sparer-Pauschbetrag pro Jahr gilt. Die Übersicht zeigt laufendes Jahr und
Vorjahr getrennt. Beim Umstieg auf Version 2.0.0 werden alle vorhandenen
Freibeträge dem Jahr 2026 zugerechnet; die Vorjahresspalte ist deshalb
zunächst leer.

## KI-Deal-Finder (Vorschläge)

Ein täglicher Hintergrund-Lauf (06:00 Uhr) durchsucht mydealz (Gruppe
"Verträge & Finanzen") und Spartanien nach neuen Neukunden-Prämien und
schlägt echte Neuigkeiten im Tab **Vorschläge** vor. Die KI *findet und
extrahiert*, sie *entscheidet und speichert keine Fakten* - ein Vorschlag
ist erst nach "Übernehmen" ein echter Deal. Voraussetzung ist ein eigener
Anthropic-API-Key (siehe Konfiguration unten); ohne Key läuft die App wie
gewohnt weiter, nur ohne Vorschläge.

Jeder thematisch passende Fund wird angezeigt - auch automatisch abgelehnte,
mit Begründung, zusammengeklappt am Seitenende. Bei Unsicherheit (z. B.
unklare Sperrfrist) landet ein Fund unter "Zu prüfen" statt automatisch
ausgeschlossen zu werden. Über den Button **Jetzt suchen** lässt sich ein
Lauf jederzeit manuell anstoßen, z. B. um die Einrichtung zu testen.

Der Button **Alle neu analysieren** daneben erzwingt für jeden aktuell
gelisteten Fund eine frische KI-Prüfung, auch wenn sich am Text nichts
geändert hat und er sonst aus dem Cache bedient würde - z. B. um bestehende
Karten mit später eingeführten Feldern nachträglich aufzufrischen. Das kostet
spürbar mehr API-Aufrufe als ein normaler Lauf, deshalb erst nach
Bestätigung in einem Dialog. Bereits übernommene oder verworfene Vorschläge
bleiben dabei unangetastet.

Ändert sich ein Angebot (z. B. eine höhere Prämie), entsteht bewusst ein
neuer Vorschlag statt eines stillen Updates am alten - die Historie bleibt
so nachvollziehbar. Ein unveränderter Fund wird dagegen nicht erneut
vorgeschlagen, auch nicht nach dem Verwerfen.

Die Suche gilt für **alle** Inhaber. Einem **minderjährigen** Inhaber wird ein
Angebot allerdings nur dann vorgeschlagen, wenn es laut Angebotstext (auch)
für Kinder abschließbar ist (z. B. Junior-Depot, Kinderkonto). Die meisten
Neukunden-Prämien setzen Volljährigkeit voraus; steht nichts dergleichen im
Text, gilt der Deal als reines Erwachsenen-Angebot und das Kind erscheint gar
nicht erst als Auswahl. Karten mit einem passenden Kind sind mit **"Auch für
Kinder"** gekennzeichnet.

Ob ein Angebot ein echter Neukunden-Deal ist, prüft die App über den
Bank-Namen im Angebotstext gegen die selbst erfassten Banken - Groß-/
Kleinschreibung, Leerzeichen und Interpunktion spielen dabei keine Rolle
("SMARTBROKER" erkennt z. B. eine selbst als "Smart Broker" angelegte Bank).
Findet sich keine passende Bank, gilt der Fund automatisch als Neukunden-Deal.

**Ein Fund erscheint nur einmal.** Passt ein Angebot zu mehreren Inhabern
(z. B. ein Erwachsener und ein Kind bei einem Junior-Depot), steht es als eine
Karte da statt einer eigenen Karte pro Person. Ist der Fund für eine Person
ein echter Neukunden-Deal, für eine andere aber z. B. schon Bestandskunde,
zählt beim Einsortieren der bessere Fall - die Karte landet unter
"Vorgeschlagen", die betroffene Person zeigt im Übernehmen-Dialog daneben
ihren abweichenden Status mit Begründung. Ein Klick auf **Übernehmen** öffnet
einen Dialog zur Auswahl der Namen - für jede ausgewählte Person entsteht ein
eigener Deal, nicht ausgewählte bleiben unverändert offen stehen.

**Gleicher Deal aus mehreren Quellen wird gebündelt.** Findet die App
dieselbe Bank+Kontoart in mehreren unabhängigen Fundstellen (z. B. einmal auf
mydealz, einmal auf Spartanien - unabhängig von der Anzahl beteiligter
Quellen), erscheint eine gemeinsame Duplikat-Karte statt mehrerer einzelner.
Jede Fundstelle steht darin mit eigener Prämienhöhe, Sperrfrist und Link zur
Auswahl - die Prämie selbst fließt bewusst nicht ins Erkennungskriterium ein,
da sie sich je Quelle unterscheiden kann. Nach Auswahl einer Version über
**"Ausgewählte übernehmen"** werden die übrigen Fundstellen automatisch mit
Grund "Duplikat" verworfen; **"Alle verwerfen"** lehnt die ganze Gruppe ab,
falls keine Version passt.

Ein Klick auf **Verwerfen** öffnet ebenfalls einen Dialog: Hier wird - mit
Mehrfachauswahl möglich - der Grund festgehalten (Duplikat, Bedingungen zu
aufwendig, noch nicht wieder Neukunde). Ohne ausgewählten Grund lässt sich
nicht verwerfen. Verworfene Funde erscheinen ganz unten in einer eigenen,
eingeklappten Sektion, mit den gewählten Gründen als Kennzeichnung - und
tauchen dank Dedup nicht erneut auf, solange sich am Fund nichts ändert.

Über die Filterleiste lässt sich die Liste nach **Quelle** (mydealz/
Spartanien), **Typ** (Erwachsene/Für Kinder) und **Status** eingrenzen -
auch nach **Verworfen**, um manuell verworfene Funde gezielt wiederzufinden.
Schneller geht's über die vier farbigen Zähler-Chips oberhalb der Liste
("vorgeschlagen", "zu prüfen", "abgelehnt", "verworfen") - ein Klick filtert
direkt auf den jeweiligen Status und klappt die passende Sektion automatisch
auf. Die Chips zeigen dabei immer die Gesamtzahl (unter Berücksichtigung von
Quelle/Typ), unabhängig davon, welcher Status gerade aktiv gefiltert ist.

Jede Karte hat oben rechts einen **"Deal öffnen"**-Link, der die zugehörige
mydealz-/Spartanien-Seite in einem neuen Tab öffnet, sowie Tags für Quelle,
Kontoart (z. B. Depot, Tagesgeld) und - falls zutreffend - "Auch für Kinder".
Setzt sich die Prämie aus mehreren Teilen mit unterschiedlichen
Voraussetzungen zusammen (z. B. 50 EUR von Spartanien für die Kontoeröffnung
plus 250 EUR von der Bank für den Kontowechselservice), werden diese
Teilprämien mit Betrag, Geber und Bedingung einzeln aufgeführt.

**API-Nutzung wird minimiert:** Bevor ein Fund an Claude geschickt wird,
prüft die App anhand eines Rohtext-Abgleichs, ob dieselbe Quelle-URL mit
demselben Text schon einmal geprüft wurde. Ein unverändertes Angebot löst
dann keinen erneuten API-Aufruf mehr aus - ein bereits als thematisch
unpassend erkannter Fund (z. B. keine Bank-Prämie) wird dauerhaft
übersprungen, ein bereits extrahiertes Angebot wird aus dem Cache
wiederverwendet. Nur wenn sich der Rohtext ändert (z. B. ein bearbeiteter
Beitrag), wird erneut geprüft.

Die einklappbare Statuskarte oben im Vorschläge-Tab (Klick auf „Letzter Lauf
…") zeigt je Quelle, was der letzte Lauf gefunden hat: wie viele Funde neue
Vorschläge waren, schon vorhanden, aktualisiert oder aussortiert (kein
Bankdeal, doppelt gelistet oder Fehler). Jeder geladene Fund landet in genau
einer dieser vier Kategorien.

## Kündigungsweg-Recherche

Beim Anlegen eines Deals schlägt die App automatisch einen Kündigungsweg vor,
sofern für Bank und Kontoart einer bekannt ist. Für elf Banken ist der Weg
fest hinterlegt und geprüft. Kennt die App keinen Eintrag, recherchiert sie
- nur mit konfiguriertem Anthropic-API-Key - einmalig per Websuche und
markiert das Ergebnis deutlich als **"KI-recherchiert, bitte prüfen"** auf
der Deal-Seite, da es anders als die fest hinterlegten Wege ungeprüft ist.
Dieselbe Bank+Kontoart-Kombination wird danach aus einem Cache wiederverwendet,
ohne erneuten API-Aufruf. Ohne API-Key oder ohne verlässlichen Treffer bleibt
das Feld wie bisher leer - der Nutzer trägt es dann selbst ein. Sobald das
Feld von Hand bearbeitet wird, verschwindet die Markierung, denn ab dann
gehört der Text dem Nutzer.

## Erste Schritte

1. Add-on starten.
2. Über die Seitenleiste öffnen (Ingress).
3. Unter "Neuer Deal" den ersten Deal anlegen - entweder per Formular oder
   per JSON-Einfügen.

## Startdaten einspielen (optional, einmalig)

Wer bereits bereinigte Daten besitzt (z. B. aus einer Excel-Migration),
legt einmalig eine `seed-data.json` in den Add-on-Konfigurationsordner
(erreichbar z. B. über die Samba-Freigabe oder ein SSH/Terminal-Add-on).
Der Ordnername folgt dem Muster `<hash>_praemien_tracker` (der Hash steht
für das Repository) und erscheint unter `addon_configs`, sobald das Add-on
einmal gestartet wurde:

```
/addon_configs/<hash>_praemien_tracker/seed-data.json
```

Die Datei muss **vor dem ersten Start** des Add-ons dort liegen. Existiert
beim Start noch keine `praemien.db`, baut die App das Schema an und legt
alle in der `seed-data.json` beschriebenen Deals inklusive Prämien,
Bedingungen, Aufgaben und Links an. Bei jedem weiteren Start ist die
Datenbank bereits vorhanden, der Seed-Import läuft dann nicht erneut.

Die Datei enthält private Daten und darf nie ins öffentliche Repo gelangen
- sie verbleibt ausschließlich lokal auf dem Green.

## Daten & Sicherheit

- Alle Daten liegen ausschließlich lokal in `/data/praemien.db`.
- Vor jeder Schema-Migration wird automatisch eine Kopie angelegt, benannt
  nach der Ziel-Version (z. B. `praemien.db.vor-0005.bak`). Steht keine
  Migration an, wird nichts kopiert - die Kopie bleibt so der Stand vor
  der Änderung.
- Die Datei liegt im persistenten Add-on-Verzeichnis und wird damit von den
  regulären Home-Assistant-Backups mit erfasst.
- Es werden bewusst keine Zugangsdaten (Login/Passwort/TAN) gespeichert -
  nur ein Flag, ob diese im Passwortmanager gesichert sind.

## Zeitangaben

Zeitstempel (z. B. im Protokoll) werden intern in UTC gespeichert und in
der Oberfläche in Ortszeit angezeigt. Das setzt voraus, dass der Container
die Zeitzone kennt - siehe `Zeitzone prüfen` unten.

Monatsangaben (Kündigungsmonat, erwartete Auszahlung) verwenden
durchgängig das Format `JJJJ-MM`, z. B. `2026-07`.

### Zeitzone prüfen

Im Add-on-Protokoll steht beim Start eine Zeile mit der erkannten
Zeitzone. Weicht die angezeigte Uhrzeit im Tab "Protokoll" von der
tatsächlichen ab, ist im Container keine Zeitzone gesetzt - dann hilft ein
`TZ`-Eintrag in der Add-on-Konfiguration. Die gespeicherten Daten sind
davon nicht betroffen, es handelt sich nur um die Anzeige.

## Demo-Modus

Für Vorführzwecke lässt sich die App über die Option `demo_modus` komplett
auf frei erfundene Testdaten umschalten - ein zweiter Personenkreis (Max
und Erika Mustermann), fiktive Banken und ein paar Deals/ToDos/Vorschläge
über alle Status hinweg, damit sich jede Ansicht sinnvoll zeigen lässt.

Das läuft auf einer eigenen Datenbankdatei (`demo.db` statt `praemien.db`)
- die echten Daten werden dabei nie gelesen oder geschrieben, unabhängig
davon, was im Demo-Modus passiert. Bei jedem Start wird die Demo-Datenbank
zusätzlich verworfen und frisch aus denselben Testdaten neu aufgebaut, ein
Neustart genügt also, um wieder bei einem sauberen Ausgangszustand zu
landen. Ein gut sichtbarer Hinweisbalken oben in der App macht zusätzlich
unmissverständlich klar, dass gerade Testdaten angezeigt werden.

Der KI-Deal-Finder läuft im Demo-Modus nicht im Hintergrund und lässt sich
auch nicht manuell anstoßen (Buttons dafür sind ausgeblendet) - selbst mit
hinterlegtem API-Key werden im Demo-Modus keine echten, kostenpflichtigen
Anfragen an Anthropic oder die Fund-Quellen ausgelöst.

Zum Zurückschalten auf die echten Daten die Option wieder auf `false`
setzen und das Add-on neu starten.

## Konfiguration

Ohne jede Einstellung ist das Add-on sofort einsatzbereit - der
KI-Deal-Finder bleibt dann einfach inaktiv. Für den KI-Deal-Finder gibt es
folgende optionale Einstellungen (Add-on-Konfiguration in Home Assistant):

| Option | Zweck | Default |
|---|---|---|
| `demo_modus` | Zeigt ausschließlich erfundene Testdaten zum Vorführen (siehe oben), rührt nie an den echten Daten. | `false` |
| `anthropic_api_key` | Eigener API-Key von [console.anthropic.com](https://console.anthropic.com) - **kein** claude.ai-Abo (Free/Pro/Max reichen nicht, das ist ein getrenntes Produkt). Ohne Key läuft die App normal weiter, nur ohne Vorschläge. | leer |
| `anthropic_model` | Welches Claude-Modell für die Extraktion genutzt wird. | `claude-haiku-4-5` |
| `mindestpraemie` | Prämien unterhalb dieses Betrags werden automatisch abgelehnt (mit Begründung, weiterhin sichtbar). | `50` |
| `mydealz_gruppe` | mydealz-Gruppe für den RSS-Feed. | `vertraege-finanzen` |
| `spartanien_url` | Ziel-URL für den Spartanien-Parser. | `https://www.spartanien.de/` |
| `benachrichtigungen_aktiv` | Push-Benachrichtigung bei neuen Vorschlägen ein-/ausschalten. | `true` |
| `benachrichtigungsgeraete` ("Benachrichtigungsgeräte") | Home-Assistant-Notify-Dienst(e) ohne `notify.`-Präfix, z. B. `mobile_app_pixel_8` für ein bestimmtes Smartphone - mehrere Geräte durch Komma getrennt eintragen, z. B. `mobile_app_pixel_8, mobile_app_iphone_anna` (Gerätename siehe HA unter Einstellungen > Geräte & Dienste > das jeweilige Handy > "Dienst" im Entwicklerwerkzeug). `notify` adressiert weiterhin alle Geräte. | `notify` |

Bei 1×/Tag und wenigen kurzen Texten liegen die tatsächlichen API-Kosten
typischerweise im Cent-Bereich pro Monat.
