from __future__ import annotations

import datetime
import json
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from . import kuendigung_recherche, kwk_recherche
from .config import DEMO_MODUS
from .derived import bank_name_normalisieren, format_monat, parse_monat
from .kuendigung_hinweise import hinweis_fuer
from .models import Aufgabe, Bank, Bedingung, Deal, DealUrl, Inhaber, Praemie
from .schemas import DealImport


def parse_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def freibetrag_jahr_bestimmen(jahr: int | None, betrag: Decimal | None) -> int | None:
    """Ohne Jahresangabe fällt ein gesetzter Freibetrag-Betrag auf das
    laufende Jahr - sonst erscheint er in keiner der beiden Jahresspalten der
    Freibetrag-Übersicht (statistiken.py) und ist praktisch unsichtbar. Ohne
    Betrag bleibt eine (unwahrscheinliche) Jahresangabe ohne Betrag einfach
    stehen, ohne Auswirkung.

    Gemeinsam genutzt von der Bearbeiten-Seite (routers/deals.py) und
    build_deal_from_import() - jede Stelle, die freibetrag setzt, muss auch
    freibetrag_jahr danach bestimmen, sonst entsteht genau diese Lücke."""
    if betrag is None:
        return jahr
    return jahr or datetime.date.today().year


def monat_aus_formular(wert: str | None) -> str | None:
    """Monatsangabe aus dem Formular auf ISO bringen. Nicht lesbare Eingaben
    werden unverändert übernommen, damit die Eingabe des Nutzers nicht
    verschwindet - sie fällt dann in "Zu prüfen" bzw. in der
    Sperrfristen-Liste auf."""
    if wert is None or not wert.strip():
        return None
    datum = parse_monat(wert)
    return format_monat(datum) if datum else wert.strip()


def kuendigung_vorschlag(db: Session, deal: Deal) -> None:
    """Fest hinterlegten Kündigungsweg (KUENDIGUNG_HINWEISE) als Vorschlag
    setzen, falls einer für Bank und Kontoart existiert und der Deal noch
    keinen eigenen trägt - reiner, kostenloser Tabellen-Lookup, keine
    KI-Websuche mehr (siehe kuendigung_recherche.naechtlicher_lauf für die,
    die stattdessen nachts läuft).

    Wird nur beim Anlegen aufgerufen. Danach gehört das Feld dem Nutzer -
    ein geleertes oder überschriebenes Feld bleibt so, wie der Nutzer es
    haben möchte (siehe deal_update()/deal_kuendigung_hinweis_update()); der
    nächtliche Batch überschreibt aus demselben Grund nur Deals, die noch
    gar keinen Hinweis haben.

    `db` bleibt ungenutzt (kein Cache-Zugriff mehr nötig) - der Parameter ist
    nur da, damit die Funktion wie kwk_vorschlag() aus build_deal_from_import
    aufgerufen werden kann, ohne dass der Aufrufer wissen muss, welche der
    beiden einen DB-Zugriff braucht.

    Im Demo-Modus komplett übersprungen, da die Bank ohnehin frei erfunden
    ist und die feste Tabelle dafür nichts liefert."""
    if DEMO_MODUS or deal.kuendigung_hinweis or deal.bank is None:
        return
    eintrag = hinweis_fuer(deal.bank.name, deal.kontoart)
    if eintrag:
        deal.kuendigung_hinweis, deal.kuendigung_hinweis_url = eintrag


