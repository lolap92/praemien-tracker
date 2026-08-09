"""Push-Benachrichtigung über die Home-Assistant-Core-API.

Setzt `homeassistant_api: true` im Add-on-Manifest voraus (config.yaml) -
dann setzt der Supervisor die Umgebungsvariable SUPERVISOR_TOKEN automatisch,
ein eigener Zugangsdaten-Eintrag ist nicht nötig. Welche Geräte (Dienste)
erreicht werden, ist über die Add-on-Option "benachrichtigungsgeraete"
konfigurierbar (mehrere, kommagetrennt); per "benachrichtigungen_aktiv"
lässt sich die Benachrichtigung ganz abschalten.
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
    geraete: list[str] | None = None,
    timeout: float = 10.0,
    nachricht: str | None = None,
) -> bool:
    """Kurznachricht bei neuen vorgeschlagenen oder zu prüfenden Funden, an
    ein oder mehrere Geräte (Home-Assistant-Notify-Dienste). Gibt zurück, ob
    mindestens ein Gerät erfolgreich erreicht wurde - für den täglichen Lauf
    ungenutzt, aber die Grundlage für die manuelle Test-Benachrichtigung in
    den Vorschlägen ("Funktioniert die Benachrichtigung?").

    Rein automatisch abgelehnte Funde lösen bewusst keine Benachrichtigung
    aus (Konzept Abschnitt 6, Schritt 7) - sie bleiben nur im Tab sichtbar.
    Ohne SUPERVISOR_TOKEN (z.B. lokal außerhalb des Add-ons) oder bei
    `aktiv=False` wird nur geloggt, kein Fehler. Schlägt der Versand an ein
    einzelnes Gerät fehl (z.B. Tippfehler im Dienstnamen), werden die
    übrigen konfigurierten Geräte trotzdem benachrichtigt - ein Fehler wird
    nur geloggt, nicht weitergeworfen.
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

    if nachricht is None:
        teile = []
        if anzahl_vorgeschlagen:
            teile.append(f"{anzahl_vorgeschlagen} neue Vorschläge")
        if anzahl_zu_pruefen:
            teile.append(f"{anzahl_zu_pruefen} zu prüfen")
        nachricht = "Prämien-Tracker: " + " · ".join(teile)

    erfolgreich = False
    for dienst in geraete or ["notify"]:
        dienst = dienst.strip() or "notify"
        try:
            antwort = httpx.post(
                SUPERVISOR_NOTIFY_URL_VORLAGE.format(dienst=dienst),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"title": "Prämien-Tracker", "message": nachricht},
                timeout=timeout,
            )
            antwort.raise_for_status()
            erfolgreich = True
        except Exception:
            logger.exception("Benachrichtigung an Dienst 'notify.%s' fehlgeschlagen.", dienst)
    return erfolgreich
