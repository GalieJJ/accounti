"""Tabellen für Kreditkarten (Baustein 5, Paket 3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class KreditkarteRow(Base):
    __tablename__ = "kreditkarten"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    bankkonto_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bankkonten.id"), unique=True
    )
    girokonto_id: Mapped[str] = mapped_column(String(36), ForeignKey("bankkonten.id"))
    endziffern: Mapped[str | None] = mapped_column(String(4), nullable=True)
    muster: Mapped[str | None] = mapped_column(String(200), nullable=True)
    abrechnungstag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class KreditkartenabrechnungRow(Base):
    __tablename__ = "kreditkartenabrechnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kreditkarte_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kreditkarten.id"), index=True
    )
    stichtag: Mapped[date] = mapped_column(Date)
    von: Mapped[date | None] = mapped_column(Date, nullable=True)
    beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    summe: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    anzahl: Mapped[int] = mapped_column(Integer)
    belastung_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True
    )
    belastung_betrag: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20))
    befund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class KreditkartenumsatzRow(Base):
    """Umsatz des Kartenkontos → seine Abrechnung (jeder Umsatz höchstens einmal)."""

    __tablename__ = "kreditkartenumsaetze"

    transaktion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    abrechnung_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kreditkartenabrechnungen.id"), index=True
    )


class KreditkartenablehnungRow(Base):
    """Von Hand gelöste Zuordnung: diese Belastung nie wieder für diese Abrechnung."""

    __tablename__ = "kreditkartenablehnungen"

    abrechnung_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kreditkartenabrechnungen.id"), primary_key=True
    )
    transaktion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
