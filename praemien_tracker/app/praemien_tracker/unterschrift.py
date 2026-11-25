"""Eingescannte Unterschrift je Inhaber für den Kündigungsbrief
(kuendigung_dokumente.py, templates/kuendigung_brief.html).

Wie bei PDF und Word ohne Pillow (siehe kuendigung_dokumente.py, armv7):
Angenommen werden PNG und JPEG, nur mit der Standardbibliothek gelesen.

- JPEG wird unverändert gespeichert - PDF (DCTDecode), Word und Browser
  können es direkt einbetten.
- PNG wird beim Hochladen einmal entpackt und als RGBA-PNG ohne
  Zeilenfilter neu geschrieben. Das ist weiterhin ein gültiges PNG für
  Browser und Word, lässt sich fürs PDF aber ohne erneutes Entfiltern in
  Farbe und Transparenz (SMask) aufteilen - das Entfiltern in reinem Python
  ist der langsame Teil und passiert so nur einmal beim Hochladen.
"""

from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXEL = 2000

_PNG_SIGNATUR = b"\x89PNG\r\n\x1a\n"

# Farbtyp -> Kanäle bei 8 Bit (0 Grau, 2 RGB, 3 Palette, 4 Grau+Alpha, 6 RGBA)
_KANAELE = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class UngueltigesBild(ValueError):
    pass


@dataclass
class Bild:
    format: str  # "png" (immer RGBA ohne Filter) oder "jpeg"
    breite: int
    hoehe: int
    daten: bytes
    jpeg_kanaele: int = 3

    @property
    def mime(self) -> str:
        return "image/png" if self.format == "png" else "image/jpeg"

    @property
    def data_uri(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.daten).decode()}"


# ------------------------------------------------------------- Einlesen ----


def normalisieren(daten: bytes) -> bytes:
    """Prüft ein hochgeladenes Bild und liefert die zu speichernden Bytes.
    Wirft UngueltigesBild mit einer Meldung für die Oberfläche."""
    if not daten:
        raise UngueltigesBild("Die Datei ist leer.")
    if len(daten) > MAX_BYTES:
        raise UngueltigesBild("Das Bild ist größer als 2 MB - bitte verkleinern oder zuschneiden.")
    if daten.startswith(_PNG_SIGNATUR):
        breite, hoehe, rgba = _png_entpacken(daten)
        _groesse_pruefen(breite, hoehe)
        return _png_schreiben(breite, hoehe, rgba)
    if daten.startswith(b"\xff\xd8"):
        breite, hoehe, _ = _jpeg_kopf(daten)
        _groesse_pruefen(breite, hoehe)
        return daten
    raise UngueltigesBild("Bitte ein PNG- oder JPEG-Bild hochladen.")


def lesen(daten: bytes | None) -> Bild | None:
    """Gespeicherte (normalisierte) Bytes -> Bild, ohne erneute Prüfung der
    Pixel. Kaputte Daten ergeben None statt eines Fehlers im Brief."""
    if not daten:
        return None
    try:
        if daten.startswith(_PNG_SIGNATUR):
            breite, hoehe = struct.unpack(">II", daten[16:24])
            return Bild("png", breite, hoehe, daten)
        if daten.startswith(b"\xff\xd8"):
            breite, hoehe, kanaele = _jpeg_kopf(daten)
            return Bild("jpeg", breite, hoehe, daten, kanaele)
    except (UngueltigesBild, struct.error):
        return None
    return None


def _groesse_pruefen(breite: int, hoehe: int) -> None:
    if not breite or not hoehe:
        raise UngueltigesBild("Das Bild hat keine Abmessungen.")
    if breite > MAX_PIXEL or hoehe > MAX_PIXEL:
        raise UngueltigesBild(f"Das Bild ist größer als {MAX_PIXEL} Pixel - bitte verkleinern oder zuschneiden.")


def _chunks(daten: bytes):
    pos = len(_PNG_SIGNATUR)
    while pos + 8 <= len(daten):
        laenge, typ = struct.unpack(">I4s", daten[pos : pos + 8])
        inhalt = daten[pos + 8 : pos + 8 + laenge]
        if len(inhalt) != laenge:
            raise UngueltigesBild("Die PNG-Datei ist unvollständig.")
        yield typ, inhalt
        if typ == b"IEND":
            return
        pos += 12 + laenge


