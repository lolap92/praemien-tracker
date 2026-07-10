# Changelog

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
