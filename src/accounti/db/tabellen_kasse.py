"""Tabelle des Kassenbuchs (Baustein 12) — nur anfügen.

Änderungen und Löschungen scheitern am ORM, unter SQLite zusätzlich an Triggern;
Korrekturen sind Stornoeinträge (GoBD: Unveränderbarkeit, § 146 Abs. 4 AO).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Connection, Date, DateTime, Integer, Numeric, String, event, text
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class KassenvorgangRow(Base):
    __tablename__ = "kassenbuch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    datum: Mapped[date] = mapped_column(Date, index=True)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    art: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(String(200))
    belegnummer: Mapped[str | None] = mapped_column(String(60), nullable=True)
    gegenkonto: Mapped[str | None] = mapped_column(String(10), nullable=True)
    steuersatz: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    transaktion_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    buchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    storno_von: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erfasst_am: Mapped[datetime] = mapped_column(DateTime)
    erfasst_von: Mapped[str | None] = mapped_column(String(50), nullable=True)


@event.listens_for(KassenvorgangRow, "before_update")
@event.listens_for(KassenvorgangRow, "before_delete")
def _nur_anfuegen(*_: object) -> None:
    msg = "Das Kassenbuch ist unveränderbar — Korrektur nur per Storno"
    raise UnveraenderbarError(msg)


KASSENBUCH_TRIGGER = [
    f"CREATE TRIGGER kassenbuch_kein_{aktion.lower()} BEFORE {aktion} "
    "ON kassenbuch BEGIN "
    "SELECT RAISE(ABORT, 'Kassenbuch ist unveränderbar'); END"
    for aktion in ("UPDATE", "DELETE")
]


@event.listens_for(KassenvorgangRow.__table__, "after_create")
def _kassenbuch_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in KASSENBUCH_TRIGGER:
            verbindung.execute(text(sql))
