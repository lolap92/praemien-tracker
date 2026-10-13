"""Kündigungsbrief als PDF und Word-Datei (kuendigung_assistent.py).

Beide Formate entstehen hier ohne zusätzliche Bibliothek, nur mit der
Standardbibliothek. Der naheliegende Weg wäre fpdf2 bzw. python-docx
gewesen - fpdf2 hängt aber zwingend an Pillow, und für Pillow gibt es keine
fertigen Pakete für armv7: Der Add-on-Build müsste es dort aus dem Quelltext
übersetzen, was im schlanken Basis-Image mangels Compiler und
Bildbibliotheken scheitert. Ein Kündigungsbrief braucht davon ohnehin nichts:
eine Schrift, Text, eine Linie.

- PDF: die in jedem PDF-Betrachter eingebaute Schrift Helvetica mit
  WinAnsiEncoding (deckt Umlaute, ß, €, „" und – ab). Zeichen außerhalb
  davon werden zu "?" - in einem deutschen Kündigungsschreiben praktisch
  nie der Fall.
- Word: ein minimales .docx (ZIP mit WordprocessingML), das Word und
  LibreOffice öffnen und das sich danach frei weiterbearbeiten lässt.

Maße nach DIN 5008 Form B wie in kuendigung_brief.html: Anschriftfeld ab
45 mm von oben, links 25 mm, rechts 20 mm - passt ins DIN-lang-
Fensterkuvert.
"""

from __future__ import annotations

import datetime
import io
import zipfile
import zlib
from dataclasses import dataclass
from xml.sax.saxutils import escape

from .models import Kuendigungsschreiben


@dataclass
class Brief:
    absender: list[str]
    empfaenger: list[str]
    ort_datum: str
    betreff: str
    # Absätze dürfen einzelne Zeilenumbrüche enthalten (z.B. eine Zeile
    # "Girokonto, Kontonummer 4711" direkt unter dem Einleitungssatz).
    absaetze: list[str]
    name: str


def absaetze_aus(text: str) -> list[str]:
    return [a.strip() for a in text.replace("\r\n", "\n").split("\n\n") if a.strip()]


def brief_aus(schreiben: Kuendigungsschreiben) -> Brief:
    datum = schreiben.datum.strftime("%d.%m.%Y")
    return Brief(
        absender=[z for z in schreiben.absender.splitlines() if z.strip()],
        empfaenger=[z for z in (schreiben.empfaenger or "").splitlines() if z.strip()],
        ort_datum=f"{schreiben.ort}, {datum}" if schreiben.ort else datum,
        betreff=schreiben.betreff,
        absaetze=absaetze_aus(schreiben.text),
        name=schreiben.name,
    )


# ---------------------------------------------------------------- PDF ----

# Zeichenbreiten von Helvetica und Helvetica-Bold (Adobe-Standardmetriken,
# Einheiten je 1000 Schriftgröße) für die WinAnsi-Codes 32-255 - nötig für
# den Zeilenumbruch und das Rechtsbündig-Setzen, weil die Schrift selbst
# nicht eingebettet wird.
_BREITEN_REGULAR = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 350,
    556, 350, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350,
    350, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 350, 500, 667,
    278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333,
    400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611,
    667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,
    556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,
)
_BREITEN_FETT = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 350,
    556, 350, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350,
    350, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 350, 500, 667,
    278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333,
    400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611,
    722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,
    556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278,
    611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,
)

_MM = 72 / 25.4
_SEITE_B = 210.0
_SEITE_H = 297.0
_RAND_LINKS = 25.0
_RAND_RECHTS = 20.0
_RAND_UNTEN = 20.0
_RAND_OBEN_FOLGESEITE = 20.0
_SCHRIFT = 11.0
_ZEILE = 14.0 / _MM  # Zeilenabstand 14 pt, in mm


def _kodiert(text: str) -> bytes:
    return text.encode("cp1252", errors="replace")


