# Changelog

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