def kwk_vorschlag(db: Session, deal: Deal) -> bool:
    """Prüft beim Anlegen eines Deals per KI-Websuche, ob die Bank für diese
    Kontoart ein "Kunden wirbt Kunden"-Programm anbietet, und legt bei Erfolg
    automatisch eine Aufgabe mit Link zur zugehörigen Seite der Bank an.

    Bewusst ohne Cache (anders als kuendigung_vorschlag, siehe
    kwk_recherche.py): ein KwK-Programm ist oft eine befristete
    Marketing-Aktion, die sich häufiger ändert als ein Kündigungsweg - dafür
    läuft die Recherche auch nur hier, beim einmaligen Anlegen des Deals,
    nicht im täglichen KI-Deal-Finder-Lauf (dort gäbe es ohne Cache keinen
    Schutz vor wiederholten Aufrufen für dieselbe Bank).

    Liefert True, wenn die Recherche fehlgeschlagen ist (API-Fehler oder kein
    auswertbares Ergebnis) - der Aufrufer (build_deal_from_import) reicht das
    bis zum Übernehmen-Endpunkt durch, der den Nutzer dann auf eine manuelle
    Prüfung hinweist. Das Anlegen des Deals selbst schlägt dadurch nie fehl -
    die Prüfung ist eine reine, nicht blockierende Ergänzung.

    `db` bleibt ungenutzt (kein Cache-Zugriff nötig) - der Parameter ist nur
    da, damit die Funktion wie kuendigung_vorschlag() aus build_deal_from_import
    aufgerufen werden kann, ohne dass der Aufrufer wissen muss, welche der
    beiden einen DB-Zugriff braucht.

    Im Demo-Modus komplett übersprungen, siehe kuendigung_vorschlag()."""
    if DEMO_MODUS or deal.bank is None:
        return False
    url, fehlgeschlagen = kwk_recherche.moeglichkeit_recherchieren(deal.bank.name, deal.kontoart)
    if url:
        deal.urls.append(DealUrl(url=url, bezeichnung="Kunden wirbt Kunden"))
        deal.aufgaben.append(
            Aufgabe(
                beschreibung=(
                    f"Kunden wirbt Kunden bei {deal.bank.name} nutzen: Freund/in werben, "
                    f"zusätzliche Prämie sichern - {url}"
                )[:255]
            )
        )
    return fehlgeschlagen


KWK_FALLBACK_AUFGABE_TEXT = "KwK möglich? Kunden-wirbt-Kunden-Programm manuell prüfen."


SPARTANIEN_AUFGABE_TEXT = "Spartanien Tracking überprüfen"


def spartanien_aufgabe_sicherstellen(deal: Deal) -> None:
    """Legt die Aufgabe "Spartanien Tracking überprüfen" an, sobald der Deal
    (mindestens) eine Prämie mit Quelle "spartanien" trägt - Spartanien zahlt
    unabhängig von der Bank aus und will separat im Blick behalten werden.

    Dedupliziert über den exakten Aufgabentext: unabhängig davon, wie oft
    diese Funktion für denselben Deal aufgerufen wird (Anlage, jede weitere
    Prämie), entsteht die Aufgabe nur einmal."""
    if not any(p.quelle == "spartanien" for p in deal.praemien):
        return
    if any(a.beschreibung == SPARTANIEN_AUFGABE_TEXT for a in deal.aufgaben):
        return
    deal.aufgaben.append(Aufgabe(beschreibung=SPARTANIEN_AUFGABE_TEXT))


# Sekunden, die routers/vorschlaege.uebernehmen_bestaetigen höchstens auf die
# beim Öffnen der Vorschau (uebernehmen_vorschau) im Hintergrund gestartete
# KwK-Recherche wartet - siehe kwk_recherche_vorab_starten/kwk_ergebnis_anwenden.
# Kurz genug, um "Übernehmen" nie spürbar zu blockieren, aber lang genug, um
# eine ohnehin meist längst fertige Recherche noch mitzunehmen.
KWK_TIMEOUT_SEKUNDEN = 2.0


def kwk_recherche_vorab_starten(bank_name: str, kontoart: str) -> str:
    """Stößt die KwK-Recherche schon beim Öffnen der Übernehmen-Vorschau im
    Hintergrund an (kwk_recherche.hintergrund_starten), statt sie wie früher
    erst beim tatsächlichen Anlegen synchron auszuführen - dort hing
    "Übernehmen" spürbar, siehe kwk_ergebnis_anwenden(). Die Zeit, die der
    Nutzer mit der Vorschau verbringt, überbrückt die KI-Websuche im
    Hintergrund. Liefert den Dedup-Schlüssel für
    kwk_recherche_ergebnis_abholen(); im Demo-Modus wird kein Thread
    gestartet, siehe kwk_vorschlag()."""
    schluessel = f"{bank_name_normalisieren(bank_name)}|{kontoart.strip().lower()}"
    if not DEMO_MODUS:
        kwk_recherche.hintergrund_starten(schluessel, bank_name, kontoart)
    return schluessel


