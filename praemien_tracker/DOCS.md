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

Wer bereits eine vorbereitete `praemien.db` besitzt (z. B. aus einer
Excel-Migration), kann diese einmalig in das Add-on-Datenverzeichnis legen
(erreichbar z. B. über die Samba- oder SSH/Terminal-Add-ons):

```
/addon_configs/<slug>_praemien_tracker/praemien.db
```

Die Datei muss vor dem ersten Start des Add-ons dort liegen. Die App
erkennt beim Start automatisch, dass die Datenbank noch keinen
Migrations-Versionsstand hat, und markiert sie als Baseline - die Tabellen
werden dabei nicht erneut angelegt.

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
