"""Datenbank-Backup direkt aus der App: Anzeigeseite, Download, Upload/Restore
(siehe backup.py)."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from .. import backup
from ..templating import templates

router = APIRouter()


@router.get("/backup")
def backup_seite(request: Request):
    return templates.TemplateResponse("backup.html", {"request": request})


@router.get("/backup/herunterladen")
def herunterladen() -> Response:
    dateiname, inhalt = backup.zip_erstellen()
    return Response(
        content=inhalt,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


@router.post("/backup/wiederherstellen")
async def wiederherstellen(request: Request, datei: UploadFile = File(...)):
    inhalt = await datei.read()
    try:
        konfiguration_wiederhergestellt = backup.wiederherstellen(inhalt)
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    return templates.TemplateResponse(
        "backup_wiederhergestellt.html",
        {"request": request, "konfiguration_wiederhergestellt": konfiguration_wiederhergestellt},
    )
