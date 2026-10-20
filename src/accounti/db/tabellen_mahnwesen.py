"""Tabellen des Mahnwesens (Baustein 6).

Versendete Mahnungen sind die Mahnhistorie: Sie lassen sich über das ORM weder ändern
noch löschen.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Connection,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    event,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class MahnungRow(Base):
    __tablename__ = "mahnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    posten_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offene_posten.id"), index=True
    )
    kontakt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kontakte.id"), index=True
    )
    stufe: Mapped[int] = mapped_column(Integer)
    stufe_name: Mapped[str] = mapped_column(String(100))
    datum: Mapped[date] = mapped_column(Date)
    belegnummer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    belegdatum: Mapped[date] = mapped_column(Date)
    faellig_am: Mapped[date] = mapped_column(Date)
    rechnungsbetrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    restbetrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    verzug_ab: Mapped[date | None] = mapped_column(Date, nullable=True)
    zinsen: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    zinsabschnitte: Mapped[str] = mapped_column(Text)  # JSON
    gebuehren_kumuliert: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    gebuehren: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    pauschale: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    summe: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    zahlungsfrist: Mapped[date] = mapped_column(Date)
    unternehmer: Mapped[bool] = mapped_column(Boolean)
    einstufung: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), index=True)
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    versand_weg: Mapped[str | None] = mapped_column(String(50), nullable=True)
    datei_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


def _gespeicherter_status(verbindung: Connection, mahnung_id: str) -> str | None:
    return verbindung.execute(
        select(MahnungRow.status).where(MahnungRow.id == mahnung_id)
    ).scalar_one_or_none()


@event.listens_for(MahnungRow, "before_update")
@event.listens_for(MahnungRow, "before_delete")
def _versendet_ist_historie(_: Any, verbindung: Connection, zeile: MahnungRow) -> None:
    if _gespeicherter_status(verbindung, zeile.id) == "versendet":
        msg = "Versendete Mahnungen sind Historie — unveränderbar"
        raise UnveraenderbarError(msg)


class MahnKontaktRow(Base):
    __tablename__ = "mahn_kontakte"

    kontakt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kontakte.id"), primary_key=True
    )
    mahnsperre: Mapped[bool] = mapped_column(Boolean, default=False)
    sperrgrund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unternehmer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
