"""Quellen (finder/quellen.py): Parse-Funktionen mit eingebetteten
Beispiel-Fragmenten sowie fetch_* gegen einen gefakten httpx.get - kein
echtes Netzwerk."""

from __future__ import annotations

from types import SimpleNamespace

from praemien_tracker.finder import quellen
from praemien_tracker.finder.quellen import fetch_mydealz, fetch_spartanien, parse_mydealz_rss, parse_spartanien_html

MYDEALZ_RSS_BEISPIEL = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>mydealz - Verträge &amp; Finanzen</title>
<item>
<title>C24 Bank: 125&#8364; Neukunden-Prämie für Girokonto</title>
<link>https://www.mydealz.de/gutscheine/c24-125-euro-123456</link>
<description>&lt;p&gt;Neukunden erhalten 125&#8364;, wenn sie das Konto bis 31.12. eröffnen \
und 3 Kartenzahlungen tätigen. Kein Gehaltseingang nötig.&lt;/p&gt;</description>
</item>
<item>
<title>Ohne Link - wird übersprungen</title>
<description>Fehlerhafter Eintrag</description>
</item>
</channel></rss>"""

SPARTANIEN_HTML_BEISPIEL = """
<html><body>
<div class="angebot">
  <a href="/angebot/comdirect-depot-80">Comdirect Depot 80 Euro Praemie</a>
  <p>80 Euro fuer Neukunden, Depotuebertrag noetig.</p>
</div>
<div class="angebot">
  <p>Kein Link vorhanden - wird übersprungen.</p>
</div>
</body></html>
"""


def test_mydealz_rss_wird_geparst():
    funde = parse_mydealz_rss(MYDEALZ_RSS_BEISPIEL)
    assert len(funde) == 1
    assert funde[0].quelle == "mydealz"
    assert funde[0].quelle_url == "https://www.mydealz.de/gutscheine/c24-125-euro-123456"
    assert "Gehaltseingang" in funde[0].text


def test_mydealz_rss_verkraftet_kaputtes_xml():
    assert parse_mydealz_rss("das ist kein xml") == []


def test_mydealz_rss_verkraftet_leeren_feed():
    leer = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    assert parse_mydealz_rss(leer) == []


def test_spartanien_html_wird_geparst():
    funde = parse_spartanien_html(SPARTANIEN_HTML_BEISPIEL, "https://www.spartanien.de/themen/bankprodukte/")
    assert len(funde) == 1
    assert funde[0].quelle == "spartanien"
    assert funde[0].quelle_url == "https://www.spartanien.de/angebot/comdirect-depot-80"
    assert "Depotuebertrag" in funde[0].text


def test_spartanien_html_verkraftet_unbekannte_struktur():
    """Geändertes Markup soll eine leere Liste liefern, keinen Fehler - der
    Lauf soll ohne diese Quelle weiterlaufen (siehe finder/lauf.py)."""
    assert parse_spartanien_html("<html><body><p>Nur Text, keine Angebote.</p></body></html>", "https://x") == []


class _FakeAntwort:
    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url

    def raise_for_status(self):
        pass


def test_fetch_mydealz_folgt_redirects(monkeypatch):
    """httpx folgt Redirects standardmäßig nicht - ohne follow_redirects=True
    würde raise_for_status() bei einer Weiterleitung fälschlich einen Fehler
    werfen (genau das ist bei spartanien live passiert)."""
    aufrufe = []
    monkeypatch.setattr(
        quellen.httpx,
        "get",
        lambda url, **kw: aufrufe.append((url, kw)) or _FakeAntwort("<rss></rss>", url),
    )

    fetch_mydealz("vertraege-finanzen")

    assert aufrufe[0][1]["follow_redirects"] is True


def test_fetch_spartanien_folgt_redirects_und_nutzt_ziel_url_als_basis(monkeypatch):
    """Nach einem Redirect müssen relative Links gegen die tatsächlich
    geladene (Ziel-)URL aufgelöst werden, nicht gegen die ursprünglich
    konfigurierte."""
    ziel_url = "https://www.spartanien.de/themen"
    html = '<html><body><div class="angebot"><a href="/angebot/x">X-Bank 50 Euro</a></div></body></html>'
    aufrufe = []
    monkeypatch.setattr(
        quellen.httpx,
        "get",
        lambda url, **kw: aufrufe.append((url, kw)) or _FakeAntwort(html, ziel_url),
    )

    funde = fetch_spartanien("https://www.spartanien.de/themen/bankprodukte/")

    assert aufrufe[0][1]["follow_redirects"] is True
    assert len(funde) == 1
    assert funde[0].quelle_url == "https://www.spartanien.de/angebot/x"
