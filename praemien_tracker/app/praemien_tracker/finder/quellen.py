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

    Ohne offiziellen Feed ist die Struktur eine Annahme über gängige
    Auszeichnung (Artikel-/Karten-Elemente mit einem Link). Passt keiner der
    Selektoren, liefert die Funktion bewusst eine leere Liste statt eines
    Fehlers - ein geändertes Markup soll den ganzen Lauf nicht zum Absturz
    bringen, sondern nur diese eine Quelle für den Tag leer lassen. Der
    tatsächliche Aufbau der Seite sollte nach der ersten Einrichtung geprüft
    und die Selektoren bei Bedarf angepasst werden.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    kandidaten = soup.select("article, .angebot, .deal, [data-angebot], li.list-item")

    funde: list[RohFund] = []
    gesehene_urls: set[str] = set()
    for eintrag in kandidaten:
        link_tag = eintrag.find("a", href=True)
        if link_tag is None:
            continue
        link = str(httpx.URL(basis_url).join(link_tag["href"]))
        if link in gesehene_urls:
            continue
        titel = link_tag.get_text(" ", strip=True)
        text = eintrag.get_text(" ", strip=True)
        if not titel or not text:
            continue
        gesehene_urls.add(link)
        funde.append(RohFund(quelle="spartanien", quelle_url=link, titel=titel, text=text))

    if not funde:
        logger.warning("spartanien-HTML lieferte keine erkennbaren Angebote - Struktur geändert?")
    return funde


def fetch_spartanien(url: str, *, timeout: float = 15.0) -> list[RohFund]:
    antwort = httpx.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    antwort.raise_for_status()
    return parse_spartanien_html(antwort.text, str(antwort.url))
