from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from .models import Bank, Inhaber


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


def get_or_create_bank(db: Session, name: str) -> Bank:
    name = name.strip()
    bank = db.query(Bank).filter(Bank.name == name).one_or_none()
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
