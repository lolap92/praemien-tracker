"""Kündigungs-Assistent: bereitet die Kündigung eines Deals als E-Mail oder
druckfertigen Brief vor (routers/kuendigung.py).

Ablauf:
1. Die KI recherchiert einmal je Bank+Kontoart, *wie* gekündigt wird
   (Kanal, Empfänger, Besonderheiten, eigenes Formular?) und liefert eine
   Textvorlage dafür. Das Ergebnis wird gecacht (KuendigungAnforderung),
   wie schon der Kündigungshinweis in kuendigung_recherche.py.
2. Die App gleicht die Platzhalter der Vorlage mit den gespeicherten Daten
   ab und fragt nur nach dem, was fehlt.
3. Die App setzt die Werte lokal ein.

Die wichtigste Entscheidung steckt in Schritt 1: Die KI bekommt nur Bank,
Kontoart und den vorhandenen Kündigungshinweis - nie Name, Anschrift oder
IBAN. Sie schreibt ausschließlich Platzhalter wie {name} oder {iban}. Das hält
persönliche Daten aus der API heraus, und die KI kann keine Kontonummer
erfinden: Was nicht gepflegt ist, bleibt als Lücke sichtbar und wird
abgefragt.

Ohne API-Key (oder wenn die Recherche nichts Verlässliches findet) greift
eine feste Standardvorlage für eine formlose schriftliche Kündigung - der
Assistent funktioniert also auch ganz ohne KI, nur ohne bankspezifische
Hinweise und Empfängerdaten.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import config, iban
from .anthropic_client import anthropic_client
from .models import Deal, KuendigungAnforderung, Kuendigungsschreiben

logger = logging.getLogger("praemien_tracker")

KANAELE: dict[str, str] = {
    "online": "Online im Kundenportal",
    "email": "Per E-Mail",
    "brief": "Per Brief",
    "formular": "Eigenes Formular der Bank",
}

# Platzhalter, die die App selbst füllen kann - Schlüssel -> Label im
# Formular. Alles andere in einer Vorlage ist ein bankspezifisches
# Zusatzfeld (KuendigungAnforderung.zusatzfelder).
STANDARD_FELDER: dict[str, str] = {
    "name": "Vollständiger Name",
    "strasse": "Straße und Hausnummer",
    "plz": "PLZ",
    "ort": "Ort",
    "geburtsdatum": "Geburtsdatum",
    "email": "E-Mail-Adresse",
    "iban": "IBAN für das Restguthaben",
    "kontonummer": "Kontonummer",
    "bank": "Bank",
    "kontoart": "Kontoart",
    "termin": "Kündigungstermin",
}

# Aus den Standardangaben berechnet, nie eigens abgefragt - vor allem für
# Bankformulare, die Vor- und Nachname oder "Ort, Datum" getrennt verlangen
# (kuendigung_formular.py).
ABGELEITETE_FELDER: dict[str, str] = {
    "vorname": "Vorname",
    "nachname": "Nachname",
    "datum": "Heutiges Datum",
    "ort_datum": "Ort, Datum",
}

# Ohne diese Angaben gibt es keinen Absender - im Brief steht er oben links,
# in der E-Mail unter dem Gruß.
ABSENDER_FELDER = ("name", "strasse", "plz", "ort")

STANDARD_TERMIN = "zum nächstmöglichen Zeitpunkt"

ANREDE = "Sehr geehrte Damen und Herren,"
GRUSS = "Mit freundlichen Grüßen"

# Bewusst kein "mein {kontoart}": die Kontoart ist Freitext, und "mein
# Kreditkarte" wäre falsch - die Konstruktion hier passt zu jedem Produkt.
STANDARD_BETREFF = "Kündigung {kontoart}, Kontonummer {kontonummer}"
STANDARD_TEXT = (
    "hiermit kündige ich das folgende Vertragsverhältnis {termin}:\n"
    "\n"
    "{kontoart}, Kontonummer {kontonummer}\n"
    "\n"
    "Ein eventuell vorhandenes Restguthaben überweisen Sie bitte auf mein "
    "Konto mit der IBAN {iban}.\n"
    "\n"
    "Bitte bestätigen Sie mir die Kündigung und das Datum der Beendigung "
    "schriftlich."
)

_PLATZHALTER = re.compile(r"\{([a-z][a-z0-9_]{0,39})\}")

RECHERCHE_PROMPT = """\
Ich möchte in Deutschland ein {kontoart} bei der Bank "{bank}" kündigen.
{hinweis_absatz}
Recherchiere über die Websuche den aktuellen, offiziellen Kündigungsweg -
bevorzugt auf der offiziellen Bank-Website oder bei seriösen
Verbraucherquellen, nicht in Foren - und liefere:

