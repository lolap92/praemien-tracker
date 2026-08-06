"""Reine Parse-Funktionen der Quellen (finder/quellen.py) - ohne Netzwerk,
mit eingebetteten Beispiel-Fragmenten."""

from __future__ import annotations

from praemien_tracker.finder.quellen import parse_mydealz_rss, parse_spartanien_html

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
