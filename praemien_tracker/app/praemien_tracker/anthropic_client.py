"""Gemeinsamer Anthropic-Client-Aufbau für alle KI-Funktionen (KI-Deal-Finder,
Kündigungsweg-Recherche). Liefert None ohne hinterlegten API-Key - die
jeweilige Funktion läuft dann normal weiter, nur ohne die KI-Ergänzung."""

from __future__ import annotations

import anthropic

from . import config


def anthropic_client() -> anthropic.Anthropic | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