def _breite_mm(text: str, groesse: float, fett: bool = False) -> float:
    tabelle = _BREITEN_FETT if fett else _BREITEN_REGULAR
    einheiten = sum(tabelle[b - 32] if b >= 32 else 0 for b in _kodiert(text))
    return einheiten * groesse / 1000 / _MM


def _umbrechen(text: str, breite_mm: float, groesse: float, fett: bool = False) -> list[str]:
    """Zeilenumbruch an Leerzeichen; ein einzelnes Wort, das allein zu lang
    ist (z.B. eine lange URL), wird hart geteilt."""
    zeilen: list[str] = []
    for roh in text.split("\n"):
        aktuell = ""
        for wort in roh.split():
            kandidat = f"{aktuell} {wort}" if aktuell else wort
            if _breite_mm(kandidat, groesse, fett) <= breite_mm:
                aktuell = kandidat
                continue
            if aktuell:
                zeilen.append(aktuell)
            while _breite_mm(wort, groesse, fett) > breite_mm:
                teil = wort
                while len(teil) > 1 and _breite_mm(teil, groesse, fett) > breite_mm:
                    teil = teil[:-1]
                zeilen.append(teil)
                wort = wort[len(teil) :]
            aktuell = wort
        zeilen.append(aktuell)
    return zeilen


def _pdf_string(text: str) -> bytes:
    roh = _kodiert(text)
    return b"(" + roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class _Seiten:
    """Sammelt Textbefehle je Seite; y wird in mm von oben gezählt wie im
    Brief-Layout, erst beim Ausgeben in PDF-Koordinaten (von unten)
    umgerechnet."""

    def __init__(self) -> None:
        self.seiten: list[list[bytes]] = [[]]

    def text(self, x_mm: float, y_mm: float, text: str, groesse: float = _SCHRIFT, fett: bool = False) -> None:
        if not text:
            return
        x = x_mm * _MM
        y = (_SEITE_H - y_mm) * _MM
        schrift = b"/F2" if fett else b"/F1"
        self.seiten[-1].append(
            b"BT " + schrift + b" %.1f Tf %.2f %.2f Td " % (groesse, x, y) + _pdf_string(text) + b" Tj ET"
        )

    def linie(self, x1_mm: float, x2_mm: float, y_mm: float) -> None:
        y = (_SEITE_H - y_mm) * _MM
        self.seiten[-1].append(b"0.5 w %.2f %.2f m %.2f %.2f l S" % (x1_mm * _MM, y, x2_mm * _MM, y))

    def neue_seite(self) -> None:
        self.seiten.append([])


def als_pdf(brief: Brief) -> bytes:
    s = _Seiten()
    rechts = _SEITE_B - _RAND_RECHTS
    satzbreite = rechts - _RAND_LINKS

    # Absender oben rechts
    y = 15.0 + _SCHRIFT / _MM
    for zeile in brief.absender:
        s.text(rechts - _breite_mm(zeile, _SCHRIFT), y, zeile)
        y += _ZEILE

    # Rücksendeangabe und Anschriftfeld (45 mm von oben, 85 mm breit)
    ruecksende = " · ".join(brief.absender)
    while ruecksende and _breite_mm(ruecksende, 7) > 85:
        ruecksende = ruecksende[:-1]
    s.text(_RAND_LINKS, 49.0, ruecksende, groesse=7)
    s.linie(_RAND_LINKS, _RAND_LINKS + 85, 50.2)
    y = 50.2 + 1.5 + _SCHRIFT / _MM
    for zeile in brief.empfaenger:
        s.text(_RAND_LINKS, y, zeile)
        y += _ZEILE

    # Datum rechtsbündig unter dem Anschriftfeld, dann Betreff
    y = max(y, 98.5 + _SCHRIFT / _MM)
    s.text(rechts - _breite_mm(brief.ort_datum, _SCHRIFT), y, brief.ort_datum)
    y += 2 * _ZEILE
    for zeile in _umbrechen(brief.betreff, satzbreite, _SCHRIFT, fett=True):
        s.text(_RAND_LINKS, y, zeile, fett=True)
        y += _ZEILE
    y += _ZEILE

    def zeile_setzen(text: str) -> None:
        nonlocal y
        if y > _SEITE_H - _RAND_UNTEN:
            s.neue_seite()
            y = _RAND_OBEN_FOLGESEITE + _SCHRIFT / _MM
        s.text(_RAND_LINKS, y, text)
        y += _ZEILE

    for absatz in brief.absaetze:
        for zeile in _umbrechen(absatz, satzbreite, _SCHRIFT):
            zeile_setzen(zeile)
        y += _ZEILE * 0.85
    # Platz für die Unterschrift
    y += 3 * _ZEILE
    zeile_setzen(brief.name)

    return _pdf_datei(s.seiten, titel=brief.betreff)


