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


def test_mydealz_rss_dedupliziert_denselben_link():
    """Der Feed listet einen Deal gelegentlich doppelt (z.B. nach einem
    Bump) - ohne Deduplizierung nach Link bricht taeglicher_lauf() mit
    einem IntegrityError ab, weil quelle_url in finder_funde eindeutig ist."""
    doppelt = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>mydealz</title>
<item>
<title>C24 Bank: 125&#8364; Neukunden-Praemie</title>
<link>https://www.mydealz.de/gutscheine/c24-125-euro-123456</link>
<description>Erster Eintrag</description>
</item>
<item>
<title>C24 Bank: 125&#8364; Neukunden-Praemie (erneut gebumpt)</title>
<link>https://www.mydealz.de/gutscheine/c24-125-euro-123456</link>
<description>Zweiter Eintrag, gleicher Link</description>
</item>
</channel></rss>"""
    funde = parse_mydealz_rss(doppelt)
    assert len(funde) == 1
    assert funde[0].quelle_url == "https://www.mydealz.de/gutscheine/c24-125-euro-123456"
    assert "Erster Eintrag" in funde[0].text


def test_spartanien_html_wird_geparst():
    funde = parse_spartanien_html(SPARTANIEN_HTML_BEISPIEL, "https://www.spartanien.de/themen/bankprodukte/")
    assert len(funde) == 1
    assert funde[0].quelle == "spartanien"
    assert funde[0].quelle_url == "https://www.spartanien.de/angebot/comdirect-depot-80"
    assert "Depotuebertrag" in funde[0].text


SPARTANIEN_HTML_ECHT = """
<article class="Finanzen  " id="aktion394" data-id="394" itemscope="" itemtype="http://schema.org/LocalBusiness">
  <a name="394"></a>
  <a title="Link zum Deal Santander BestGiro" href="https://www.spartanien.de/Santander+BestGiro"></a>
  <section>
    <header>
      <a href="https://www.spartanien.de/Santander+BestGiro" style="text-decoration:none">
        <h3 itemprop="name">Santander BestGiro</h3>
      </a>
    </header>
    <p class="description" itemprop="description">
      Eroeffne das kostenlose Santander BestGiro Girokonto und sichere dir 50 EUR von Spartanien
      fuer die reine kostenlose Kontoeroeffnung. Zusaetzlich gibt es 250 EUR Bonus von der Santander!
    </p>
    <a href="https://www.spartanien.de/Santander+BestGiro">
      <figure><div class="voucher"><strong>50 EUR</strong></div></figure>
    </a>
  </section>
</article>
"""


def test_spartanien_html_wird_geparst_mit_echter_kartenstruktur():
    """Regressionstest fuer den realen Aufbau: jede Karte verlinkt zuerst
    ueber einen unsichtbaren Anker ganz ohne Text - vor der Korrektur wurde
    dieser als Titel-Link genommen, was jede Karte mangels Titel
    uebersprungen hat (0 Funde im echten Betrieb)."""
    funde = parse_spartanien_html(SPARTANIEN_HTML_ECHT, "https://www.spartanien.de/themen")
    assert len(funde) == 1
    assert funde[0].quelle_url == "https://www.spartanien.de/Santander+BestGiro"
    assert funde[0].titel == "Santander BestGiro"
    assert "Santander BestGiro" in funde[0].text
    assert "250 EUR" in funde[0].text


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
