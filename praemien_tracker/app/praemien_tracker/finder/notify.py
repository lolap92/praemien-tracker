"""Push-Benachrichtigung über das zentrale Home-Assistant-Skript
`script.benachrichtigung_senden`.

Setzt `homeassistant_api: true` im Add-on-Manifest voraus (config.yaml) -
dann setzt der Supervisor die Umgebungsvariable SUPERVISOR_TOKEN automatisch,
ein eigener Zugangsdaten-Eintrag ist nicht nötig. Welche Geräte das Skript
anspricht, ist über die Add-on-Option "benachrichtigungsgeraete" konfigurierbar
(mehrere, kommagetrennt, siehe config.py); per "benachrichtigungen_aktiv"
lässt sich die Benachrichtigung ganz abschalten.

Das Skript selbst kümmert sich um den gerätespezifischen notify-Versand
(damit aktionsfähige Buttons zuverlässig funktionieren) und protokolliert den
vollständigen Text zentral fürs Benachrichtigungen-Dashboard - der
Prämien-Tracker ruft es deshalb mit genau einem Service-Call für alle
konfigurierten Geräte auf, statt wie zuvor je Gerät einen eigenen
notify-Dienst direkt anzusprechen.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("praemien_tracker.finder")

SUPERVISOR_SCRIPT_URL = "http://supervisor/core/api/services/script/benachrichtigung_senden"


def benachrichtigen(
    anzahl_vorgeschlagen: int,
    anzahl_zu_pruefen: int,
    *,
    aktiv: bool = True,
    geraete: list[str] | None = None,
    timeout: float = 10.0,
    nachricht: str | None = None,
) -> bool:
    """Kurznachricht bei neuen vorgeschlagenen oder zu prüfenden Funden, über
    das zentrale Skript `script.benachrichtigung_senden` an die konfigurierten
    Zielgeräte. Gibt zurück, ob der Skript-Aufruf erfolgreich war.

    Rein automatisch abgelehnte Funde lösen bewusst keine Benachrichtigung
    aus (Konzept Abschnitt 6, Schritt 7) - sie bleiben nur im Tab sichtbar.
    Ohne SUPERVISOR_TOKEN (z.B. lokal außerhalb des Add-ons), bei
    `aktiv=False` oder ohne konfigurierte Zielgeräte wird nur geloggt, kein
    Fehler.
    """
    if not aktiv:
        logger.info(
            "Benachrichtigungen sind per Konfiguration deaktiviert - übersprungen: "
            "%d vorgeschlagen, %d zu prüfen.",
            anzahl_vorgeschlagen,
            anzahl_zu_pruefen,
        )
        return False

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        logger.info(
            "Kein SUPERVISOR_TOKEN gesetzt (außerhalb des Add-ons?) - Benachrichtigung übersprungen: "
            "%d vorgeschlagen, %d zu prüfen.",
            anzahl_vorgeschlagen,
            anzahl_zu_pruefen,
        )
        return False

    ziel_geraete = [g.strip() for g in (geraete or []) if g.strip()]
    if not ziel_geraete:
        logger.info(
            "Keine Zielgeräte konfiguriert - Benachrichtigung übersprungen: "
            "%d vorgeschlagen, %d zu prüfen.",
            anzahl_vorgeschlagen,
            anzahl_zu_pruefen,
        )
        return False

    if nachricht is None:
        teile = []
        if anzahl_vorgeschlagen:
            teile.append(f"{anzahl_vorgeschlagen} neue Vorschläge")
        if anzahl_zu_pruefen:
            teile.append(f"{anzahl_zu_pruefen} zu prüfen")
        nachricht = "Prämien-Tracker: " + " · ".join(teile)

    try:
        antwort = httpx.post(
            SUPERVISOR_SCRIPT_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "geraete": ziel_geraete,
                "titel": "Prämien-Tracker",
                "nachricht": nachricht,
                "quelle": "Prämien-Tracker",
            },
            timeout=timeout,
        )
        antwort.raise_for_status()
        return True
    except Exception:
        logger.exception("Benachrichtigung über script.benachrichtigung_senden fehlgeschlagen.")
        return False
