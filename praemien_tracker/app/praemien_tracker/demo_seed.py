"""Demo-Daten für den Demo-Modus (siehe config.DEMO_MODUS).

Baut Deals/Aufgaben/Vorschläge bewusst direkt über die Modelle auf - NICHT
über helpers.build_deal_from_import(): das ruft für jeden Deal
kuendigung_vorschlag() auf, das bei konfiguriertem Anthropic-API-Key eine
echte, kostenpflichtige KI-Websuche auslösen kann (kuendigung_recherche.py).
Im Demo-Modus darf unter keinen Umständen eine echte externe Anfrage
ausgelöst werden - deshalb hier ein eigener, reiner ORM-Pfad ohne jede
Fachlogik, die auf Anthropic/mydealz/spartanien zugreift. Alle Namen sind
bewusst offensichtlich fiktiv, damit nie der Eindruck echter Bankdaten
entsteht.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .models import Aufgabe, Bank, Bedingung, Deal, DealVorschlag, Inhaber, Praemie, VorschlagBedingung


def lade_demo_daten(db: Session) -> None:
    heute = datetime.date.today()
    jahr = heute.year

    max_ = Inhaber(name="Max Mustermann")
    erika = Inhaber(name="Erika Mustermann")
    db.add_all([max_, erika])
    db.flush()

    def deal(bank: str, kontoart: str, inhaber: Inhaber, **kwargs) -> Deal:
        d = Deal(
            bank=Bank(name=bank),
            kontoart=kontoart,
            inhaber=inhaber,
            kuendigung_hinweis="Demo-Hinweis: Kündigung im Online-Banking unter Konto > Schließen möglich.",
            **kwargs,
        )
        db.add(d)
        return d

    # Kündigen (Prämie da, keine offenen Punkte, keine Sperrfrist)
    d1 = deal("Musterbank", "Girokonto", max_, zugangsdaten_gespeichert=True)
    d1.praemien.append(Praemie(quelle="bank", betrag=Decimal("150"), erhalten=True))

    # Bedingungen offen
    d2 = deal("Beispielbank AG", "Girokonto", max_, zugangsdaten_gespeichert=True)
    d2.praemien.append(Praemie(quelle="bank", betrag=Decimal("100"), erhalten=False))
    d2.bedingungen.append(Bedingung(beschreibung="3 Kartenzahlungen pro Monat", erfuellt=False))

    # Auf Prämie warten
    d3 = deal(
        "Demo Sparkasse",
        "Depot",
        erika,
        zugangsdaten_gespeichert=True,
        freibetrag=Decimal("500"),
        freibetrag_jahr=jahr,
    )
    d3.praemien.append(Praemie(quelle="spartanien", betrag=Decimal("300"), erhalten=False))

    # Auf Kündigung warten (Sperrfrist liegt noch in der Zukunft)
    d4 = deal(
        "Testbank Süd",
        "Girokonto",
        erika,
        zugangsdaten_gespeichert=True,
        kuendbar_ab=heute + datetime.timedelta(days=60),
    )
    d4.praemien.append(Praemie(quelle="bank", betrag=Decimal("120"), erhalten=True))
    d4.bedingungen.append(Bedingung(beschreibung="Gehaltseingang", erfuellt=True))

    # Bestätigung warten
    d5 = deal(
        "Fiktivbank",
        "Girokonto",
        max_,
        gekuendigt=True,
        gekuendigt_im_monat=f"{jahr - 1}-09",
        kuendigung_bestaetigt=False,
        zugangsdaten_gespeichert=True,
    )
    d5.praemien.append(Praemie(quelle="bank", betrag=Decimal("75"), erhalten=True))

    # Abgeschlossen
    d6 = deal(
        "Show-Bank",
        "Girokonto",
        erika,
        gekuendigt=True,
        gekuendigt_im_monat=f"{jahr - 2}-11",
        kuendigung_bestaetigt=True,
        zugangsdaten_gespeichert=True,
    )
    d6.praemien.append(Praemie(quelle="bank", betrag=Decimal("90"), erhalten=True))

    db.add(Aufgabe(beschreibung="Demo-Aufgabe: Kontoauszüge prüfen", erledigt=False, deal=None))
    db.add(
        Aufgabe(
            beschreibung="Demo-Aufgabe: Freistellungsauftrag für nächstes Jahr planen",
            erledigt=False,
            deal=None,
            faellig_bis=datetime.date(jahr, 12, 31),
        )
    )

    # Vorschläge (KI-Deal-Finder-Funde) - rein statisch für den Demo-Modus,
    # keine echte Websuche/API-Anfrage, kein Bezug zu echten Angeboten.
    def vorschlag(bank: str, inhaber: Inhaber, status: str, index: int, **kwargs) -> DealVorschlag:
        v = DealVorschlag(
            quelle=("spartanien", "mydealz", "dealdoktor")[index % 3],
            quelle_url=f"https://beispiel.invalid/demo-{index}",
            inhalt_hash=f"demo-hash-{index}",
            bank_name=bank,
            kontoart="Girokonto",
            praemie_betrag=Decimal("80"),
            status=status,
            inhaber=inhaber,
            roh_json="{}",
            **kwargs,
        )
        db.add(v)
        return v

    vorschlag("Neubank Demo", max_, "vorgeschlagen", 1)
    vorschlag("Wechselbank Beispiel", erika, "vorgeschlagen", 2)
    v3 = vorschlag("Prüfbank Beispiel", max_, "zu_pruefen", 3)
    v3.bedingungen.append(
        VorschlagBedingung(
            beschreibung="Mindesteinlage 2.000 €", einschaetzung="zu_pruefen", betrag_euro=Decimal("2000")
        )
    )
    v3.bedingungen.append(
        VorschlagBedingung(
            beschreibung="Kreditkarte innerhalb von 4 Wochen mindestens 2x für insgesamt 50 € einsetzen",
            einschaetzung="erfuellt",
            anzahl=2,
            betrag_euro=Decimal("50"),
            frist_wochen=4,
        )
    )
    vorschlag("Abgelehnt-Bank", erika, "automatisch_abgelehnt", 4, ablehnungsgruende="Prämie unter Mindestbetrag")
    vorschlag("Verworfen-Bank", max_, "verworfen", 5, verwerfen_gruende="bestandskunde")

    db.commit()
