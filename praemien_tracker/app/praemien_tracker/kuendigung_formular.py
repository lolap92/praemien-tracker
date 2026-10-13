"""Bankformulare im Kündigungs-Assistenten: ein PDF-Formular der Bank laden
oder hochladen, seine Felder erkennen, ihnen Werte zuordnen und es
ausgefüllt wieder ausgeben (routers/kuendigung.py).

Die Zuordnung "welches Feld bekommt welchen Wert" folgt demselben Prinzip
wie die Briefvorlage: Sie besteht nur aus Platzhaltern ({vorname}, {iban},
...) oder festen Texten. Die KI sieht dafür die Feldnamen, ihre Beschriftung
und den Text des leeren Formulars - nie persönliche Daten. Ohne API-Key
ordnet eine Stichwortsuche über Feldname und Beschriftung zu; das trifft
übliche Felder (Name, Anschrift, IBAN) zuverlässig, bei kryptischen
Feldnamen ("Textfeld 12") aber nichts.

Nicht ausfüllbar sind gescannte PDFs ohne Formularfelder, reine
XFA-Formulare (nur Adobe Reader) und verschlüsselte PDFs, die sich ohne
Zusatzbibliothek nicht öffnen lassen. Dann bleibt das Original zum
Herunterladen plus eine Ausfüllhilfe mit allen bekannten Werten.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import asdict, dataclass, field

import anthropic
import httpx
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from . import config
from . import kuendigung_assistent as ka
from .finder.quellen import USER_AGENT
from .models import Deal, KuendigungFormular

logger = logging.getLogger("praemien_tracker")

MAX_GROESSE = 10 * 1024 * 1024
# Mehr Felder gehen nicht an die KI - ein Kündigungsformular hat selten
# mehr als 40; ein Formular mit Hunderten ist eher ein Kontoeröffnungsantrag.
MAX_FELDER_KI = 150
MAX_TEXT_KI = 6000

AN = "an"
AUS = "aus"

# Feld-Flags (PDF 1.7, Tabelle 226/228)
_FF_NUR_LESEN = 1
_FF_RADIO = 1 << 15
_FF_DRUCKKNOPF = 1 << 16


class FormularFehler(Exception):
    """Fehler mit einer Meldung, die so in der Oberfläche stehen kann."""


@dataclass
class FormFeld:
    name: str
    typ: str  # "text" | "checkbox" | "radio" | "auswahl"
    label: str
    # Checkbox/Radio: die "an"-Zustände ohne führenden Schrägstrich;
    # Auswahl: die Optionen.
    optionen: list[str] = field(default_factory=list)
    max_len: int | None = None


# ------------------------------------------------------------ Einlesen ----


def _text(wert) -> str:
    return str(wert).strip() if wert is not None else ""


def _zustaende(widget) -> list[str]:
    ap = widget.get("/AP")
    if ap is None:
        return []
    normal = ap.get_object().get("/N")
    if normal is None or not hasattr(normal.get_object(), "keys"):
        return []
    return [str(k).lstrip("/") for k in normal.get_object().keys() if str(k) != "/Off"]


def _optionen(opt) -> list[str]:
    ergebnis = []
    for eintrag in opt or []:
        eintrag = eintrag.get_object() if hasattr(eintrag, "get_object") else eintrag
        if isinstance(eintrag, list):
            # [Exportwert, Anzeige] - eingetragen wird der Exportwert.
            ergebnis.append(_text(eintrag[0]))
        else:
            ergebnis.append(_text(eintrag))
    return [o for o in ergebnis if o]


def _sammeln(feld, eltern_name: str, geerbt: dict, ziel: list[FormFeld]) -> None:
    feld = feld.get_object()
    teil = _text(feld.get("/T"))
    name = f"{eltern_name}.{teil}" if eltern_name and teil else (teil or eltern_name)
    geerbt = {
        "/FT": feld.get("/FT", geerbt.get("/FT")),
        "/Ff": int(feld.get("/Ff", geerbt.get("/Ff", 0))),
        "/TU": feld.get("/TU", geerbt.get("/TU")),
        "/Opt": feld.get("/Opt", geerbt.get("/Opt")),
        "/MaxLen": feld.get("/MaxLen", geerbt.get("/MaxLen")),
    }
    kinder = [k.get_object() for k in feld.get("/Kids", [])]
    unterfelder = [k for k in kinder if "/T" in k]
    if unterfelder:
        for kind in unterfelder:
            _sammeln(kind, name, geerbt, ziel)
        return
    if not name:
        return

    ft, ff = geerbt["/FT"], geerbt["/Ff"]
    if ff & _FF_NUR_LESEN:
        return
    label = _text(geerbt["/TU"]) or name
    widgets = kinder or [feld]
    if ft == "/Tx":
        max_len = geerbt["/MaxLen"]
        ziel.append(FormFeld(name, "text", label, max_len=int(max_len) if max_len else None))
    elif ft == "/Btn" and not ff & _FF_DRUCKKNOPF:
        zustaende = list(dict.fromkeys(z for w in widgets for z in _zustaende(w)))
        ziel.append(FormFeld(name, "radio" if ff & _FF_RADIO else "checkbox", label, optionen=zustaende))
    elif ft == "/Ch":
        ziel.append(FormFeld(name, "auswahl", label, optionen=_optionen(geerbt["/Opt"])))
    # /Sig (Unterschrift) und Druckknöpfe bleiben bewusst außen vor.


def _leser(pdf: bytes) -> PdfReader:
    if not pdf.startswith(b"%PDF"):
        raise FormularFehler("Die Datei ist kein PDF.")
    try:
        leser = PdfReader(io.BytesIO(pdf))
    except Exception as exc:
        raise FormularFehler("Das PDF ließ sich nicht lesen.") from exc
    if leser.is_encrypted:
        try:
            ok = leser.decrypt("")
        except Exception as exc:
            # AES-verschlüsselte PDFs bräuchten die Bibliothek cryptography -
            # für ein Formular, das sich auch von Hand ausfüllen lässt, ist
            # das die Abhängigkeit nicht wert.
            raise FormularFehler("Das PDF ist verschlüsselt und lässt sich hier nicht ausfüllen.") from exc
        if not ok:
            raise FormularFehler("Das PDF ist mit einem Passwort geschützt.")
    return leser


def einlesen(pdf: bytes) -> tuple[list[FormFeld], str | None]:
    """(Felder, Hinweis). Ein Hinweis heißt: nicht ausfüllbar, Felder leer.
    Wirft FormularFehler nur, wenn es gar kein lesbares PDF ist."""
    try:
        leser = _leser(pdf)
    except FormularFehler as exc:
        if "verschlüsselt" in str(exc) or "Passwort" in str(exc):
            return [], str(exc)
        raise
    acroform = leser.trailer["/Root"].get("/AcroForm")
    acroform = acroform.get_object() if acroform is not None else None
    felder: list[FormFeld] = []
    if acroform is not None:
        try:
            for f in acroform.get("/Fields", []):
                _sammeln(f, "", {}, felder)
        except Exception:
            logger.exception("Formularfelder ließen sich nicht vollständig lesen.")
            felder = []
    if felder:
        return felder, None
    if acroform is not None and "/XFA" in acroform:
        return [], "Das ist ein XFA-Formular, das sich nur in Adobe Reader ausfüllen lässt."
    return [], "Das PDF hat keine ausfüllbaren Felder - es ist zum Ausdrucken und Ausfüllen von Hand gedacht."


def seitentext(pdf: bytes) -> str:
    try:
        leser = _leser(pdf)
        text = "\n".join((seite.extract_text() or "") for seite in leser.pages[:6])
    except Exception:
        return ""
    return re.sub(r"[ \t]+", " ", text).strip()[:MAX_TEXT_KI]


def von_url_laden(url: str) -> bytes:
    """Lädt das Formular direkt von der Bank. Nur https: die URL stammt aus
    einer KI-Recherche, und ein Ziel im lokalen Netz (http://...) hat hier
    nichts verloren."""
    if not url.lower().startswith("https://"):
        raise FormularFehler("Nur https-Links lassen sich laden.")
    try:
        with httpx.stream(
            "GET", url, timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as antwort:
            antwort.raise_for_status()
            daten = bytearray()
            for stueck in antwort.iter_bytes():
                daten += stueck
                if len(daten) > MAX_GROESSE:
                    raise FormularFehler("Die Datei ist größer als 10 MB.")
    except FormularFehler:
        raise
    except Exception as exc:
        logger.warning("Formular von %s nicht ladbar: %s", url, exc)
        raise FormularFehler("Das Formular ließ sich nicht herunterladen.") from exc
    if not bytes(daten[:1024]).lstrip().startswith(b"%PDF"):
        raise FormularFehler(
            "Unter dem Link liegt kein PDF, sondern vermutlich eine Webseite. "
            "Bitte das Formular dort herunterladen und hier hochladen."
        )
    return bytes(daten)


# ----------------------------------------------------------- Zuordnung ----

# Reihenfolge zählt: der erste Treffer gewinnt. "ort, datum" vor "ort" und
# "datum"; "vorname" vor "name"; Bankangaben ("Name der Bank") gar nicht.
_STICHWOERTER: list[tuple[str, str]] = [
    (r"\bort\b.*\bdatum\b|datum.*\bort\b", "{ort_datum}"),
    (r"geburts", "{geburtsdatum}"),
    (r"vorname", "{vorname}"),
    (r"nachname|familienname|zuname", "{nachname}"),
    (r"name.*bank|bank.*name|kreditinstitut", ""),
    (r"\biban\b", "{iban}"),
    (r"kontonummer|konto-nr|kontonr|depotnummer|depot-nr|depotnr", "{kontonummer}"),
    (r"e-?mail", "{email}"),
    (r"kunden-?n(umme)?r|kundennr", "{kundennummer}"),
    (r"stra(ss|ß)e|anschrift", "{strasse}"),
    (r"\bplz\b|postleitzahl", "{plz}"),
    (r"\bort\b|wohnort|\bstadt\b", "{ort}"),
    (r"\bdatum\b", "{datum}"),
    (r"\bname\b|kontoinhaber|inhaber", "{name}"),
]


def stichwort_zuordnung(felder: list[FormFeld]) -> dict[str, str]:
    zuordnung = {}
    for f in felder:
        if f.typ != "text":
            continue
        such = f"{f.name} {f.label}".lower().replace("_", " ")
        for muster, vorlage in _STICHWOERTER:
            if re.search(muster, such):
                if vorlage:
                    zuordnung[f.name] = vorlage
                break
    return zuordnung


ZUORDNUNG_PROMPT = """\
Das folgende PDF-Formular dient der Kündigung eines {kontoart} bei der Bank
"{bank}". Ordne den Formularfeldern zu, was der Kontoinhaber eintragen muss.

Formularfelder (JSON):
{felder}

Text des leeren Formulars (zur Orientierung, wo welches Feld steht):
---
{text}
---

Du kennst keine persönlichen Daten und darfst keine erfinden. Gib für jedes
Feld, das der Kontoinhaber ausfüllen soll, eine vorlage an:
- Textfelder: ausschließlich Platzhalter in geschweiften Klammern, ggf.
  kombiniert ("{{plz}} {{ort}}"), oder ein fester Text, wenn das Formular
  ihn erwartet (z. B. "Kündigung"). Verfügbare Platzhalter:
{platzhalter}
- Checkboxen: "an" oder "aus" - "an" nur, wenn es für eine vollständige
  Kündigung mit Überweisung des Restguthabens eindeutig richtig ist.
- Radio-Gruppen und Auswahllisten: genau eine der angegebenen Optionen.
Lass Felder weg, die die Bank selbst ausfüllt, die eine Unterschrift
erwarten oder bei denen du unsicher bist.

Verlangt ein Feld eine Angabe, die in der Liste nicht vorkommt (z. B.
Kundennummer, Depotnummer), erfinde einen Platzhalter aus Kleinbuchstaben
und Unterstrichen und führe ihn unter zusatzfelder mit kurzem deutschem
Label und einem Hinweis auf, wo man den Wert findet.
"""


class _Zuordnung(BaseModel):
    feld: str
    vorlage: str


class _ZuordnungErgebnis(BaseModel):
    zuordnungen: list[_Zuordnung] = []
    zusatzfelder: list[ka._Zusatzfeld] = []


def _bekannte_platzhalter() -> dict[str, str]:
    return {**ka.STANDARD_FELDER, **ka.ABGELEITETE_FELDER}


def _bereinigt(ergebnis: _ZuordnungErgebnis, felder: list[FormFeld]) -> tuple[dict[str, str], list[dict]]:
    """Nur Zuordnungen zu tatsächlich vorhandenen Feldern und mit zum Feldtyp
    passendem Wert - was die KI sich bei Checkbox oder Auswahlliste
    ausdenkt, ließe sich ohnehin nicht eintragen."""
    nach_name = {f.name: f for f in felder}
    zuordnung: dict[str, str] = {}
    for z in ergebnis.zuordnungen:
        f = nach_name.get(z.feld.strip())
        vorlage = z.vorlage.strip()
        if f is None or not vorlage:
            continue
        if f.typ == "checkbox" and vorlage.lower() not in (AN, AUS):
            continue
        if f.typ in ("radio", "auswahl") and vorlage not in f.optionen:
            continue
        zuordnung[f.name] = vorlage.lower() if f.typ == "checkbox" else vorlage
    benutzt = ka.platzhalter_in("\n".join(v for n, v in zuordnung.items() if nach_name[n].typ == "text"))
    return zuordnung, ka.zusatzfelder_fuer(benutzt, ergebnis.zusatzfelder)


def ki_zuordnung(
    client: anthropic.Anthropic, deal: Deal, felder: list[FormFeld], text: str
) -> tuple[dict[str, str], list[dict]] | None:
    felder_json = json.dumps(
        [
            {k: v for k, v in asdict(f).items() if v not in (None, [], "")}
            for f in felder[:MAX_FELDER_KI]
        ],
        ensure_ascii=False,
    )
    platzhalter = "\n".join(f"  {{{k}}} - {label}" for k, label in _bekannte_platzhalter().items())
    prompt = ZUORDNUNG_PROMPT.format(
        bank=deal.bank.name, kontoart=deal.kontoart, felder=felder_json, text=text or "(kein Text)", platzhalter=platzhalter
    )
    try:
        antwort = client.messages.parse(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            output_format=_ZuordnungErgebnis,
        )
    except Exception:
        logger.exception("Formular-Zuordnung für %s (%s) fehlgeschlagen.", deal.bank.name, deal.kontoart)
        return None
    if antwort.parsed_output is None:
        return None
    return _bereinigt(antwort.parsed_output, felder)


# ------------------------------------------------- Speichern und Laden ----


def hash_von(pdf: bytes) -> str:
    return hashlib.sha256(pdf).hexdigest()


def formular_fuer(db, deal: Deal) -> KuendigungFormular | None:
    return (
        db.query(KuendigungFormular)
        .filter(KuendigungFormular.bank_name == deal.bank.name, KuendigungFormular.kontoart == deal.kontoart)
        .one_or_none()
    )


def felder_von(formular: KuendigungFormular) -> list[FormFeld]:
    try:
        return [FormFeld(**f) for f in json.loads(formular.felder)]
    except (ValueError, TypeError):
        return []


def zuordnung_von(formular: KuendigungFormular) -> dict[str, str]:
    try:
        wert = json.loads(formular.zuordnung or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in wert.items()} if isinstance(wert, dict) else {}


def zusatzfelder_von(formular: KuendigungFormular) -> list[dict]:
    try:
        wert = json.loads(formular.zusatzfelder or "[]")
    except ValueError:
        return []
    return [z for z in wert if isinstance(z, dict)] if isinstance(wert, list) else []


def zuordnen(formular: KuendigungFormular, deal: Deal, client: anthropic.Anthropic | None) -> None:
    """Setzt die Zuordnung neu - per KI, wenn ein Client da ist und sie
    etwas liefert, sonst per Stichwort."""
    felder = felder_von(formular)
    ergebnis = ki_zuordnung(client, deal, felder, seitentext(formular.pdf)) if client and felder else None
    if ergebnis is not None:
        zuordnung, zusatz = ergebnis
        formular.zuordnung_ki = True
    else:
        zuordnung = stichwort_zuordnung(felder)
        zusatz = ka.zusatzfelder_fuer(ka.platzhalter_in(" ".join(zuordnung.values())), [])
        formular.zuordnung_ki = False
    formular.zuordnung = json.dumps(zuordnung, ensure_ascii=False)
    formular.zusatzfelder = json.dumps(zusatz, ensure_ascii=False) if zusatz else None


def speichern(db, deal: Deal, pdf: bytes, quelle: str, client: anthropic.Anthropic | None) -> KuendigungFormular:
    """Legt das Formular für Bank+Kontoart an oder ersetzt es. Ein PDF mit
    unverändertem Inhalt behält seine Zuordnung - erneutes Laden kostet
    dann keinen API-Aufruf."""
    felder, hinweis = einlesen(pdf)
    formular = formular_fuer(db, deal)
    if formular is not None and hash_von(formular.pdf) == hash_von(pdf):
        formular.quelle = quelle[:500]
        return formular
    if formular is None:
        formular = KuendigungFormular(bank_name=deal.bank.name, kontoart=deal.kontoart)
        db.add(formular)
    formular.quelle = quelle[:500]
    formular.pdf = pdf
    formular.felder = json.dumps([asdict(f) for f in felder], ensure_ascii=False)
    formular.hinweis = hinweis
    zuordnen(formular, deal, client)
    # Eigene Werte für ein anderes Formular passen nicht mehr.
    deal.kuendigung_formular_werte = None
    return formular


# ----------------------------------------------------------- Ausfüllen ----


def eigene_werte(deal: Deal) -> dict[str, str]:
    try:
        wert = json.loads(deal.kuendigung_formular_werte or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in wert.items()} if isinstance(wert, dict) else {}


def _passend_kuerzen(wert: str, max_len: int | None) -> str:
    """Eine IBAN in Vierergruppen ist 27 Zeichen lang, ein Kammfeld dafür
    oft nur 22 - dann ohne Leerzeichen."""
    if max_len and len(wert) > max_len:
        ohne = wert.replace(" ", "")
        return ohne if len(ohne) <= max_len else wert[:max_len]
    return wert


@dataclass
class Feldwert:
    feld: FormFeld
    wert: str  # Text, "an"/"aus" oder Option
    vorschlag: str  # aus der Zuordnung, ohne eigene Eingabe
    fehlt: list[str]  # Platzhalter ohne Wert
    eigen: bool


def feldwerte(formular: KuendigungFormular, deal: Deal) -> list[Feldwert]:
    werte = ka.werte_fuer(deal)
    zuordnung = zuordnung_von(formular)
    eigen = eigene_werte(deal)
    ergebnis = []
    for f in felder_von(formular):
        vorlage = zuordnung.get(f.name, "")
        if f.typ == "text":
            fehlt = [p for p in ka.platzhalter_in(vorlage) if not werte.get(p)]
            vorschlag = "" if fehlt else _passend_kuerzen(ka.einsetzen(vorlage, werte), f.max_len)
        else:
            fehlt = []
            vorschlag = vorlage if f.typ != "checkbox" else (vorlage or AUS)
        wert = eigen[f.name] if f.name in eigen else vorschlag
        ergebnis.append(Feldwert(f, wert, vorschlag, fehlt if f.name not in eigen else [], f.name in eigen))
    return ergebnis


def ausfuellen(pdf: bytes, werte: list[Feldwert]) -> bytes:
    leser = _leser(pdf)
    schreiber = PdfWriter(clone_from=leser)
    eintraege: dict[str, str] = {}
    for fw in werte:
        f = fw.feld
        if f.typ == "checkbox":
            if f.optionen:
                eintraege[f.name] = "/" + f.optionen[0] if fw.wert == AN else "/Off"
        elif f.typ == "radio":
            if fw.wert in f.optionen:
                eintraege[f.name] = "/" + fw.wert
        elif fw.wert:
            eintraege[f.name] = _passend_kuerzen(fw.wert, f.max_len)
    acroform = schreiber._root_object.get("/AcroForm")
    if acroform is not None:
        # Hybrid-Formulare tragen zusätzlich eine XFA-Fassung. Adobe Reader
        # zeigte dann die leere XFA-Fassung statt der ausgefüllten Felder.
        acroform = acroform.get_object()
        if "/XFA" in acroform:
            del acroform[NameObject("/XFA")]
    schreiber.update_page_form_field_values(None, eintraege, auto_regenerate=True)
    ausgabe = io.BytesIO()
    schreiber.write(ausgabe)
    return ausgabe.getvalue()
