"""Tabellen des Jahresabschlusses (Baustein 12)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class KontoauszugssaldoRow(Base):
    __tablename__ = "kontoauszugssalden"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    bankkonto_id: Mapped[str] = mapped_column(String(36), index=True)
    stichtag: Mapped[date] = mapped_column(Date, index=True)
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    erfasst_am: Mapped[datetime] = mapped_column(DateTime)
    erfasst_von: Mapped[str | None] = mapped_column(String(50), nullable=True)
