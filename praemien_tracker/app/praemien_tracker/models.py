"""Datenmodell: ausschließlich Fakten.

Es gibt bewusst keine status-Spalte und keine ToDo-Tabelle für abgeleitete
ToDos. Status und die abgeleitete ToDo-Liste sind berechnete Sichten auf
diese Fakten (siehe derived.py).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    deals: Mapped[list["Deal"]] = relationship(back_populates="bank")


class Inhaber(Base):
    __tablename__ = "inhaber"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    ist_minderjaehrig: Mapped[bool] = mapped_column(Boolean, default=False)

    deals: Mapped[list["Deal"]] = relationship(back_populates="inhaber")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"), index=True)
    inhaber_id: Mapped[int] = mapped_column(ForeignKey("inhaber.id"), index=True)
    kontoart: Mapped[str] = mapped_column(String(50))
    kuendbar_ab: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    gekuendigt: Mapped[bool] = mapped_column(Boolean, default=False)
    gekuendigt_im_monat: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kuendigung_bestaetigt: Mapped[bool] = mapped_column(Boolean, default=False)
    # Deal ist nie zustande gekommen. Bewusst getrennt von gekuendigt: ein
    # stornierter Deal darf nicht in der Sperrfristen-Auswertung auftauchen,
    # denn dort geht es darum, wann eine Bank wieder Neukunden-Ziel ist.
    storniert: Mapped[bool] = mapped_column(Boolean, default=False)
    freibetrag: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Kalenderjahr, dem der Freistellungsauftrag zugerechnet wird - der
    # Sparer-Pauschbetrag gilt pro Jahr, eine jahresuebergreifende Summe
    # beantwortet keine sinnvolle Frage.
    freibetrag_jahr: Mapped[int | None] = mapped_column(nullable=True)
    # Geprüfte Auffälligkeiten als JSON {regel: signatur}. Die Signatur hält
    # den Zustand fest, der geprüft wurde - ändern sich die Fakten, passt sie
    # nicht mehr und der Hinweis erscheint erneut (siehe derived.pruefpunkte).
    pruefung_geprueft: Mapped[str | None] = mapped_column(Text, nullable=True)
    praemien_auf_sparkonto: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kontonummer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zugangsdaten_gespeichert: Mapped[bool] = mapped_column(Boolean, default=False)
    kommentar: Mapped[str | None] = mapped_column(Text, nullable=True)
    kuendigung_hinweis: Mapped[str | None] = mapped_column(Text, nullable=True)
    kuendigung_hinweis_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # True, solange kuendigung_hinweis unverändert aus einer KI-Websuche
    # stammt (siehe kuendigung_recherche.py) - im Unterschied zu einem fest
    # hinterlegten (kuendigung_hinweise.py) oder von Hand eingetragenen
    # Hinweis. Wird beim manuellen Bearbeiten des Felds wieder auf False
    # gesetzt, da es dann Nutzerhoheit ist.
    kuendigung_hinweis_ki: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON-Liste von Feldnamen, die bewusst als "nicht nötig" abgehakt wurden
    uebersprungene_felder: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_am: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    geaendert_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    bank: Mapped["Bank"] = relationship(back_populates="deals")
    inhaber: Mapped["Inhaber"] = relationship(back_populates="deals")
    praemien: Mapped[list["Praemie"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="Praemie.id"
    )
    bedingungen: Mapped[list["Bedingung"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="Bedingung.id"
    )
    aufgaben: Mapped[list["Aufgabe"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="Aufgabe.id"
    )
    urls: Mapped[list["DealUrl"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="DealUrl.id"
    )


class Praemie(Base):
    __tablename__ = "praemien"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    quelle: Mapped[str] = mapped_column(String(20))  # "spartanien" | "bank"
    betrag: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Wofür es diese (Teil-)Prämie gibt, Freitext aus dem Angebot (z.B. "für den
    # Kontowechselservice"). Nur zur Anzeige, macht bei aufgeteilten Prämien
    # nachvollziehbar, welcher Teilbetrag woran hängt. NULL, wenn das Angebot
    # keine Aufteilung mit eigenem Zweck nennt.
    zweck: Mapped[str | None] = mapped_column(String(255), nullable=True)
    erhalten: Mapped[bool] = mapped_column(Boolean, default=False)
    auszahlung_erwartet: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "YYYY-MM"
    # Bis wann die Prämie zuletzt/als nächstes auf Eingang geprüft wurde -
    # reiner Merkposten fürs "Prämien-Hopping" ("wo hatte ich schon
    # nachgeschaut?"), unabhängig vom Überfälligkeits-Datum in derived.py.
    # Nur gesetzt, wenn der Nutzer aktiv "+2 Wochen" geklickt hat; solange
    # leer, zeigt die Oberfläche stattdessen einen berechneten Vorschlag an
    # (siehe derived.praemie_naechste_pruefung).
    naechste_pruefung_am: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    deal: Mapped["Deal"] = relationship(back_populates="praemien")


class Bedingung(Base):
    __tablename__ = "bedingungen"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    beschreibung: Mapped[str] = mapped_column(String(255))
    erfuellt: Mapped[bool] = mapped_column(Boolean, default=False)
    faellig_bis: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # Wann erfüllt wurde - Bezugspunkt für die Überfälligkeit einer Prämie,
    # solange kein Auszahlungsdatum hinterlegt ist. Kalenderdatum, weil in
    # Monaten gerechnet wird. Wird beim Zurücknehmen wieder geleert.
    erfuellt_am: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # Strukturierte Kennzahlen der Auflage (von der KI extrahiert, sonst von
    # Hand), rein informativ für eine kompakte Anzeige "2× · 50 € · 4 Wochen".
    # beschreibung bleibt die verbindliche Quelle; jeweils NULL, wenn die Größe
    # im Angebot nicht genannt war.
    anzahl: Mapped[int | None] = mapped_column(nullable=True)
    betrag_euro: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    frist_wochen: Mapped[int | None] = mapped_column(nullable=True)
    # Label der Teilprämie, für die diese Bedingung erfüllt werden muss
    # (z.B. "250 € für den Kontowechselservice"). NULL = Grundvoraussetzung
    # fürs ganze Angebot. Macht sichtbar, welche Auflagen sich weglassen
    # lassen, wenn ein Teilbetrag bewusst nicht mitgenommen wird.
    gilt_fuer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    deal: Mapped["Deal"] = relationship(back_populates="bedingungen")


class Aufgabe(Base):
    __tablename__ = "aufgaben"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)
    beschreibung: Mapped[str] = mapped_column(String(255))
    erledigt: Mapped[bool] = mapped_column(Boolean, default=False)
    faellig_bis: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    deal: Mapped["Deal | None"] = relationship(back_populates="aufgaben")


class DealUrl(Base):
    __tablename__ = "deal_urls"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    bezeichnung: Mapped[str | None] = mapped_column(String(100), nullable=True)

    deal: Mapped["Deal"] = relationship(back_populates="urls")


class DealVorschlag(Base):
    """KI-Fund einer Neukunden-Prämie, noch kein Fakt (Erweiterung KI-Deal-Finder).

    Bewusst von DEAL getrennt: ein Fund ist erst nach "Übernehmen" ein Fakt.
    `bank_name` bleibt Freitext (keine FK auf BANK) - die Auflösung zu einem
    bestehenden oder neuen Bank-Datensatz passiert erst beim Übernehmen, über
    denselben Mechanismus wie beim händischen JSON-Import (roh_json).
    """

    __tablename__ = "deal_vorschlaege"

    id: Mapped[int] = mapped_column(primary_key=True)
    inhaber_id: Mapped[int] = mapped_column(ForeignKey("inhaber.id"), index=True)
    quelle: Mapped[str] = mapped_column(String(20))  # "mydealz" | "spartanien" | "dealdoktor"
    quelle_url: Mapped[str] = mapped_column(String(500), index=True)
    bank_name: Mapped[str] = mapped_column(String(100))
    kontoart: Mapped[str] = mapped_column(String(50))
    praemie_betrag: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Aus dem Angebotstext extrahiert, optional; bei Mehrdeutigkeit ("6 oder
    # 12 Monate") wird die kürzere Angabe übernommen (siehe extraktion.py).
    sperrfrist_monate: Mapped[int | None] = mapped_column(nullable=True)
    # Klartext-Begründung(en), nur bei zu_pruefen/automatisch_abgelehnt gefüllt.
    ablehnungsgruende: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Komma-getrennte Codes aus matching.VERWERFEN_GRUENDE_LABELS, nur beim
    # manuellen Verwerfen durch den Nutzer gefüllt (Mehrfachauswahl im
    # Dialog) - im Unterschied zu ablehnungsgruende, das die automatische
    # KI-Ablehnung begründet. Für einen minderjährigen Inhaber, für den ein
    # Angebot strukturell gar nicht gilt, wird die Zeile stattdessen direkt
    # gelöscht statt verworfen (siehe finder/lauf.py:
    # _nicht_anwendbaren_vorschlag_entfernen) - keine Entscheidung, die
    # "verworfen" markiert werden müsste.
    verwerfen_gruende: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Vollständiges JSON im Deal-Anlage-Format (schemas.DealImport) - wird
    # beim Übernehmen unverändert an build_deal_from_import() gereicht.
    roh_json: Mapped[str] = mapped_column(Text)
    # Hash aus den fachlich relevanten Feldern (Prämie, Sperrfrist,
    # Bedingungen) - Grundlage für die Dedup-Prüfung: bei geänderten Daten
    # (z.B. höhere Prämie) entsteht bewusst ein neuer Datensatz statt eines
    # stillen Updates, damit die Historie nachvollziehbar bleibt.
    inhalt_hash: Mapped[str] = mapped_column(String(64), index=True)
    gefunden_am: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), index=True)
    # Verweist auf den Deal, der beim Übernehmen aus dieser Zeile entstanden
    # ist (nur bei status=uebernommen gesetzt, siehe routers/vorschlaege.py:
    # uebernehmen_bestaetigen) - macht die Übernahme nachvollziehbar. Absichtlich
    # ohne Kaskaden-Löschung: wird der Deal später gelöscht, bleibt die
    # Vorschlags-Zeile selbst erhalten (siehe zuruecksetzen), nur die
    # Verknüpfung wird geleert (routers/deals.py: deal_delete).
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)

    inhaber: Mapped["Inhaber"] = relationship()
    deal: Mapped["Deal | None"] = relationship()
    bedingungen: Mapped[list["VorschlagBedingung"]] = relationship(
        back_populates="vorschlag", cascade="all, delete-orphan", order_by="VorschlagBedingung.id"
    )
    praemien: Mapped[list["VorschlagPraemie"]] = relationship(
        back_populates="vorschlag", cascade="all, delete-orphan", order_by="VorschlagPraemie.id"
    )


class VorschlagPraemie(Base):
    """Einzelne Teilprämie eines Vorschlags mit eigener Bedingung.

    Ein Angebot bringt häufig mehrere Prämien mit unterschiedlichen
    Voraussetzungen mit (z.B. 50 EUR von Spartanien für die Kontoeröffnung
    plus 250 EUR von der Bank für den Kontowechselservice). Damit das im
    Vorschlag sichtbar bleibt, wird jede Teilprämie einzeln festgehalten -
    analog zu VorschlagBedingung. `praemie_betrag` auf DealVorschlag bleibt
    die Gesamtsumme für Anzeige und Mindestprämien-Prüfung.
    """

    __tablename__ = "vorschlag_praemien"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_vorschlag_id: Mapped[int] = mapped_column(ForeignKey("deal_vorschlaege.id"), index=True)
    betrag: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Wer die Teilprämie zahlt, Freitext aus dem Angebot (z.B. "Spartanien",
    # "Santander"). Nur zur Anzeige; die kanonische Zuordnung spartanien/bank
    # für den späteren Deal steckt in roh_json.
    geber: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Wofür es diese Teilprämie gibt (z.B. "für die Kontoeröffnung").
    bedingung: Mapped[str | None] = mapped_column(String(255), nullable=True)

    vorschlag: Mapped["DealVorschlag"] = relationship(back_populates="praemien")


class VorschlagBedingung(Base):
    """Einzelne, von der KI erkannte Bedingung eines Vorschlags.

    Bewusst als Liste (analog zu Bedingung auf DEAL) statt eines einzelnen
    Freitextfelds: ein Angebot bringt in der Regel mehrere, unabhängig zu
    bewertende Bedingungen mit (Mindesteinlage, Gehaltseingang,
    Vertragslaufzeit, ...).
    """

    __tablename__ = "vorschlag_bedingungen"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_vorschlag_id: Mapped[int] = mapped_column(ForeignKey("deal_vorschlaege.id"), index=True)
    beschreibung: Mapped[str] = mapped_column(String(255))
    # erfuellt | zu_pruefen | nicht_erfuellt - KI-Einschätzung je Bedingung.
    # Nur "nicht_erfuellt" fließt in eine automatische Ablehnung ein, siehe
    # matching.py.
    einschaetzung: Mapped[str] = mapped_column(String(20))
    # Strukturierte Kennzahlen der Auflage aus der KI-Extraktion, sofern im
    # Text genannt - erlauben die kompakte Anzeige "2× · 50 € · 4 Wochen" auf
    # der Vorschlagskarte und wandern beim Übernehmen über roh_json auf die
    # spätere Bedingung. Jeweils NULL, wenn im Angebotstext nicht genannt.
    anzahl: Mapped[int | None] = mapped_column(nullable=True)
    betrag_euro: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    frist_wochen: Mapped[int | None] = mapped_column(nullable=True)
    # Label der Teilprämie, für die diese Bedingung gilt (z.B. "250 € für den
    # Kontowechselservice"). NULL = Grundvoraussetzung fürs ganze Angebot.
    gilt_fuer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    vorschlag: Mapped["DealVorschlag"] = relationship(back_populates="bedingungen")


class FinderFund(Base):
    """Gedächtnis des KI-Deal-Finders je Rohquelle-URL - verhindert, dass ein
    unverändertes Angebot bei jedem Lauf erneut gegen die Anthropic-API
    geschickt wird. Themen-Check und Struktur-Extraktion sind die einzigen
    kostenpflichtigen Schritte (siehe finder/lauf.py); beide werden
    übersprungen, solange sich rohtext_hash seit dem letzten Lauf nicht
    ändert.

    War ein Fund thematisch nicht passend, wird das dauerhaft festgehalten
    (ist_relevant=False, extraktion_json=None) - er geht dann bei künftigen
    Läufen gar nicht mehr an die API, sondern wird direkt übersprungen.
    Ändert sich der Rohtext unter derselben URL (z.B. ein bearbeiteter
    mydealz-Beitrag), weicht der Hash ab und der Fund wird neu geprüft.
    """

    __tablename__ = "finder_funde"

    id: Mapped[int] = mapped_column(primary_key=True)
    quelle: Mapped[str] = mapped_column(String(20))
    quelle_url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    rohtext_hash: Mapped[str] = mapped_column(String(64))
    ist_relevant: Mapped[bool] = mapped_column(Boolean)
    # Vollständiges Extraktionsergebnis (extraktion.AngebotExtraktion) als
    # JSON - nur gefüllt, wenn ist_relevant. Wird bei unverändertem Rohtext
    # wiederverwendet, damit auch das deterministische Matching (eine
    # Sperrfrist kann mit der Zeit erfüllt werden, ohne dass sich am Angebot
    # etwas ändert) weiterhin ohne neuen API-Aufruf läuft.
    extraktion_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstmals_gesehen_am: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    zuletzt_gesehen_am: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class KuendigungRecherche(Base):
    """KI-recherchierter Kündigungsweg für eine Bank+Kontoart-Kombination, für
    die KUENDIGUNG_HINWEISE (kuendigung_hinweise.py, fest hinterlegt) keinen
    Eintrag kennt. Wird einmalig per Web-Search recherchiert (siehe
    kuendigung_recherche.py) und danach für jeden weiteren Deal derselben
    Kombination aus dem Cache übernommen statt erneut gegen die API zu gehen
    - dieselbe Kostenersparnis-Idee wie FinderFund beim KI-Deal-Finder."""

    __tablename__ = "kuendigung_recherchen"
    __table_args__ = (UniqueConstraint("bank_name", "kontoart", name="uq_kuendigung_recherche_bank_kontoart"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_name: Mapped[str] = mapped_column(String(100), index=True)
    kontoart: Mapped[str] = mapped_column(String(50))
    hinweis: Mapped[str] = mapped_column(Text)
    hinweis_url: Mapped[str] = mapped_column(String(500))
    recherchiert_am: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class FinderLauf(Base):
    """Protokoll eines KI-Deal-Finder-Laufs - für die Statusanzeige im
    Vorschläge-Tab (letzter Lauf erfolgreich? wie viele Funde je Quelle?
    Fehler?). Bewusst eine eigene, schlanke Tabelle statt Wiederverwendung
    von ProtokollEintrag: dort geht es um Änderungen an Fakten, hier um den
    Lauf selbst - beides zu vermischen würde die Änderungshistorie
    verunreinigen."""

    __tablename__ = "finder_laeufe"

    id: Mapped[int] = mapped_column(primary_key=True)
    gestartet_am: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    beendet_am: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    erfolgreich: Mapped[bool] = mapped_column(Boolean, default=False)
    mydealz_geladen: Mapped[int] = mapped_column(default=0)
    spartanien_geladen: Mapped[int] = mapped_column(default=0)
    dealdoktor_geladen: Mapped[int] = mapped_column(default=0)
    # Aufschlüsselung je Quelle für die Tabelle im Vorschläge-Tab. Jeder
    # geladene Fund landet in genau einer der vier Kategorien, die Summe je
    # Quelle ergibt wieder <quelle>_geladen:
    #   neu          = neues Bank-Angebot (neue Karte)
    #   vorhanden    = bekanntes Bank-Angebot, unverändert
    #   aktualisiert = bekanntes Bank-Angebot, Status durch Zeitablauf nachgezogen
    #   rauschen     = kein Bank-Angebot, Duplikat oder Fehler ("nicht relevant, doppelt, etc.")
    mydealz_neu: Mapped[int] = mapped_column(default=0)
    mydealz_vorhanden: Mapped[int] = mapped_column(default=0)
    mydealz_aktualisiert: Mapped[int] = mapped_column(default=0)
    mydealz_rauschen: Mapped[int] = mapped_column(default=0)
    spartanien_neu: Mapped[int] = mapped_column(default=0)
    spartanien_vorhanden: Mapped[int] = mapped_column(default=0)
    spartanien_aktualisiert: Mapped[int] = mapped_column(default=0)
    spartanien_rauschen: Mapped[int] = mapped_column(default=0)
    dealdoktor_neu: Mapped[int] = mapped_column(default=0)
    dealdoktor_vorhanden: Mapped[int] = mapped_column(default=0)
    dealdoktor_aktualisiert: Mapped[int] = mapped_column(default=0)
    dealdoktor_rauschen: Mapped[int] = mapped_column(default=0)
    # Neue Angebote/Karten insgesamt (Summe über beide Quellen, = *_neu) -
    # ein neuer Deal zählt genau einmal, unabhängig von der Zahl der Inhaber.
    neu_gefunden: Mapped[int] = mapped_column(default=0)
    uebersprungen: Mapped[int] = mapped_column(default=0)
    # Funde, die dank finder_funde (Rohtext unverändert) ganz ohne
    # API-Aufruf erledigt wurden - macht die Kostenersparnis sichtbar.
    aus_cache: Mapped[int] = mapped_column(default=0)
    # Klartext, mehrere Fehler mit "; " getrennt (Quellenausfall, einzelne
    # Extraktionsfehler, unerwarteter Abbruch) - None, wenn alles glatt lief.
    fehler: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProtokollEintrag(Base):
    """Änderungsprotokoll, automatisch über SQLAlchemy-Events befüllt (siehe
    protokoll.py) - kein manuelles Loggen in den Routen nötig. Bewusst ohne
    ForeignKey-Constraint auf deals.id, da ein Eintrag auch nach dem Löschen
    des zugehörigen Deals bestehen bleiben muss."""

    __tablename__ = "protokoll"

    id: Mapped[int] = mapped_column(primary_key=True)
    zeitpunkt: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    tabelle: Mapped[str] = mapped_column(String(50))
    objekt_id: Mapped[int] = mapped_column()
    deal_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    aktion: Mapped[str] = mapped_column(String(20))  # "erstellt" | "geaendert" | "geloescht"
    feld: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alter_wert: Mapped[str | None] = mapped_column(Text, nullable=True)
    neuer_wert: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Komplettes JSON der Zeile zum Zeitpunkt dieses Eintrags (bei "geaendert"
    # der Stand nach der Änderung, bei "geloescht" der Stand davor) -
    # zusätzlich zu alter_wert/neuer_wert, die sich nur auf das einzelne
    # geänderte Feld beziehen.
    json_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Denormalisiert zum Zeitpunkt des Eintrags gespeichert (nicht per JOIN
    # nachgeschlagen), damit der Kontext auch nach dem Löschen des Deals
    # erhalten bleibt.
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    inhaber_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kontoart: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Vollständig gerenderte Momentaufnahme der Dealseite (deal_snapshot.html)
    # zum Zeitpunkt dieses Eintrags - anders als der Link auf deals/{id}
    # bleibt das auch dann lesbar, wenn der Deal später gelöscht wird.
    html_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
