"""SQLAlchemy-Tabellen (Persistenzschicht, portabel SQLite/Postgres)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Float, Integer, Numeric, String
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


class BuchungssatzRow(Base):
    __tablename__ = "buchungssaetze"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaktion_id: Mapped[str] = mapped_column(String(36))
    datum: Mapped[date] = mapped_column(Date)
    soll_konto: Mapped[str] = mapped_column(String(10))
    haben_konto: Mapped[str] = mapped_column(String(10))
    betrag_netto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    steuer_schluessel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steuer_betrag: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    buchungstext: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    geprueft_von: Mapped[str | None] = mapped_column(String(50), nullable=True)
