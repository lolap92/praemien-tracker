"""Datenmodell: ausschließlich Fakten.

Es gibt bewusst keine status-Spalte und keine ToDo-Tabelle für abgeleitete
ToDos. Status und die abgeleitete ToDo-Liste sind berechnete Sichten auf
diese Fakten (siehe derived.py).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
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
    freibetrag: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    praemien_auf_sparkonto: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kontonummer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zugangsdaten_gespeichert: Mapped[bool] = mapped_column(Boolean, default=False)
    kommentar: Mapped[str | None] = mapped_column(Text, nullable=True)
    kuendigung_hinweis: Mapped[str | None] = mapped_column(Text, nullable=True)
    kuendigung_hinweis_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
    erhalten: Mapped[bool] = mapped_column(Boolean, default=False)
    auszahlung_erwartet: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "YYYY-MM"

    deal: Mapped["Deal"] = relationship(back_populates="praemien")


class Bedingung(Base):
    __tablename__ = "bedingungen"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    beschreibung: Mapped[str] = mapped_column(String(255))
    erfuellt: Mapped[bool] = mapped_column(Boolean, default=False)
    faellig_bis: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

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
