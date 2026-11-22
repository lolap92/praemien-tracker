"""Datenbank-Backup direkt aus der App: Anzeigeseite, Download, Upload/Restore
(siehe backup.py)."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from .. import backup
from ..ingress import redirect
from ..templating import templates

router = APIRouter()


@router.get("/backup")
def backup_seite(request: Request):
    return templates.TemplateResponse("backup.html", {"request": request})


@router.post("/backup/herunterladen")
def herunterladen(request: Request):
    # Bewusst POST, nicht GET: zip_erstellen() legt über erstellen() eine
    # frische Sicherung in BACKUP_DIR an und rotiert ältere weg. Als GET-Link
    # hätten schon ein Prefetch des Browsers oder ein Neuladen der Seite die
    # Rotation weitergedreht.
    #
    # Die Datei selbst kommt aber per Weiterleitung über ein GET
    # (backup_datei): Die Home-Assistant-App auf Android reicht Downloads an
    # den Android-Download-Manager weiter, und der lädt die Adresse erneut
    # per GET - eine direkte Antwort auf das POST endete dort mit "Fehler bei
    # Download" ohne Dateinamen. Im Browser ändert sich nichts: Die Datei wird
    # heruntergeladen, die Seite bleibt stehen.
    dateiname = backup.zip_fuer_download_ablegen()
    return redirect(request, f"backup/datei/{dateiname}")


@router.get("/backup/datei/{dateiname}")
def backup_datei(dateiname: str):
    # Liefert nur ein schon abgelegtes ZIP aus und legt nichts Neues an -
    # ein Prefetch oder wiederholter Abruf dreht keine Rotation weiter.
    pfad = backup.download_pfad(dateiname)
    if pfad is None:
        raise HTTPException(status_code=404, detail="Backup-Datei nicht gefunden - bitte neu herunterladen.")
    return FileResponse(pfad, media_type="application/zip", filename=dateiname)


@router.post("/backup/wiederherstellen")
async def wiederherstellen(request: Request, datei: UploadFile = File(...)):
    inhalt = await datei.read()
    try:
        konfiguration_wiederhergestellt, konfiguration_dauerhaft = backup.wiederherstellen(inhalt)
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    return templates.TemplateResponse(
        "backup_wiederhergestellt.html",
        {
            "request": request,
            "konfiguration_wiederhergestellt": konfiguration_wiederhergestellt,
            "konfiguration_dauerhaft": konfiguration_dauerhaft,
        },
    )
