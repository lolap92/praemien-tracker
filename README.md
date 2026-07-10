# Prämien-Tracker

Private Web-App zur Verwaltung von Bank-Prämien-Deals ("Prämien-Hopping"),
betrieben als Home-Assistant-Add-on. Details zu Anforderungen und
Architekturentscheidungen siehe das ursprüngliche Konzeptdokument.

**Grundprinzip:** Der Nutzer erfasst nur Fakten (Bank, Kontoart, Inhaber,
Prämien, Bedingungen, Kündigungsdaten). Status, Kennzahlen und die
ToDo-Liste werden von der App aus diesen Fakten abgeleitet und nirgends
redundant gespeichert.

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
    ├── build.yaml           # Basis-Images je Architektur
    ├── Dockerfile
    ├── run.sh
    ├── DOCS.md              # wird in der HA-UI als Add-on-Doku angezeigt
    └── app/
        ├── requirements.txt
        ├── alembic.ini
        ├── migrations/      # Alembic-Migrationen (versioniertes Schema)
        └── praemien_tracker/
            ├── models.py    # Fakten (SQLAlchemy-Modelle)
            ├── derived.py   # abgeleitete Sichten: Status, Kennzahlen, ToDos
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

### Optional: vorhandene Datenbank einspielen

Wer bereits eine vorbereitete `praemien.db` hat, kann diese **vor dem
ersten Start** einmalig nach `/addon_configs/<slug>_praemien_tracker/`
kopieren (z. B. über die Samba- oder Terminal/SSH-Add-ons). Die App
erkennt beim Start automatisch eine Datenbank ohne Migrations-Versionsstand
und markiert sie als Baseline, statt die Tabellen erneut anzulegen (siehe
`praemien_tracker/app/praemien_tracker/main.py`).

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
uvicorn praemien_tracker.main:app --reload --port 8000
```

Neue Migration nach einer Modelländerung erzeugen:

```bash
alembic revision --autogenerate -m "kurze beschreibung"
```
