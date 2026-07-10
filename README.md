# Prämien-Tracker

Private Web-App zur Verwaltung von Bank-Prämien-Deals ("Prämien-Hopping"),
betrieben als Home-Assistant-Add-on. Details zu Anforderungen und
Architekturentscheidungen siehe das ursprüngliche Konzeptdokument.

**Grundprinzip:** Der Nutzer erfasst nur Fakten (Bank, Kontoart, Inhaber,
Prämien, Bedingungen, Kündigungsdaten, Kündigung-Anweisungen). Status,
Kennzahlen und die ToDo-Liste werden von der App aus diesen Fakten
abgeleitet und nirgends redundant gespeichert.

Jeder Deal kann eine **Kündigung-Anweisung** tragen (Freitext + optionaler
Link, z. B. zu einem PDF-Kündigungsformular) - hilfreich, wenn der genaue
Kündigungsweg pro Bank nicht offensichtlich ist. Über **Deals → Export**
lässt sich der komplette Datenbestand als Excel-Datei (mehrere Sheets:
Deals, Prämien, Bedingungen, Aufgaben, Links) herunterladen.

## Stack

- **Backend:** FastAPI (Python), server-gerenderte Jinja2-Templates
  (mobil-first, responsive)
- **Datenbank:** SQLite unter `/data/praemien.db`
- **ORM & Migrationen:** SQLAlchemy + Alembic
- **Einbindung:** Home-Assistant-Ingress (Login und Reverse-Proxy inklusive)

## Repo-Struktur

```
praemien-tracker/
├── repository.yaml          # HA-Add-on-Repository-Metadaten
└── praemien_tracker/        # das eigentliche Add-on
    ├── config.yaml          # Add-on-Manifest (Ingress, Architekturen, …)
    ├── Dockerfile           # FROM python:3.12-slim-bookworm (multi-arch)
    ├── run.sh
    ├── DOCS.md              # wird in der HA-UI als Add-on-Doku angezeigt
    └── app/
        ├── requirements.txt
        ├── alembic.ini
        ├── migrations/      # Alembic-Migrationen (versioniertes Schema)
        └── praemien_tracker/
            ├── models.py    # Fakten (SQLAlchemy-Modelle)
            ├── derived.py   # abgeleitete Sichten: Status, Kennzahlen, ToDos
            ├── seed.py      # einmaliger Import aus seed-data.json (Erststart)
            ├── main.py      # FastAPI-App + Migrations-Startup
            ├── routers/     # Übersicht, ToDos, Deals, Vollständigkeit
            ├── templates/   # Jinja2-Templates
            └── static/      # CSS
```

## Installation auf dem Home Assistant Green

1. In Home Assistant unter **Einstellungen → Add-ons → Add-on-Store → ⋮ →
   Repositories** diese Repo-URL hinzufügen:
   `https://github.com/lolap92/praemien-tracker`
2. Das Add-on **Prämien-Tracker** im Store auswählen und **installieren**.
   Der HA-Supervisor baut das Image selbst auf dem Green (aarch64) - dafür
   ist der Build bewusst leichtgewichtig gehalten (schlankes
   `python:3.12-slim`-Basis-Image, keine Kompilierung nötig).
3. Add-on **starten**. Es erscheint per Ingress in der Seitenleiste.

### Optional: Startdaten einspielen

Wer bereits bereinigte Daten hat, legt **vor dem ersten Start** eine
`seed-data.json` (reiner Text, siehe `schemas.SeedData`/`DealImport` für das
Format) in den Add-on-Konfigurationsordner. Der ist z. B. über die
Samba-Freigabe erreichbar unter `\\<HA-IP>\addon_configs\<hash>_praemien_tracker\`
(der Ordner erscheint dort, sobald das Add-on einmal mit der aktuellen
Version gestartet wurde) oder über ein Terminal/SSH-Add-on unter
`/addon_configs/<hash>_praemien_tracker/seed-data.json`. Beim ersten Start
- wenn noch keine `praemien.db` existiert - baut die App daraus die
Datenbank auf und stempelt die Schema-Baseline. Bei jedem weiteren Start
ist die Datenbank bereits vorhanden, der Seed-Import läuft dann nicht
erneut (siehe `praemien_tracker/app/praemien_tracker/seed.py`).

`seed-data.json` enthält private Daten und gehört **nicht** ins Repo -
sie ist in `.gitignore` ausgeschlossen und verbleibt ausschließlich auf
dem Green.

## Schema-Änderungen

Änderungen am Datenmodell werden als neue Alembic-Migration unter
`praemien_tracker/app/migrations/versions/` abgelegt. Beim nächsten
Add-on-Start wendet die App ausstehende Migrationen automatisch an und legt
vorher eine Sicherheitskopie (`praemien.db.bak`) an - zusätzlich zu den
laufenden Home-Assistant-Backups.

## Lokale Entwicklung (ohne Home Assistant)

```bash
cd praemien_tracker/app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATA_DIR=./data
export CONFIG_DIR=./config
uvicorn praemien_tracker.main:app --reload --port 8000
```

Neue Migration nach einer Modelländerung erzeugen:

```bash
alembic revision --autogenerate -m "kurze beschreibung"
```
