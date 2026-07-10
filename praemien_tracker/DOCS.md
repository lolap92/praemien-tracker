# Prämien-Tracker

Private Web-App zur Verwaltung von Bank-Prämien-Deals. Läuft ausschließlich
im Heimnetz und wird über die Home-Assistant-Ingress-Funktion aufgerufen -
es ist keine zusätzliche Portfreigabe oder Anmeldung nötig.

## Grundprinzip

Du erfasst nur Fakten (Bank, Kontoart, Inhaber, Prämien, Bedingungen,
Kündigungsdaten). Status, Kennzahlen und die ToDo-Liste berechnet die App
automatisch daraus - sie werden nirgends redundant gepflegt.

## Erste Schritte

1. Add-on starten.
2. Über die Seitenleiste öffnen (Ingress).
3. Unter "Neuer Deal" den ersten Deal anlegen - entweder per Formular oder
   per JSON-Einfügen.

## Startdaten einspielen (optional, einmalig)

Wer bereits bereinigte Daten besitzt (z. B. aus einer Excel-Migration),
legt einmalig eine `seed-data.json` in das Add-on-Datenverzeichnis
(erreichbar z. B. über die Samba- oder SSH/Terminal-Add-ons):

```
/addon_configs/<slug>_praemien_tracker/seed-data.json
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
- Vor jeder Schema-Migration wird automatisch eine Kopie
  (`praemien.db.bak`) angelegt.
- Die Datei liegt im persistenten Add-on-Verzeichnis und wird damit von den
  regulären Home-Assistant-Backups mit erfasst.
- Es werden bewusst keine Zugangsdaten (Login/Passwort/TAN) gespeichert -
  nur ein Flag, ob diese im Passwortmanager gesichert sind.

## Konfiguration

Das Add-on hat keine Optionen - es ist sofort einsatzbereit.
