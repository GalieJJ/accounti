"""Tabellen der Anlagenbuchhaltung (Baustein 12)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class AnlagegutRow(Base):
    __tablename__ = "anlagegueter"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    konto: Mapped[str] = mapped_column(String(10), index=True)
    afa_konto: Mapped[str | None] = mapped_column(String(10), nullable=True)
    anschaffungsdatum: Mapped[date] = mapped_column(Date)
    anschaffungskosten: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    nutzungsdauer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    afa_art: Mapped[str] = mapped_column(String(20))
    wechsel_linear: Mapped[bool] = mapped_column(Boolean, default=True)
    immateriell: Mapped[bool] = mapped_column(Boolean, default=False)
    beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    typ: Mapped[str | None] = mapped_column(String(40), nullable=True)
    abgang_datum: Mapped[date | None] = mapped_column(Date, nullable=True)
    abgang_art: Mapped[str | None] = mapped_column(String(20), nullable=True)
    abgang_erloes: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notiz: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class AfaVorgangRow(Base):
    """Gebuchte AfA je Anlagegut bzw. Sammelposten (Grundlage des AfA-Laufs)."""

    __tablename__ = "afa_vorgaenge"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    objekt: Mapped[str] = mapped_column(String(80), index=True)
    anlage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    jahr: Mapped[int] = mapped_column(Integer, index=True)
    bis_monat: Mapped[int] = mapped_column(Integer)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    buchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    begruendung: Mapped[str] = mapped_column(String(500))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
