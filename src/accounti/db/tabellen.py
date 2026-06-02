"""SQLAlchemy-Tabellen (Persistenzschicht, portabel SQLite/Postgres)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class TransaktionRow(Base):
    __tablename__ = "transaktionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    datum: Mapped[date] = mapped_column(Date)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    verwendungszweck: Mapped[str] = mapped_column(String(500))
    gegenkonto_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gegenkonto_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    quelle: Mapped[str] = mapped_column(String(20))
    rohtext: Mapped[str] = mapped_column(String(2000))
