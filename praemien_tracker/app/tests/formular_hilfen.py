"""Baut ein kleines, echtes AcroForm-PDF für die Formular-Tests - ohne
fremde Testdatei im Repository und ohne Bibliothek, die Formulare anlegen
kann (pypdf füllt nur aus)."""

from __future__ import annotations


def formular_pdf(felder: list[dict]) -> bytes:
    """felder: dicts mit name, typ ("tx" | "cb" | "radio" | "ch"),
    optional tooltip, max_len, nur_lesen, optionen, eltern (Name eines
    übergeordneten Felds für hierarchische Namen)."""
    objekte: list[bytes] = []

    def neu(inhalt: bytes) -> int:
        objekte.append(inhalt)
        return len(objekte)

    katalog = neu(b"")
    seiten = neu(b"")
    schrift = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    text = b"BT /F1 12 Tf 50 800 Td (Kuendigungsformular Testbank) Tj ET"
    inhalt = neu(b"<< /Length %d >>\nstream\n" % len(text) + text + b"\nendstream")
    seite = neu(b"")
    widgets: list[int] = []
    wurzeln: list[int] = []
    eltern_ids: dict[str, tuple[int, list[int]]] = {}
    y = 760
    for f in felder:
        y -= 30
        rect = b"[50 %d 300 %d]" % (y, y + 18)
        tip = b" /TU <feff" + f.get("tooltip", "").encode("utf-16-be").hex().encode() + b">" if f.get("tooltip") else b""
        ff = (1 if f.get("nur_lesen") else 0)
        name = f["name"].encode()
        if f["typ"] == "tx":
            extra = b" /MaxLen %d" % f["max_len"] if f.get("max_len") else b""
            obj = b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (%s)%s /Rect %s /P %d 0 R /DA (/Helv 10 Tf 0 g) /F 4 /Ff %d%s >>" % (
                name, tip, rect, seite, ff, extra)
            wid = neu(obj)
            widgets.append(wid)
            ziel = wid
        elif f["typ"] == "cb":
            an = neu(b"<< /Length 0 >>\nstream\n\nendstream")
            aus = neu(b"<< /Length 0 >>\nstream\n\nendstream")
            wid = neu(b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (%s)%s /Rect %s /P %d 0 R /V /Off /AS /Off /F 4 /Ff %d /AP << /N << /Ja %d 0 R /Off %d 0 R >> >> >>" % (
                name, tip, rect, seite, ff, an, aus))
            widgets.append(wid)
            ziel = wid
        elif f["typ"] == "radio":
            gruppe = neu(b"")
            kinder = []
            for i, option in enumerate(f["optionen"]):
                an = neu(b"<< /Length 0 >>\nstream\n\nendstream")
                aus = neu(b"<< /Length 0 >>\nstream\n\nendstream")
                kid = neu(b"<< /Type /Annot /Subtype /Widget /Parent %d 0 R /Rect [%d %d %d %d] /P %d 0 R /AS /Off /F 4 /AP << /N << /%s %d 0 R /Off %d 0 R >> >> >>" % (
                    gruppe, 50 + i * 30, y, 62 + i * 30, y + 12, seite, option.encode(), an, aus))
                kinder.append(kid)
                widgets.append(kid)
            objekte[gruppe - 1] = b"<< /FT /Btn /T (%s)%s /Ff %d /V /Off /Kids [%s] >>" % (
                name, tip, (1 << 15) | (1 << 14) | ff, b" ".join(b"%d 0 R" % k for k in kinder))
            ziel = gruppe
        else:
            opts = b" ".join(b"(%s)" % o.encode() for o in f["optionen"])
            wid = neu(b"<< /Type /Annot /Subtype /Widget /FT /Ch /T (%s)%s /Rect %s /P %d 0 R /DA (/Helv 10 Tf 0 g) /F 4 /Ff %d /Opt [%s] >>" % (
                name, tip, rect, seite, (1 << 17) | ff, opts))
            widgets.append(wid)
            ziel = wid
        if f.get("eltern"):
            if f["eltern"] not in eltern_ids:
                eid = neu(b"")
                eltern_ids[f["eltern"]] = (eid, [])
                wurzeln.append(eid)
            eid, kids = eltern_ids[f["eltern"]]
            kids.append(ziel)
            objekte[ziel - 1] = objekte[ziel - 1][:-2] + b" /Parent %d 0 R >>" % eid
        else:
            wurzeln.append(ziel)
    for eltern, (eid, kids) in eltern_ids.items():
        objekte[eid - 1] = b"<< /T (%s) /Kids [%s] >>" % (eltern.encode(), b" ".join(b"%d 0 R" % k for k in kids))

    annots = b" ".join(b"%d 0 R" % w for w in widgets)
    objekte[seite - 1] = (
        b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
        b"/Resources << /Font << /F1 %d 0 R >> >> /Annots [%s] >>" % (seiten, inhalt, schrift, annots)
    )
    objekte[seiten - 1] = b"<< /Type /Pages /Kids [%d 0 R] /Count 1 >>" % seite
    objekte[katalog - 1] = (
        b"<< /Type /Catalog /Pages %d 0 R /AcroForm << /Fields [%s] /DR << /Font << /Helv %d 0 R >> >> "
        b"/DA (/Helv 10 Tf 0 g) >> >>" % (seiten, b" ".join(b"%d 0 R" % w for w in wurzeln), schrift)
    )
    ausgabe = bytearray(b"%PDF-1.4\n")
    versaetze = []
    for nummer, obj in enumerate(objekte, start=1):
        versaetze.append(len(ausgabe))
        ausgabe += b"%d 0 obj\n" % nummer + obj + b"\nendobj\n"
    xref = len(ausgabe)
    ausgabe += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    for v in versaetze:
        ausgabe += b"%010d 00000 n \n" % v
    ausgabe += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objekte) + 1, katalog, xref)
    return bytes(ausgabe)


STANDARD_FORMULAR = [
    {"name": "Feld1", "typ": "tx", "tooltip": "Vorname"},
    {"name": "Feld2", "typ": "tx", "tooltip": "Nachname"},
    {"name": "Strasse", "typ": "tx"},
    {"name": "PLZ", "typ": "tx"},
    {"name": "Ort", "typ": "tx"},
    {"name": "IBAN", "typ": "tx", "max_len": 22},
    {"name": "Kundennummer", "typ": "tx"},
    {"name": "Bearbeiter", "typ": "tx", "nur_lesen": True},
    {"name": "Restguthaben", "typ": "cb", "tooltip": "Restguthaben überweisen"},
    {"name": "Grund", "typ": "radio", "optionen": ["Umzug", "Sonstiges"]},
    {"name": "Kontoart", "typ": "ch", "optionen": ["Girokonto", "Depot"]},
    {"name": "Datum", "typ": "tx", "eltern": "Unterschrift", "tooltip": "Ort, Datum"},
]
