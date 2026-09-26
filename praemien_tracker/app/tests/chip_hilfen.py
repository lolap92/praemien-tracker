"""Liest die Trefferzahl eines Filter-Chips aus dem gerenderten HTML
(templates/_filter_chips.html)."""

from __future__ import annotations

import re


def chip_anzahl(html: str, name: str, wert: str) -> int | None:
    treffer = re.search(
        rf'name="{re.escape(name)}" value="{re.escape(wert)}"[^>]*>[^<]*<span class="num">(\d+)</span>',
        html,
    )
    return int(treffer.group(1)) if treffer else None