def kwk_recherche_ergebnis_abholen(schluessel: str, timeout: float) -> tuple[str | None, bool] | None:
    """Holt das Ergebnis einer mit kwk_recherche_vorab_starten() gestarteten
    Recherche ab, siehe kwk_recherche.ergebnis_abholen(). Im Demo-Modus oder
    ohne Schlüssel (z.B. Direktaufruf ohne vorherige Vorschau) immer None."""
    if DEMO_MODUS or not schluessel:
        return None
    return kwk_recherche.ergebnis_abholen(schluessel, timeout)


def kwk_ergebnis_anwenden(deal: Deal, ergebnis: tuple[str | None, bool] | None) -> None:
    """Wertet ein per kwk_recherche_vorab_starten()/kwk_recherche_ergebnis_abholen()
    vorab im Hintergrund ermitteltes KwK-Rechercheergebnis aus. Bei Erfolg wie
    kwk_vorschlag(): URL + Aufgabe mit dem gefundenen Programm. Liegt (noch)
    kein Ergebnis vor (Timeout) oder ist die Recherche fehlgeschlagen, gibt es
    - anders als früher der reine Hinweis-Banner nach dem Übernehmen - direkt
    eine einfache Erinnerungs-Aufgabe: der Nutzer bekommt so in jedem Fall
    eine konkrete, nicht mehr wegklickbare Handlung statt eines Hinweistexts.

    Im Demo-Modus / ohne Bank passiert nichts, siehe kwk_vorschlag()."""
    if DEMO_MODUS or deal.bank is None:
        return
    if ergebnis is None or ergebnis[1]:
        deal.aufgaben.append(Aufgabe(beschreibung=KWK_FALLBACK_AUFGABE_TEXT))
        return
    url, _fehlgeschlagen = ergebnis
    if url:
        deal.urls.append(DealUrl(url=url, bezeichnung="Kunden wirbt Kunden"))
        deal.aufgaben.append(
            Aufgabe(
                beschreibung=(
                    f"Kunden wirbt Kunden bei {deal.bank.name} nutzen: Freund/in werben, "
                    f"zusätzliche Prämie sichern - {url}"
                )[:255]
            )
        )


def get_or_create_bank(db: Session, name: str) -> Bank:
    """Bank per Name finden oder neu anlegen - der Abgleich ignoriert Groß-/
    Kleinschreibung, Leerzeichen und Interpunktion (z.B. "SMARTBROKER" ==
    "Smart Broker"), sonst entstünde beim Übernehmen eines Vorschlags mit
    leicht abweichender Schreibweise ein doppelter Bank-Datensatz für
    dieselbe Bank."""
    name = name.strip()
    ziel = bank_name_normalisieren(name)
    bank = next((b for b in db.query(Bank).all() if bank_name_normalisieren(b.name) == ziel), None)
    if bank is None:
        bank = Bank(name=name)
        db.add(bank)
        db.flush()
    return bank


def get_or_create_inhaber(db: Session, name: str) -> Inhaber:
    name = name.strip()
    inhaber = db.query(Inhaber).filter(Inhaber.name == name).one_or_none()
    if inhaber is None:
        inhaber = Inhaber(name=name)
        db.add(inhaber)
        db.flush()
    return inhaber


def _leer_zu_none(wert: str | None) -> str | None:
    """Randleerzeichen entfernen, Leerstrings zu None - damit der Importpfad
    dieselben Werte erzeugt wie der Formularpfad."""
    if wert is None:
        return None
    return wert.strip() or None