def _png_entpacken(daten: bytes) -> tuple[int, int, bytes]:
    kopf = None
    palette = b""
    transparenz = b""
    idat = []
    for typ, inhalt in _chunks(daten):
        if typ == b"IHDR":
            kopf = struct.unpack(">IIBBBBB", inhalt)
        elif typ == b"PLTE":
            palette = inhalt
        elif typ == b"tRNS":
            transparenz = inhalt
        elif typ == b"IDAT":
            idat.append(inhalt)
    if kopf is None or not idat:
        raise UngueltigesBild("Die PNG-Datei ist unvollständig.")
    breite, hoehe, tiefe, farbtyp, _, _, interlace = kopf
    if tiefe != 8 or farbtyp not in _KANAELE or interlace:
        raise UngueltigesBild(
            "Dieses PNG-Format wird nicht unterstützt (nur 8 Bit, ohne Interlacing) - "
            "bitte als normales PNG oder JPEG speichern."
        )
    _groesse_pruefen(breite, hoehe)
    try:
        roh = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise UngueltigesBild("Die PNG-Datei ist beschädigt.") from exc

    bpp = _KANAELE[farbtyp]
    zeile_len = breite * bpp
    if len(roh) < hoehe * (zeile_len + 1):
        raise UngueltigesBild("Die PNG-Datei ist unvollständig.")
    pixel = bytearray(hoehe * zeile_len)
    vorher = bytearray(zeile_len)
    for y in range(hoehe):
        start = y * (zeile_len + 1)
        filter_ = roh[start]
        zeile = bytearray(roh[start + 1 : start + 1 + zeile_len])
        _entfiltern(filter_, zeile, vorher, bpp)
        pixel[y * zeile_len : (y + 1) * zeile_len] = zeile
        vorher = zeile
    return breite, hoehe, _als_rgba(bytes(pixel), farbtyp, palette, transparenz)


