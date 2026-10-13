"""IBAN-Hilfen für die Referenzkonto-Angabe am Inhaber (Kündigungs-Assistent).

Eigenes, abhängigkeitsfreies Modul, weil sowohl protokoll.py (Maskierung)
als auch die Router es brauchen - helpers.py zieht über die KI-Recherchen
den Anthropic-Client nach sich und eignet sich nicht als Import für das
Protokoll."""

from __future__ import annotations


def normalisieren(eingabe: str | None) -> str | None:
    """Leerzeichen raus, Großbuchstaben - so wie sie im Feld landet. Leere
    Eingabe heißt "nicht erfasst" (None)."""
    if eingabe is None:
        return None
    wert = "".join(eingabe.split()).upper()
    return wert or None


def gueltig(iban: str | None) -> bool:
    """Prüfsumme nach ISO 13616 (mod 97). Fängt Tippfehler ab, bevor ein
    Restguthaben auf ein falsches Konto überwiesen werden soll - sagt aber
    nichts darüber, ob das Konto existiert."""
    if not iban or len(iban) < 15 or len(iban) > 34 or not iban.isalnum():
        return False
    if not (iban[:2].isalpha() and iban[2:4].isdigit()):
        return False
    umgestellt = iban[4:] + iban[:4]
    try:
        zahl = int("".join(str(int(z, 36)) for z in umgestellt))
    except ValueError:
        return False
    return zahl % 97 == 1


def formatiert(iban: str | None) -> str:
    """In Vierergruppen, wie sie auf Papier lesbar ist."""
    if not iban:
        return ""
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def maskiert(iban: str | None) -> str | None:
    """Für das Änderungsprotokoll: erkennbar, welches Konto es war, ohne die
    vollständige Nummer ein zweites Mal im Klartext abzulegen."""
    if not iban:
        return iban
    if len(iban) <= 8:
        return "…" + iban[-2:]
    return f"{iban[:4]} … {iban[-4:]}"