def build_deal_from_import(db: Session, daten: DealImport, *, hintergrund_recherche: bool = False) -> Deal:
    """Legt einen Deal inkl. Prämien/Bedingungen/Aufgaben/Links aus validierten
    JSON-Importdaten an.

    `hintergrund_recherche`: True, wenn der Aufrufer die KwK-Recherche selbst
    übernimmt (siehe helpers.kwk_ergebnis_anwenden) - z.B. weil mehrere Deals
    aus demselben Übernehmen-Vorgang (routers/vorschlaege.
    uebernehmen_bestaetigen) dieselbe, schon vorab im Hintergrund gestartete
    Recherche teilen sollen, statt sie hier pro Deal erneut synchron
    auszulösen. Der Kündigungsweg-Lookup (kuendigung_vorschlag) läuft davon
    unabhängig immer - er ist reiner Tabellen-Lookup, keine KI-Websuche."""
    deal = Deal(
        bank=get_or_create_bank(db, daten.bank),
        inhaber=get_or_create_inhaber(db, daten.inhaber),
        kontoart=daten.kontoart.strip(),
        kontonummer=_leer_zu_none(daten.kontonummer),
        kuendbar_ab=daten.kuendbar_ab,
        gekuendigt=daten.gekuendigt,
        gekuendigt_im_monat=_leer_zu_none(daten.gekuendigt_im_monat),
        kuendigung_bestaetigt=daten.kuendigung_bestaetigt,
        kuendigung_hinweis=_leer_zu_none(daten.kuendigung_hinweis),
        kuendigung_hinweis_url=_leer_zu_none(daten.kuendigung_hinweis_url),
        freibetrag=daten.freibetrag,
        freibetrag_jahr=freibetrag_jahr_bestimmen(daten.freibetrag_jahr, daten.freibetrag),
        praemien_auf_sparkonto=daten.praemien_auf_sparkonto,
        kommentar=_leer_zu_none(daten.kommentar),
        zugangsdaten_gespeichert=daten.zugangsdaten_gespeichert,
    )
    if daten.uebersprungene_felder:
        deal.uebersprungene_felder = json.dumps(sorted(set(daten.uebersprungene_felder)))
    for p in daten.praemien:
        deal.praemien.append(
            Praemie(
                quelle=p.quelle,
                betrag=p.betrag,
                erhalten=p.erhalten,
                auszahlung_erwartet=_leer_zu_none(p.auszahlung_erwartet),
            )
        )
    for b in daten.bedingungen:
        deal.bedingungen.append(
            Bedingung(
                beschreibung=b.beschreibung.strip(),
                erfuellt=b.erfuellt,
                faellig_bis=b.faellig_bis,
                anzahl=b.anzahl,
                betrag_euro=b.betrag_euro,
                frist_wochen=b.frist_wochen,
            )
        )
    for u in daten.urls:
        deal.urls.append(DealUrl(url=u.url.strip(), bezeichnung=_leer_zu_none(u.bezeichnung)))
    for a in daten.aufgaben:
        deal.aufgaben.append(
            Aufgabe(beschreibung=a.beschreibung.strip(), erledigt=a.erledigt, faellig_bis=a.faellig_bis)
        )
    # Reiner Tabellen-Lookup, keine KI-Websuche mehr (siehe Docstring dort) -
    # läuft deshalb immer, unabhängig von hintergrund_recherche.
    kuendigung_vorschlag(db, deal)
    spartanien_aufgabe_sicherstellen(deal)
    if hintergrund_recherche:
        deal.kwk_fehlgeschlagen = False
    else:
        # Nicht in der Datenbank gespeichert (kein mapped_column) - reiner
        # In-Memory-Marker, damit der Aufrufer direkt am zurückgegebenen Deal
        # ablesen kann, ob die KwK-Recherche fehlgeschlagen ist.
        deal.kwk_fehlgeschlagen = kwk_vorschlag(db, deal)
        if deal.kwk_fehlgeschlagen:
            # Wie kwk_ergebnis_anwenden() beim Übernehmen-Ablauf: eine
            # fehlgeschlagene Recherche bleibt beim manuellen JSON-Import
            # sonst folgenlos - der Nutzer bekommt stattdessen eine konkrete
            # Erinnerungs-Aufgabe statt eines nirgends ausgewerteten Markers.
            deal.aufgaben.append(Aufgabe(beschreibung=KWK_FALLBACK_AUFGABE_TEXT))
    db.add(deal)
    return deal
