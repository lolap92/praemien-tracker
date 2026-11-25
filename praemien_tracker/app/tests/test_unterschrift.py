"""Unterschrift je Inhaber (unterschrift.py) - Hochladen auf der
Inhaber-Seite und Einbetten in Druckansicht, PDF und Word
(kuendigung_dokumente.py). Die Testbilder entstehen hier synthetisch."""

from __future__ import annotations

import datetime
import io
import struct
import zipfile
import zlib

import pytest
from fastapi.testclient import TestClient

from praemien_tracker import kuendigung_dokumente as kd
from praemien_tracker import unterschrift as u
from praemien_tracker.main import app
from praemien_tracker.models import Bank, Deal, Inhaber, Kuendigungsschreiben, ProtokollEintrag

client = TestClient(app)


def _chunk(typ: bytes, inhalt: bytes) -> bytes:
    return struct.pack(">I", len(inhalt)) + typ + inhalt + struct.pack(">I", zlib.crc32(typ + inhalt))


def _png(breite, hoehe, farbtyp, zeilen_roh, filter_=0, palette=b"", trns=b""):
    """Baut ein PNG; filter_ 1 (Sub) oder 2 (Up) wird hier selbst kodiert,
    damit das Entfiltern in unterschrift.py wirklich etwas zu tun hat."""
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[farbtyp]
    roh = b""
    vorher = bytes(len(zeilen_roh[0]))
    for zeile in zeilen_roh:
        if filter_ == 1:
            kodiert = bytes((zeile[i] - (zeile[i - bpp] if i >= bpp else 0)) & 0xFF for i in range(len(zeile)))
        elif filter_ == 2:
            kodiert = bytes((zeile[i] - vorher[i]) & 0xFF for i in range(len(zeile)))
        else:
            kodiert = zeile
        roh += bytes([filter_]) + kodiert
        vorher = zeile
    teile = [_chunk(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, farbtyp, 0, 0, 0))]
    if palette:
        teile.append(_chunk(b"PLTE", palette))
    if trns:
        teile.append(_chunk(b"tRNS", trns))
    teile += [_chunk(b"IDAT", zlib.compress(roh)), _chunk(b"IEND", b"")]
    return b"\x89PNG\r\n\x1a\n" + b"".join(teile)


def _rgba_von(normalisiert: bytes) -> bytes:
    bild = u.lesen(normalisiert)
    idat = b"".join(i for t, i in u._chunks(normalisiert) if t == b"IDAT")
    roh = zlib.decompress(idat)
    z = bild.breite * 4
    return b"".join(roh[y * (z + 1) + 1 : (y + 1) * (z + 1)] for y in range(bild.hoehe))


RGBA_ZEILEN = [bytes([10, 20, 30, 255, 40, 50, 60, 0]), bytes([70, 80, 90, 128, 200, 210, 220, 255])]


@pytest.mark.parametrize("filter_", [0, 1, 2])
def test_png_rgba_wird_entfiltert(filter_):
    normal = u.normalisieren(_png(2, 2, 6, RGBA_ZEILEN, filter_))
    assert _rgba_von(normal) == b"".join(RGBA_ZEILEN)
    assert (u.lesen(normal).breite, u.lesen(normal).hoehe) == (2, 2)


def test_png_grau_und_palette_werden_rgba():
    grau = u.normalisieren(_png(2, 1, 0, [bytes([0, 255])]))
    assert _rgba_von(grau) == bytes([0, 0, 0, 255, 255, 255, 255, 255])

    palette = bytes([255, 0, 0, 0, 0, 255])
    pal = u.normalisieren(_png(2, 1, 3, [bytes([1, 0])], palette=palette, trns=bytes([0])))
    assert _rgba_von(pal) == bytes([0, 0, 255, 255, 255, 0, 0, 0])


def test_ungueltige_bilder_werden_abgelehnt():
    with pytest.raises(u.UngueltigesBild, match="PNG- oder JPEG"):
        u.normalisieren(b"GIF89a....")
    with pytest.raises(u.UngueltigesBild):
        u.normalisieren(b"")
    zu_breit = _png(u.MAX_PIXEL + 1, 1, 0, [bytes(u.MAX_PIXEL + 1)])
    with pytest.raises(u.UngueltigesBild, match="Pixel"):
        u.normalisieren(zu_breit)
    assert u.lesen(b"kaputt") is None


def test_jpeg_bleibt_unveraendert():
    # Kleinster gültiger Kopf: SOI, SOF0 mit 3x2 Pixeln und 3 Kanälen.
    jpeg = b"\xff\xd8" + b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, 2, 3, 3) + bytes(9) + b"\xff\xd9"
    assert u.normalisieren(jpeg) == jpeg
    bild = u.lesen(jpeg)
    assert (bild.format, bild.breite, bild.hoehe) == ("jpeg", 3, 2)


def _brief(unterschrift):
    return kd.Brief(["Max Muster", "Weg 1", "12345 Ort"], ["Bank AG"], "Ort", "Betreff", ["Text"], "Max Muster", unterschrift)


