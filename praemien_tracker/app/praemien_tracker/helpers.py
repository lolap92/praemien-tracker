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
    """Recherchierten Kündigungsweg als Vorschlag setzen, falls für Bank und
    Kontoart einer hinterlegt ist und der Deal noch keinen eigenen trägt.

    Kennt KUENDIGUNG_HINWEISE (fest hinterlegt) keinen Eintrag, wird
    zusätzlich einmalig per KI-Websuche recherchiert (kuendigung_recherche.py)
    - nur, wenn ein Anthropic-API-Key konfiguriert ist, sonst bleibt das Feld
    wie bisher leer. Ein so gesetzter Hinweis wird als KI-recherchiert
    markiert (kuendigung_hinweis_ki), damit die Oberfläche ihn von den fest
    hinterlegten, geprüften Einträgen unterscheiden kann.

    Wird nur beim Anlegen aufgerufen. Danach gehört das Feld dem Nutzer -
    ein geleertes oder überschriebenes Feld bleibt so, wie der Nutzer es
    haben möchte (siehe deal_update()/deal_kuendigung_hinweis_update()).

    Im Demo-Modus komplett übersprungen (auch die feste Tabelle bringt
    nichts, da die Bank ohnehin frei erfunden ist) - vor allem aber, damit
    hier unter keinen Umständen eine echte, kostenpflichtige KI-Websuche
    ausgelöst wird, nur weil im Demo-Modus ein Vorschlag "übernommen" wird.
    """
    if DEMO_MODUS or deal.kuendigung_hinweis or deal.bank is None:
        return
    eintrag = hinweis_fuer(deal.bank.name, deal.kontoart)
    if eintrag:
        deal.kuendigung_hinweis, deal.kuendigung_hinweis_url = eintrag
        return
    eintrag = kuendigung_recherche.hinweis_recherchieren(db, deal.bank.name, deal.kontoart)
    if eintrag:
        deal.kuendigung_hinweis, deal.kuendigung_hinweis_url = eintrag
        deal.kuendigung_hinweis_ki = True


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


def build_deal_from_import(db: Session, daten: DealImport) -> Deal:
    """Legt einen Deal inkl. Prämien/Bedingungen/Aufgaben/Links aus validierten
    JSON-Importdaten an."""
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
            Bedingung(beschreibung=b.beschreibung.strip(), erfuellt=b.erfuellt, faellig_bis=b.faellig_bis)
        )
    for u in daten.urls:
        deal.urls.append(DealUrl(url=u.url.strip(), bezeichnung=_leer_zu_none(u.bezeichnung)))
    for a in daten.aufgaben:
        deal.aufgaben.append(
            Aufgabe(beschreibung=a.beschreibung.strip(), erledigt=a.erledigt, faellig_bis=a.faellig_bis)
        )
    kuendigung_vorschlag(db, deal)
    spartanien_aufgabe_sicherstellen(deal)
    # Nicht in der Datenbank gespeichert (kein mapped_column) - reiner
    # In-Memory-Marker, damit der Übernehmen-Endpunkt direkt am
    # zurückgegebenen Deal ablesen kann, ob die KwK-Recherche fehlgeschlagen
    # ist, und den Nutzer entsprechend hinweisen kann.
    deal.kwk_fehlgeschlagen = kwk_vorschlag(db, deal)
    db.add(deal)
    return deal
