"""Tabellen für Marktplatz-Abrechnungen (Baustein 11)."""

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


class MarktplatzAbrechnungRow(Base):
    __tablename__ = "marktplatz_abrechnungen"
    __table_args__ = (UniqueConstraint("marktplatz", "nummer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    marktplatz: Mapped[str] = mapped_column(String(20))
    nummer: Mapped[str] = mapped_column(String(80))
    von: Mapped[date] = mapped_column(Date)
    bis: Mapped[date] = mapped_column(Date)
    auszahlungsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    waehrung: Mapped[str] = mapped_column(String(3))
    auszahlung: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    kurs: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    anfangssaldo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    endsaldo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    dateiname: Mapped[str] = mapped_column(String(255))
    beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    vollstaendig: Mapped[bool] = mapped_column(Boolean, default=True)
    importiert_am: Mapped[datetime] = mapped_column(DateTime)


class MarktplatzPostenRow(Base):
    __tablename__ = "marktplatz_posten"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    abrechnung_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("marktplatz_abrechnungen.id"), index=True
    )
    nr: Mapped[int] = mapped_column(Integer)
    art: Mapped[str] = mapped_column(String(20))
    datum: Mapped[date] = mapped_column(Date)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    waehrung: Mapped[str] = mapped_column(String(3))
    betrag_eur: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    beschreibung: Mapped[str] = mapped_column(String(500))
    gebuehrenart: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bestellnummer: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    artikel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bestimmungsland: Mapped[str | None] = mapped_column(String(2), nullable=True)
    abgangsland: Mapped[str | None] = mapped_column(String(2), nullable=True)
    kaeufer_ust_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    versand_durch_marktplatz: Mapped[bool] = mapped_column(Boolean, default=False)
    geschaeftskunde: Mapped[bool] = mapped_column(Boolean, default=False)
    auszahlungs_nr: Mapped[str | None] = mapped_column(String(80), nullable=True)
    referenz: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    gegenpartei: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_transaktion_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )


class MarktplatzBefundRow(Base):
    __tablename__ = "marktplatz_befunde"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    abrechnung_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("marktplatz_abrechnungen.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(40))
    schweregrad: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(String(1000))
    posten_nr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    erledigt: Mapped[bool] = mapped_column(Boolean, default=False)
