"""Tabellen für festgeschriebene Kontoauszüge (Baustein 11)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class KontoauszugRow(Base):
    __tablename__ = "kontoauszuege"
    __table_args__ = (
        UniqueConstraint("finanzkonto", "jahr", "nummer"),
        UniqueConstraint("finanzkonto", "von"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finanzkonto: Mapped[str] = mapped_column(String(10), index=True)
    jahr: Mapped[int] = mapped_column(Integer)
    nummer: Mapped[int] = mapped_column(Integer)
    von: Mapped[date] = mapped_column(Date)
    bis: Mapped[date] = mapped_column(Date)
    waehrung: Mapped[str] = mapped_column(String(3))
    anfangssaldo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    endsaldo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    kontrollsaldo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class KontoauszugUmsatzRow(Base):
    __tablename__ = "kontoauszug_umsaetze"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    auszug_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kontoauszuege.id"), index=True
    )
    transaktion_id: Mapped[str] = mapped_column(String(36), unique=True)
    position: Mapped[int] = mapped_column(Integer)
    nachtrag: Mapped[bool] = mapped_column(Boolean, default=False)
