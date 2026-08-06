"""Rohtext von den beiden Quellen holen - ohne jede Fachlogik.

mydealz läuft über den offiziellen RSS-Feed pro Gruppe (dokumentierter Weg,
kein Scraping-Risiko). spartanien hat keinen bekannten Feed; dort wird die
Angebotsliste per HTML geparst - bewusst so tolerant gebaut, dass ein
geändertes Markup zu einer leeren Liste statt zu einem Absturz des ganzen
Laufs führt (siehe fetch_spartanien).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("praemien_tracker.finder")

USER_AGENT = "praemien-tracker/1 (privater Gebrauch, siehe github.com/lolap92/praemien-tracker)"
MYDEALZ_RSS_URL = "https://www.mydealz.de/rss/gruppe/{gruppe}"


@dataclass(frozen=True)
class RohFund:
    """Ein ungeprüfter Fund, roher Text für die KI-Extraktion (extraktion.py)."""

    quelle: str  # "mydealz" | "spartanien"
    quelle_url: str
    titel: str
    text: str


def parse_mydealz_rss(xml_text: str) -> list[RohFund]:
    """RSS-Items in RohFund-Objekte übersetzen.

    Jedes Item liefert Titel, Link und eine HTML-Beschreibung - aus der
    Beschreibung wird der reine Text extrahiert (Tags entfernt), da die
    KI-Extraktion mit Fließtext arbeitet, nicht mit Markup.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("mydealz-RSS-Feed ließ sich nicht als XML lesen - Struktur geändert?")
        return []

    funde: list[RohFund] = []
    for item in root.iter("item"):
        titel = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        beschreibung_html = item.findtext("description") or ""
        text = BeautifulSoup(beschreibung_html, "html.parser").get_text(" ", strip=True)
        if not link or not titel:
            continue
        funde.append(RohFund(quelle="mydealz", quelle_url=link, titel=titel, text=text or titel))
    return funde


def fetch_mydealz(gruppe: str, *, timeout: float = 15.0) -> list[RohFund]:
    url = MYDEALZ_RSS_URL.format(gruppe=gruppe)
    antwort = httpx.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    antwort.raise_for_status()
    return parse_mydealz_rss(antwort.text)


def parse_spartanien_html(html_text: str, basis_url: str) -> list[RohFund]:
    """Angebotsliste in RohFund-Objekte übersetzen.

    Jede Karte ist ein `<article itemtype="http://schema.org/LocalBusiness">`
    (schema.org-Microdata, an echtem Markup verifiziert) - deutlich
    zuverlässiger als eine Rate-Auswahl über generische Klassen. Passt dieser
    Selektor nicht mehr (Markup erneut geändert), fällt die Funktion auf
    tolerante generische Selektoren zurück statt mit einem Fehler
    abzubrechen - eine leere Liste lässt nur diese eine Quelle für den Tag
    leer, statt den ganzen Lauf zu stoppen.

    Jede Karte verlinkt zusätzlich über einen unsichtbaren Anker ganz ohne
    Text (nur ein "title"-Attribut) direkt vor dem eigentlichen Titel-Link -
    der erste `<a href>` ist deshalb nicht zuverlässig der richtige; genommen
    wird stattdessen der erste Link mit sichtbarem Text.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    kandidaten = soup.select('article[itemtype="http://schema.org/LocalBusiness"]')
    if not kandidaten:
        kandidaten = soup.select("article, .angebot, .deal, [data-angebot], li.list-item")

    funde: list[RohFund] = []
    gesehene_urls: set[str] = set()
    for eintrag in kandidaten:
        link_tag = next((a for a in eintrag.find_all("a", href=True) if a.get_text(strip=True)), None)
        if link_tag is None:
            continue
        link = str(httpx.URL(basis_url).join(link_tag["href"]))
        if link in gesehene_urls:
            continue

        titel_tag = eintrag.select_one('[itemprop="name"]') or eintrag.find(["h2", "h3", "h4"])
        titel = (titel_tag.get_text(" ", strip=True) if titel_tag else "") or link_tag.get_text(" ", strip=True)
        beschreibung_tag = eintrag.select_one('.description, [itemprop="description"]')
        beschreibung = (
            beschreibung_tag.get_text(" ", strip=True) if beschreibung_tag else eintrag.get_text(" ", strip=True)
        )
        if not titel or not beschreibung:
            continue

        gesehene_urls.add(link)
        text = beschreibung if beschreibung.startswith(titel) else f"{titel}. {beschreibung}"
        funde.append(RohFund(quelle="spartanien", quelle_url=link, titel=titel, text=text))

    if not funde:
        logger.warning("spartanien-HTML lieferte keine erkennbaren Angebote - Struktur geändert?")
    return funde


def fetch_spartanien(url: str, *, timeout: float = 15.0) -> list[RohFund]:
    antwort = httpx.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    antwort.raise_for_status()
    return parse_spartanien_html(antwort.text, str(antwort.url))
