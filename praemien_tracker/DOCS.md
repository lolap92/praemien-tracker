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
"Verträge & Finanzen") und spartanien nach neuen Neukunden-Prämien und
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

Ändert sich ein Angebot (z. B. eine höhere Prämie), entsteht bewusst ein
neuer Vorschlag statt eines stillen Updates am alten - die Historie bleibt
so nachvollziehbar. Ein unveränderter Fund wird dagegen nicht erneut
vorgeschlagen, auch nicht nach dem Verwerfen.

Die Suche gilt für **alle** Inhaber, auch minderjährige.

**API-Nutzung wird minimiert:** Bevor ein Fund an Claude geschickt wird,
prüft die App anhand eines Rohtext-Abgleichs, ob dieselbe Quelle-URL mit
demselben Text schon einmal geprüft wurde. Ein unverändertes Angebot löst
dann keinen erneuten API-Aufruf mehr aus - ein bereits als thematisch
unpassend erkannter Fund (z. B. keine Bank-Prämie) wird dauerhaft
übersprungen, ein bereits extrahiertes Angebot wird aus dem Cache
wiederverwendet. Nur wenn sich der Rohtext ändert (z. B. ein bearbeiteter
Beitrag), wird erneut geprüft. Die Übersicht im Vorschläge-Tab zeigt, wie
viele Funde je Lauf ganz ohne API-Aufruf erledigt wurden.

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

## Konfiguration

Ohne jede Einstellung ist das Add-on sofort einsatzbereit - der
KI-Deal-Finder bleibt dann einfach inaktiv. Für den KI-Deal-Finder gibt es
folgende optionale Einstellungen (Add-on-Konfiguration in Home Assistant):

| Option | Zweck | Default |
|---|---|---|
| `anthropic_api_key` | Eigener API-Key von [console.anthropic.com](https://console.anthropic.com) - **kein** claude.ai-Abo (Free/Pro/Max reichen nicht, das ist ein getrenntes Produkt). Ohne Key läuft die App normal weiter, nur ohne Vorschläge. | leer |
| `anthropic_model` | Welches Claude-Modell für die Extraktion genutzt wird. | `claude-haiku-4-5` |
| `mindestpraemie` | Prämien unterhalb dieses Betrags werden automatisch abgelehnt (mit Begründung, weiterhin sichtbar). | `50` |
| `mydealz_gruppe` | mydealz-Gruppe für den RSS-Feed. | `vertraege-finanzen` |
| `spartanien_url` | Ziel-URL für den spartanien-Parser. | `https://www.spartanien.de/themen/bankprodukte/` |

Bei 1×/Tag und wenigen kurzen Texten liegen die tatsächlichen API-Kosten
typischerweise im Cent-Bereich pro Monat.