def _pdf_datei(seiten: list[list[bytes]], titel: str) -> bytes:
    objekte: list[bytes] = []

    def neu(inhalt: bytes) -> int:
        objekte.append(inhalt)
        return len(objekte)

    katalog = neu(b"")  # wird unten gefüllt, sobald die Seitenliste steht
    seitenbaum = neu(b"")
    f1 = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    seiten_ids = []
    for befehle in seiten:
        daten = zlib.compress(b"\n".join(befehle))
        inhalt = neu(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(daten) + daten + b"\nendstream")
        seiten_ids.append(
            neu(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                % (seitenbaum, _SEITE_B * _MM, _SEITE_H * _MM, f1, f2, inhalt)
            )
        )
    objekte[katalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % seitenbaum
    objekte[seitenbaum - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % i for i in seiten_ids),
        len(seiten_ids),
    )
    # Titel als UTF-16 mit BOM - die einzige Kodierung, in der ein
    # PDF-Textstring Umlaute ohne Umweg sicher darstellt.
    titel_hex = ("feff" + titel.encode("utf-16-be").hex()).encode()
    jetzt = datetime.datetime.now().strftime("D:%Y%m%d%H%M%S").encode()
    info = neu(b"<< /Title <" + titel_hex + b"> /Producer (Praemien-Tracker) /CreationDate (" + jetzt + b") >>")

    ausgabe = io.BytesIO()
    ausgabe.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    versaetze = []
    for nummer, inhalt in enumerate(objekte, start=1):
        versaetze.append(ausgabe.tell())
        ausgabe.write(b"%d 0 obj\n" % nummer + inhalt + b"\nendobj\n")
    xref = ausgabe.tell()
    ausgabe.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1))
    for versatz in versaetze:
        ausgabe.write(b"%010d 00000 n \n" % versatz)
    ausgabe.write(
        b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objekte) + 1, katalog, info, xref)
    )
    return ausgabe.getvalue()


# --------------------------------------------------------------- Word ----

# Word rechnet in Twips (1/20 pt); 1 mm = 56,7 Twips.
def _tw(mm: float) -> int:
    return max(0, round(mm * 56.7))


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{_W_NS}">
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial" w:eastAsia="Arial"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="de-DE"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="0" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Standard"><w:name w:val="Normal"/></w:style>
</w:styles>"""


def _core(titel: str) -> str:
    jetzt = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>{escape(titel)}</dc:title>
<dc:creator>Prämien-Tracker</dc:creator>
<dcterms:created xsi:type="dcterms:W3CDTF">{jetzt}</dcterms:created>
</cp:coreProperties>"""