def _entfiltern(filter_: int, zeile: bytearray, vorher: bytearray, bpp: int) -> None:
    n = len(zeile)
    if filter_ == 0:
        return
    if filter_ == 1:
        for i in range(bpp, n):
            zeile[i] = (zeile[i] + zeile[i - bpp]) & 0xFF
    elif filter_ == 2:
        for i in range(n):
            zeile[i] = (zeile[i] + vorher[i]) & 0xFF
    elif filter_ == 3:
        for i in range(n):
            links = zeile[i - bpp] if i >= bpp else 0
            zeile[i] = (zeile[i] + ((links + vorher[i]) >> 1)) & 0xFF
    elif filter_ == 4:
        for i in range(n):
            a = zeile[i - bpp] if i >= bpp else 0
            b = vorher[i]
            c = vorher[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            zeile[i] = (zeile[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
    else:
        raise UngueltigesBild("Die PNG-Datei ist beschädigt.")


def _als_rgba(pixel: bytes, farbtyp: int, palette: bytes, transparenz: bytes) -> bytes:
    if farbtyp == 6:
        return pixel
    anzahl = len(pixel) // _KANAELE[farbtyp]
    rgba = bytearray(b"\xff" * (anzahl * 4))
    if farbtyp == 2:
        for k in range(3):
            rgba[k::4] = pixel[k::3]
    elif farbtyp == 0:
        for k in range(3):
            rgba[k::4] = pixel
    elif farbtyp == 4:
        for k in range(3):
            rgba[k::4] = pixel[0::2]
        rgba[3::4] = pixel[1::2]
    elif farbtyp == 3:
        if not palette:
            raise UngueltigesBild("Die PNG-Datei ist unvollständig.")
        eintraege = [
            palette[i * 3 : i * 3 + 3] + (bytes([transparenz[i]]) if i < len(transparenz) else b"\xff")
            for i in range(256)
        ]
        eintraege = [e if len(e) == 4 else b"\x00\x00\x00\xff" for e in eintraege]
        rgba = bytearray(b"".join(eintraege[i] for i in pixel))
    return bytes(rgba)


def _png_schreiben(breite: int, hoehe: int, rgba: bytes) -> bytes:
    zeile_len = breite * 4
    roh = b"".join(b"\x00" + rgba[y * zeile_len : (y + 1) * zeile_len] for y in range(hoehe))

    def chunk(typ: bytes, inhalt: bytes) -> bytes:
        return struct.pack(">I", len(inhalt)) + typ + inhalt + struct.pack(">I", zlib.crc32(typ + inhalt))

    return (
        _PNG_SIGNATUR
        + chunk(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(roh, 9))
        + chunk(b"IEND", b"")
    )


def _jpeg_kopf(daten: bytes) -> tuple[int, int, int]:
    """Breite, Höhe und Kanäle aus dem SOF-Segment."""
    pos = 2
    while pos + 4 <= len(daten):
        if daten[pos] != 0xFF:
            raise UngueltigesBild("Die JPEG-Datei ist beschädigt.")
        marker = daten[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        (laenge,) = struct.unpack(">H", daten[pos + 2 : pos + 4])
        if marker in (0xC0, 0xC1, 0xC2) and pos + 10 <= len(daten):
            hoehe, breite = struct.unpack(">HH", daten[pos + 5 : pos + 9])
            kanaele = daten[pos + 9]
            if kanaele not in (1, 3):
                raise UngueltigesBild("CMYK-JPEGs werden nicht unterstützt - bitte als PNG oder RGB-JPEG speichern.")
            return breite, hoehe, kanaele
        if 0xC3 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            raise UngueltigesBild("Dieses JPEG-Format wird nicht unterstützt - bitte als PNG speichern.")
        pos += 2 + laenge
    raise UngueltigesBild("Die JPEG-Datei ist beschädigt.")


# ------------------------------------------------------------------ PDF ----


def pdf_teile(bild: Bild) -> tuple[bytes, bytes | None]:
    """(Bild-XObject, SMask-XObject oder None) als fertige PDF-Objekte. Im
    Bild-Objekt steht "%SMASK%" als Platzhalter für den Verweis auf die
    Maske, weil deren Objektnummer erst beim Zusammensetzen feststeht."""
    if bild.format == "jpeg":
        farbraum = b"/DeviceGray" if bild.jpeg_kanaele == 1 else b"/DeviceRGB"
        kopf = b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 " % (
            bild.breite,
            bild.hoehe,
            farbraum,
        )
        return kopf + b"/Filter /DCTDecode /Length %d >>\nstream\n" % len(bild.daten) + bild.daten + b"\nendstream", None

    idat = b"".join(inhalt for typ, inhalt in _chunks(bild.daten) if typ == b"IDAT")
    roh = zlib.decompress(idat)
    zeile_len = bild.breite * 4
    # Filterbyte je Zeile abschneiden (normalisiert ist es immer 0).
    rgba = b"".join(roh[y * (zeile_len + 1) + 1 : (y + 1) * (zeile_len + 1)] for y in range(bild.hoehe))
    rgb = bytearray(len(rgba) // 4 * 3)
    for k in range(3):
        rgb[k::3] = rgba[k::4]
    alpha = rgba[3::4]

    def objekt(daten: bytes, farbraum: bytes, extra: bytes = b"") -> bytes:
        gepackt = zlib.compress(bytes(daten), 9)
        return (
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 %s"
            b"/Filter /FlateDecode /Length %d >>\nstream\n" % (bild.breite, bild.hoehe, farbraum, extra, len(gepackt))
            + gepackt
            + b"\nendstream"
        )

    return objekt(rgb, b"/DeviceRGB", b"/SMask %SMASK% "), objekt(alpha, b"/DeviceGray")


def masse_mm(bild: Bild, max_breite_mm: float, max_hoehe_mm: float) -> tuple[float, float]:
    """Größe im Brief: so groß wie möglich innerhalb des Rahmens, mit
    erhaltenem Seitenverhältnis."""
    faktor = min(max_breite_mm / bild.breite, max_hoehe_mm / bild.hoehe)
    return bild.breite * faktor, bild.hoehe * faktor