def test_pdf_und_word_betten_die_unterschrift_ein():
    bild = u.normalisieren(_png(2, 2, 6, RGBA_ZEILEN))
    pdf = kd.als_pdf(_brief(bild))
    assert b"/XObject << /Im1" in pdf and b"/SMask" in pdf and b"%SMASK%" not in pdf
    ohne = kd.als_pdf(_brief(None))
    assert b"/XObject" not in ohne

    docx = zipfile.ZipFile(io.BytesIO(kd.als_docx(_brief(bild))))
    assert docx.read("word/media/unterschrift.png") == bild
    assert 'r:embed="rId2"' in docx.read("word/document.xml").decode()
    assert "media/unterschrift.png" in docx.read("word/_rels/document.xml.rels").decode()
    assert "word/media/unterschrift.png" not in zipfile.ZipFile(io.BytesIO(kd.als_docx(_brief(None)))).namelist()


def test_hochladen_druckansicht_und_entfernen(db):
    inhaber = Inhaber(name="Max", voller_name="Max Muster")
    deal = Deal(kontoart="Girokonto", bank=Bank(name="Testbank"), inhaber=inhaber)
    db.add(deal)
    db.flush()
    schreiben = Kuendigungsschreiben(
        deal_id=deal.id, kanal="brief", datum=datetime.date(2026, 11, 25), absender="Max Muster", betreff="Kündigung", text="Text", name="Max Muster"
    )
    db.add(schreiben)
    db.commit()
    png = _png(2, 2, 6, RGBA_ZEILEN, 1)

    antwort = client.post(
        "/inhaber",
        files={f"unterschrift_{inhaber.id}": ("sig.png", png, "image/png")},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    db.refresh(inhaber)
    assert inhaber.unterschrift == u.normalisieren(png)
    assert "data:image/png;base64," in client.get("/inhaber").text

    brief = client.get(f"/deals/{deal.id}/kuendigung/schreiben/{schreiben.id}/druck")
    assert brief.status_code == 200 and 'class="unterschrift-bild"' in brief.text

    # Protokoll: nur dass es ein Bild gibt, nicht die Bytes.
    eintrag = db.query(ProtokollEintrag).filter_by(tabelle="Inhaber", feld="unterschrift").one()
    assert eintrag.neuer_wert.startswith("Bild (")

    # Ohne neue Datei bleibt das Bild, "entfernen" löscht es.
    client.post("/inhaber", data={f"voller_name_{inhaber.id}": "Max Muster"}, follow_redirects=False)
    db.refresh(inhaber)
    assert inhaber.unterschrift is not None
    client.post("/inhaber", data={f"unterschrift_loeschen_{inhaber.id}": "on"}, follow_redirects=False)
    db.refresh(inhaber)
    assert inhaber.unterschrift is None


def test_unbrauchbares_bild_zeigt_fehler_und_speichert_den_rest(db):
    inhaber = Inhaber(name="Elli")
    db.add(inhaber)
    db.commit()
    antwort = client.post(
        "/inhaber",
        data={f"ort_{inhaber.id}": "Breuberg"},
        files={f"unterschrift_{inhaber.id}": ("sig.gif", b"GIF89a", "image/gif")},
    )
    assert antwort.status_code == 400
    assert "Unterschrift für Elli" in antwort.text
    db.refresh(inhaber)
    assert inhaber.ort == "Breuberg" and inhaber.unterschrift is None


def test_unterschrift_per_json_setzen_laesst_den_rest_unberuehrt(db):
    import base64

    kind = Inhaber(name="Finn", ist_minderjaehrig=True)
    elli = Inhaber(name="Elli")
    db.add_all([kind, elli])
    db.commit()
    png = _png(2, 2, 6, RGBA_ZEILEN, 2)

    antwort = client.post(f"/inhaber/{elli.id}/unterschrift", json={"bild_base64": base64.b64encode(png).decode()})
    assert antwort.status_code == 200
    assert antwort.json() == {"inhaber": "Elli", "unterschrift_hinterlegt": True, "breite": 2, "hoehe": 2}
    db.refresh(elli)
    db.refresh(kind)
    assert elli.unterschrift == u.normalisieren(png)
    assert kind.ist_minderjaehrig is True

    # Auch als data-URI, Fehler und Entfernen
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    assert client.post(f"/inhaber/{elli.id}/unterschrift", json={"bild_base64": uri}).status_code == 200
    assert client.post(f"/inhaber/{elli.id}/unterschrift", json={"bild_base64": "!!"}).status_code == 400
    assert client.post(f"/inhaber/{elli.id}/unterschrift", json={"bild_base64": "R0lGODlh"}).status_code == 400
    assert client.post("/inhaber/9999/unterschrift", json={"bild_base64": ""}).status_code == 404
    assert client.post(f"/inhaber/{elli.id}/unterschrift", json={"bild_base64": ""}).json()["unterschrift_hinterlegt"] is False