def _absatz(
    zeilen: list[str],
    *,
    vor_mm: float = 0,
    rechts: bool = False,
    fett: bool = False,
    groesse_pt: float | None = None,
    zeile_exakt_pt: float | None = None,
    rand_rechts_mm: float = 0,
    linie_unten: bool = False,
) -> str:
    ppr = []
    if rechts:
        ppr.append('<w:jc w:val="right"/>')
    abstand = f'w:before="{_tw(vor_mm)}"'
    if zeile_exakt_pt is not None:
        abstand += f' w:line="{round(zeile_exakt_pt * 20)}" w:lineRule="exact"'
    ppr.append(f"<w:spacing {abstand}/>")
    if rand_rechts_mm:
        ppr.append(f'<w:ind w:right="{_tw(rand_rechts_mm)}"/>')
    if linie_unten:
        ppr.append('<w:pBdr><w:bottom w:val="single" w:sz="4" w:space="1" w:color="555555"/></w:pBdr>')
    rpr = []
    if fett:
        rpr.append("<w:b/>")
    if groesse_pt is not None:
        rpr.append(f'<w:sz w:val="{round(groesse_pt * 2)}"/><w:szCs w:val="{round(groesse_pt * 2)}"/>')
    rpr_xml = f"<w:rPr>{''.join(rpr)}</w:rPr>" if rpr else ""
    laeufe = "<w:br/>".join(f'<w:t xml:space="preserve">{escape(z)}</w:t>' for z in zeilen)
    # Ordnung in pPr ist im Schema festgelegt: pBdr vor spacing vor ind vor jc.
    reihenfolge = {"<w:pB": 0, "<w:sp": 1, "<w:in": 2, "<w:jc": 3}
    ppr.sort(key=lambda teil: reihenfolge[teil[:5]])
    return f"<w:p><w:pPr>{''.join(ppr)}{rpr_xml}</w:pPr><w:r>{rpr_xml}{laeufe}</w:r></w:p>"


def als_docx(brief: Brief) -> bytes:
    """Kopfbereich mit exakten Zeilenhöhen, damit das Anschriftfeld wie im
    PDF 45 mm von oben steht; der Brieftext darunter fließt normal und
    lässt sich in Word beliebig weiterbearbeiten."""
    oben = 15.0
    zeile_mm = 14.0 / _MM
    teile = []
    for zeile in brief.absender or [""]:
        teile.append(_absatz([zeile], rechts=True, zeile_exakt_pt=14))
    stand = oben + len(brief.absender or [""]) * zeile_mm

    ruecksende_hoehe = 10 / _MM
    teile.append(
        _absatz(
            [" · ".join(brief.absender)],
            vor_mm=46.0 - stand,
            groesse_pt=7,
            zeile_exakt_pt=10,
            rand_rechts_mm=(_SEITE_B - _RAND_LINKS - _RAND_RECHTS) - 85,
            linie_unten=True,
        )
    )
    stand = max(stand, 46.0) + ruecksende_hoehe + 0.5
    for i, zeile in enumerate(brief.empfaenger):
        teile.append(_absatz([zeile], vor_mm=1.5 if i == 0 else 0, zeile_exakt_pt=14))
    stand += 1.5 + len(brief.empfaenger) * zeile_mm

    teile.append(_absatz([brief.ort_datum], vor_mm=98.5 - stand, rechts=True, zeile_exakt_pt=14))
    teile.append(_absatz([brief.betreff], vor_mm=2 * zeile_mm, fett=True))
    for i, absatz in enumerate(brief.absaetze):
        teile.append(_absatz(absatz.split("\n"), vor_mm=(2 if i == 0 else 1) * zeile_mm * 0.85))
    teile.append(_absatz([brief.name], vor_mm=3.5 * zeile_mm))

    abschnitt = (
        f'<w:sectPr><w:pgSz w:w="{_tw(_SEITE_B)}" w:h="{_tw(_SEITE_H)}"/>'
        f'<w:pgMar w:top="{_tw(oben)}" w:right="{_tw(_RAND_RECHTS)}" w:bottom="{_tw(_RAND_UNTEN)}" '
        f'w:left="{_tw(_RAND_LINKS)}" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
    )
    dokument = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{_W_NS}">'
        f"<w:body>{''.join(teile)}{abschnitt}</w:body></w:document>"
    )

    ausgabe = io.BytesIO()
    with zipfile.ZipFile(ausgabe, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS)
        z.writestr("word/document.xml", dokument)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("docProps/core.xml", _core(brief.betreff))
    return ausgabe.getvalue()