- kanal: "online" (nur im Kundenportal/App), "email", "brief" oder
  "formular" (die Bank verlangt ein eigenes Formular).
- empfaenger_anschrift: Postanschrift für Kündigungen, Zeilen mit \\n
  getrennt, beginnend mit dem Firmennamen. Leer, wenn nicht verlässlich
  gefunden.
- empfaenger_email: E-Mail-Adresse für Kündigungen, nur wenn die Bank sie
  dafür ausdrücklich nennt, sonst leer.
- formular_url: Link auf das Kündigungsformular, falls es eines gibt.
- besonderheiten: kurze Hinweise, was vor oder bei der Kündigung zu
  beachten ist (z. B. "Depot muss vorher leer sein"). Höchstens 4.
- betreff und text: ein Kündigungsschreiben auf Deutsch, förmlich. text ist
  nur der Kern - OHNE Anrede, OHNE Grußformel und OHNE Unterschrift (die
  ergänzt die App), beginnend klein nach der Anrede ("hiermit kündige ich
  ..."). Er muss alle Angaben enthalten, die diese Bank für die Kündigung
  verlangt.
- quelle_url: die URL, auf der du die Informationen gefunden hast.

Du kennst keine persönlichen Daten und darfst keine erfinden. Schreibe für
jede persönliche Angabe ausschließlich einen Platzhalter in geschweiften
Klammern. Verfügbar sind:
{platzhalter_liste}
Verlangt die Bank eine Angabe, die darin nicht vorkommt (z. B. Kundennummer,
Depotnummer), erfinde einen neuen Platzhalter aus Kleinbuchstaben und
Unterstrichen (z. B. {{kundennummer}}) und führe ihn unter zusatzfelder mit
einem kurzen deutschen Label und einem Hinweis auf, wo man den Wert findet.

Findest du keine verlässliche, auf diese Bank bezogene Information, setze
gefunden auf false und lass die übrigen Felder leer.
"""


class _Zusatzfeld(BaseModel):
    schluessel: str
    label: str
    hinweis: str = ""


class _AnforderungErgebnis(BaseModel):
    gefunden: bool
    kanal: str = ""
    empfaenger_anschrift: str = ""
    empfaenger_email: str = ""
    formular_url: str = ""
    besonderheiten: list[str] = []
    zusatzfelder: list[_Zusatzfeld] = []
    betreff: str = ""
    text: str = ""
    quelle_url: str = ""


@dataclass
class Anforderung:
    """Gemeinsame Sicht auf eine recherchierte Anforderung und die
    Standardvorlage - das Template muss beides nicht unterscheiden."""

    kanal: str
    betreff_vorlage: str
    text_vorlage: str
    empfaenger_anschrift: str = ""
    empfaenger_email: str = ""
    formular_url: str = ""
    quelle_url: str = ""
    besonderheiten: list[str] = field(default_factory=list)
    zusatzfelder: list[dict] = field(default_factory=list)
    recherchiert_am: datetime.datetime | None = None

    @property
    def ki(self) -> bool:
        return self.recherchiert_am is not None

    @property
    def kanal_label(self) -> str:
        return KANAELE.get(self.kanal, self.kanal)

    @property
    def platzhalter(self) -> list[str]:
        """Alle Platzhalter in Betreff und Text, in Reihenfolge des ersten
        Auftretens - das ist auch die Reihenfolge der Rückfragen."""
        return platzhalter_in(self.betreff_vorlage + "\n" + self.text_vorlage)


def standard_anforderung() -> Anforderung:
    return Anforderung(kanal="brief", betreff_vorlage=STANDARD_BETREFF, text_vorlage=STANDARD_TEXT)


def _json_liste(text: str | None) -> list:
    if not text:
        return []
    try:
        wert = json.loads(text)
    except ValueError:
        return []
    return wert if isinstance(wert, list) else []


def _aus_zeile(zeile: KuendigungAnforderung) -> Anforderung:
    return Anforderung(
        kanal=zeile.kanal,
        betreff_vorlage=zeile.betreff_vorlage,
        text_vorlage=zeile.text_vorlage,
        empfaenger_anschrift=zeile.empfaenger_anschrift or "",
        empfaenger_email=zeile.empfaenger_email or "",
        formular_url=zeile.formular_url or "",
        quelle_url=zeile.quelle_url or "",
        besonderheiten=[str(b) for b in _json_liste(zeile.besonderheiten)],
        zusatzfelder=[z for z in _json_liste(zeile.zusatzfelder) if isinstance(z, dict)],
        recherchiert_am=zeile.recherchiert_am,
    )


def _gecachte_zeile(db: Session, deal: Deal) -> KuendigungAnforderung | None:
    return (
        db.query(KuendigungAnforderung)
        .filter(KuendigungAnforderung.bank_name == deal.bank.name, KuendigungAnforderung.kontoart == deal.kontoart)
        .one_or_none()
    )


def anforderung_fuer(db: Session, deal: Deal) -> Anforderung:
    """Gecachte Recherche für Bank+Kontoart, sonst die Standardvorlage. Löst
    nie selbst einen API-Aufruf aus - das passiert nur auf Knopfdruck
    (recherchieren), damit das Öffnen der Seite nie auf eine Websuche
    wartet."""
    zeile = _gecachte_zeile(db, deal)
    return _aus_zeile(zeile) if zeile is not None else standard_anforderung()


def _bereinigt(ergebnis: _AnforderungErgebnis) -> dict | None:
    """Macht aus der KI-Antwort die zu speichernden Werte - oder None, wenn
    sie nicht brauchbar ist.

    Ein Platzhalter im Text, den die KI nicht als Zusatzfeld aufgeführt hat,
    wird trotzdem zu einem: sonst stünde er im fertigen Schreiben, ohne dass
    die App je danach fragt. Umgekehrt fallen aufgeführte Zusatzfelder weg,
    die im Text gar nicht vorkommen, und solche, die einen Standard-Schlüssel
    überschreiben würden."""
    betreff = ergebnis.betreff.strip()
    text = ergebnis.text.strip()
    if not ergebnis.gefunden or not betreff or not text:
        return None
    kanal = ergebnis.kanal.strip().lower()
    if kanal not in KANAELE:
        kanal = "brief"

    zusatzfelder = zusatzfelder_fuer(platzhalter_in(betreff + "\n" + text), ergebnis.zusatzfelder)

    besonderheiten = [b.strip() for b in ergebnis.besonderheiten if b.strip()][:4]
    return {
        "kanal": kanal,
        "empfaenger_anschrift": ergebnis.empfaenger_anschrift.strip() or None,
        "empfaenger_email": ergebnis.empfaenger_email.strip() or None,
        "formular_url": ergebnis.formular_url.strip() or None,
        "besonderheiten": json.dumps(besonderheiten, ensure_ascii=False) if besonderheiten else None,
        "zusatzfelder": json.dumps(zusatzfelder, ensure_ascii=False) if zusatzfelder else None,
        "betreff_vorlage": betreff[:300],
        "text_vorlage": text,
        "quelle_url": ergebnis.quelle_url.strip()[:500] or None,
    }


def platzhalter_in(text: str) -> list[str]:
    gesehen: dict[str, None] = {}
    for treffer in _PLATZHALTER.finditer(text):
        gesehen.setdefault(treffer.group(1), None)
    return list(gesehen)


def zusatzfelder_fuer(benutzt, aufgefuehrt_roh) -> list[dict]:
    """Ein Zusatzfeld je benutztem Platzhalter, den die App nicht selbst
    kennt - mit Label und Hinweis aus der KI-Antwort, sofern sie ihn dort
    aufgeführt hat, sonst aus dem Schlüssel gebildet. Gemeinsam für die
    Briefvorlage und die Formular-Zuordnung (kuendigung_formular.py)."""
    aufgefuehrt = {
        z.schluessel.strip(): z
        for z in aufgefuehrt_roh
        if _PLATZHALTER.fullmatch("{" + z.schluessel.strip() + "}")
    }
    zusatzfelder = []
    for schluessel in benutzt:
        if schluessel in STANDARD_FELDER or schluessel in ABGELEITETE_FELDER:
            continue
        z = aufgefuehrt.get(schluessel)
        zusatzfelder.append(
            {
                "schluessel": schluessel,
                "label": (z.label.strip() if z and z.label.strip() else schluessel.replace("_", " ").capitalize()),
                "hinweis": z.hinweis.strip() if z else "",
            }
        )
    return zusatzfelder


def _prompt(deal: Deal) -> str:
    hinweis_absatz = (
        f"Bisher bekannter Kündigungshinweis (kann veraltet sein): {deal.kuendigung_hinweis}\n"
        if deal.kuendigung_hinweis
        else ""
    )
    platzhalter_liste = "\n".join(f"  {{{k}}} - {label}" for k, label in STANDARD_FELDER.items())
    return RECHERCHE_PROMPT.format(
        bank=deal.bank.name,
        kontoart=deal.kontoart,
        hinweis_absatz=hinweis_absatz,
        platzhalter_liste=platzhalter_liste,
    )


def _abfragen(client: anthropic.Anthropic, deal: Deal) -> _AnforderungErgebnis | None:
    try:
        antwort = client.messages.parse(
            model=config.ANTHROPIC_MODEL,
            max_tokens=2048,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": _prompt(deal)}],
            output_format=_AnforderungErgebnis,
        )
    except Exception:
        logger.exception("Kündigungs-Anforderungen für %s (%s) fehlgeschlagen.", deal.bank.name, deal.kontoart)
        return None
    return antwort.parsed_output


def recherchieren(db: Session, deal: Deal) -> Anforderung | None:
    """Recherchiert die Anforderungen für Bank+Kontoart dieses Deals frisch
    und ersetzt einen vorhandenen Cache-Eintrag. None, wenn kein API-Key
    hinterlegt ist, der Demo-Modus läuft oder nichts Verlässliches gefunden
    wurde - ein bestehender Eintrag bleibt dann unangetastet, eine
    fehlgeschlagene Neu-Recherche wirft also nichts weg."""
    if config.DEMO_MODUS:
        return None
    client = anthropic_client()
    if client is None:
        return None
    ergebnis = _abfragen(client, deal)
    werte = _bereinigt(ergebnis) if ergebnis is not None else None
    if werte is None:
        return None

    zeile = _gecachte_zeile(db, deal)
    if zeile is None:
        zeile = KuendigungAnforderung(bank_name=deal.bank.name, kontoart=deal.kontoart)
        db.add(zeile)
    for name, wert in werte.items():
        setattr(zeile, name, wert)
    zeile.recherchiert_am = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    db.commit()
    return _aus_zeile(zeile)


def angaben_laden(deal: Deal) -> dict[str, str]:
    if not deal.kuendigung_angaben:
        return {}
    try:
        wert = json.loads(deal.kuendigung_angaben)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in wert.items()} if isinstance(wert, dict) else {}


def angaben_speichern(deal: Deal, angaben: dict[str, str]) -> None:
    bereinigt = {k: v for k, v in angaben.items() if v}
    deal.kuendigung_angaben = json.dumps(bereinigt, ensure_ascii=False, sort_keys=True) if bereinigt else None


def werte_fuer(deal: Deal) -> dict[str, str]:
    """Alle bekannten Werte für die Platzhalter - leer heißt "fehlt".

    Der kurze Inhaber-Name zählt bewusst nicht als vollständiger Name: ein
    Kündigungsschreiben, das mit "Max" unterschrieben ist, ordnet die Bank
    womöglich nicht zu. Das Formular schlägt ihn aber als Startwert vor."""
    inhaber = deal.inhaber
    angaben = angaben_laden(deal)
    werte = {
        "name": inhaber.voller_name or "",
        "strasse": inhaber.strasse or "",
        "plz": inhaber.plz or "",
        "ort": inhaber.ort or "",
        "geburtsdatum": inhaber.geburtsdatum.strftime("%d.%m.%Y") if inhaber.geburtsdatum else "",
        "email": inhaber.email or "",
        "iban": iban.formatiert(inhaber.iban),
        "kontonummer": deal.kontonummer or "",
        "bank": deal.bank.name,
        "kontoart": deal.kontoart,
        "termin": angaben.get("termin") or STANDARD_TERMIN,
    }
    # Vorname = alles bis zum letzten Wort. Bei Doppelnamen ("Anna-Lena
    # von Berg") nicht immer richtig - im Formular lässt sich das je Feld
    # überschreiben.
    teile = werte["name"].rsplit(" ", 1)
    werte["vorname"] = teile[0] if len(teile) == 2 else ""
    werte["nachname"] = teile[-1] if werte["name"] else ""
    werte["datum"] = datetime.date.today().strftime("%d.%m.%Y")
    werte["ort_datum"] = f"{werte['ort']}, {werte['datum']}" if werte["ort"] else ""
    for schluessel, wert in angaben.items():
        if schluessel not in werte:
            werte[schluessel] = wert
    return werte


def label_fuer(anforderung: Anforderung, schluessel: str) -> str:
    if schluessel in STANDARD_FELDER:
        return STANDARD_FELDER[schluessel]
    if schluessel in ABGELEITETE_FELDER:
        return ABGELEITETE_FELDER[schluessel]
    for z in anforderung.zusatzfelder:
        if z.get("schluessel") == schluessel:
            return z.get("label") or schluessel
    return schluessel


def fehlende(anforderung: Anforderung, werte: dict[str, str]) -> list[str]:
    """Platzhalter der Vorlage ohne Wert - solange einer fehlt, gibt es kein
    fertiges Schreiben, nur die Rückfrage danach."""
    return [p for p in anforderung.platzhalter if not werte.get(p)]


def absender_fehlend(werte: dict[str, str]) -> list[str]:
    return [f for f in ABSENDER_FELDER if not werte.get(f)]


def einsetzen(vorlage: str, werte: dict[str, str]) -> str:
    """Setzt die Werte ein. Ein unbekannter Platzhalter bleibt stehen, wie er
    ist - aufgefallen wäre er vorher schon in fehlende()."""
    return _PLATZHALTER.sub(lambda m: werte.get(m.group(1)) or m.group(0), vorlage)


def schreiben(anforderung: Anforderung, werte: dict[str, str]) -> dict[str, str]:
    """Betreff und Text inklusive Anrede und Grußformel, ohne Namen - der
    wird je nach Kanal unterschiedlich angefügt (im Brief mit Platz für die
    Unterschrift, in der E-Mail mit Anschrift darunter)."""
    kern = einsetzen(anforderung.text_vorlage, werte).strip()
    return {
        "betreff": einsetzen(anforderung.betreff_vorlage, werte).strip(),
        "text": f"{ANREDE}\n\n{kern}\n\n{GRUSS}",
    }


def mail_signatur(werte: dict[str, str]) -> str:
    return "\n".join(absender_zeilen(werte))


def absender_zeilen(werte: dict[str, str]) -> list[str]:
    zeilen = [werte.get("name", ""), werte.get("strasse", ""), f"{werte.get('plz', '')} {werte.get('ort', '')}".strip()]
    return [z for z in zeilen if z]


def schreiben_speichern(
    deal: Deal, kanal: str, betreff: str, text: str, datei: bytes | None = None
) -> Kuendigungsschreiben:
    """Hält ein Schreiben als Momentaufnahme fest. Solange zum selben Kanal
    noch ein unversendeter Entwurf existiert, wird der überschrieben statt
    ein weiterer angelegt - wer nach einer Korrektur das PDF erneut
    herunterlädt, soll nicht drei fast gleiche Entwürfe in der Liste haben.
    Ein versendetes Schreiben wird dagegen nie mehr verändert."""
    werte = werte_fuer(deal)
    entwurf = next(
        (s for s in reversed(deal.kuendigungsschreiben) if s.kanal == kanal and s.versendet_am is None),
        None,
    )
    if entwurf is None:
        entwurf = Kuendigungsschreiben(kanal=kanal)
        deal.kuendigungsschreiben.append(entwurf)
    if kanal == "email":
        entwurf.empfaenger = deal.bank.kuendigung_email or None
        # In der E-Mail steht die Anschrift unter dem Gruß statt im Briefkopf.
        signatur = mail_signatur(werte)
        text = f"{text}\n{signatur}" if signatur else text
    else:
        entwurf.empfaenger = deal.bank.anschrift or None
    entwurf.absender = "\n".join(absender_zeilen(werte))
    entwurf.ort = werte.get("ort") or None
    entwurf.datum = datetime.date.today()
    entwurf.betreff = betreff[:300]
    entwurf.text = text
    entwurf.name = werte.get("name", "")
    entwurf.datei = datei
    return entwurf
