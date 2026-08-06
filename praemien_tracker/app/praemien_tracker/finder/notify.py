"""Push-Benachrichtigung über die Home-Assistant-Core-API.

Setzt `homeassistant_api: true` im Add-on-Manifest voraus (config.yaml) -
dann setzt der Supervisor die Umgebungsvariable SUPERVISOR_TOKEN automatisch,
ein eigener Zugangsdaten-Eintrag ist nicht nötig. Welcher Dienst (und damit
welches Gerät/welche Person) erreicht wird, ist über die Add-on-Option
"notify_dienst" konfigurierbar; per "benachrichtigungen_aktiv" lässt sich die
Benachrichtigung ganz abschalten.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("praemien_tracker.finder")

SUPERVISOR_NOTIFY_URL_VORLAGE = "http://supervisor/core/api/services/notify/{dienst}"


def benachrichtigen(
    anzahl_vorgeschlagen: int,
    anzahl_zu_pruefen: int,
    *,
    aktiv: bool = True,
    dienst: str = "notify",
    timeout: float = 10.0,
) -> None:
    """Kurznachricht bei neuen vorgeschlagenen oder zu prüfenden Funden.

    Rein automatisch abgelehnte Funde lösen bewusst keine Benachrichtigung
    aus (Konzept Abschnitt 6, Schritt 7) - sie bleiben nur im Tab sichtbar.
    Ohne SUPERVISOR_TOKEN (z.B. lokal außerhalb des Add-ons) oder bei
    `aktiv=False` wird nur geloggt, kein Fehler.
    """
    if not aktiv:
        logger.info(
            "Benachrichtigungen sind per Konfiguration deaktiviert - übersprungen: "
            "%d vorgeschlagen, %d zu prüfen.",
            anzahl_vorgeschlagen,
            anzahl_zu_pruefen,
        )
        return

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        logger.info(
            "Kein SUPERVISOR_TOKEN gesetzt (außerhalb des Add-ons?) - Benachrichtigung übersprungen: "
            "%d vorgeschlagen, %d zu prüfen.",
            anzahl_vorgeschlagen,
            anzahl_zu_pruefen,
        )
        return

    teile = []
    if anzahl_vorgeschlagen:
        teile.append(f"{anzahl_vorgeschlagen} neue Vorschläge")
    if anzahl_zu_pruefen:
        teile.append(f"{anzahl_zu_pruefen} zu prüfen")
    nachricht = "Prämien-Tracker: " + " · ".join(teile)

    antwort = httpx.post(
        SUPERVISOR_NOTIFY_URL_VORLAGE.format(dienst=dienst or "notify"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"title": "Prämien-Tracker", "message": nachricht},
        timeout=timeout,
    )
    antwort.raise_for_status()
