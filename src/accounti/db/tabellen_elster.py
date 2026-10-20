"""Tabellen der Steuermeldungen (Baustein 9) — beide nur zum Anfügen."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Connection,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class SteuermeldungFreigabeRow(Base):
    __tablename__ = "steuermeldung_freigaben"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    art: Mapped[str] = mapped_column(String(20))
    zeitraum: Mapped[str] = mapped_column(String(10), index=True)
    inhalt_hash: Mapped[str] = mapped_column(String(64), index=True)
    werte: Mapped[str] = mapped_column(Text)
    freigegeben_von: Mapped[str] = mapped_column(String(100))
    hinweise: Mapped[str] = mapped_column(Text)


class SteuermeldungProtokollRow(Base):
    """Übermittlungsprotokoll — verkettet per Hash, aufbewahrungspflichtig."""

    __tablename__ = "steuermeldung_protokolle"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    art: Mapped[str] = mapped_column(String(20))
    zeitraum: Mapped[str] = mapped_column(String(10), index=True)
    modus: Mapped[str] = mapped_column(String(10))
    weg: Mapped[str] = mapped_column(String(20))
    berichtigt: Mapped[bool] = mapped_column(Boolean)
    freigabe_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    freigegeben_von: Mapped[str | None] = mapped_column(String(100), nullable=True)
    datensatz: Mapped[str] = mapped_column(Text)
    datensatz_hash: Mapped[str] = mapped_column(String(64))
    ticket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erfolgreich: Mapped[bool] = mapped_column(Boolean)
    ergebnis: Mapped[str] = mapped_column(Text)
    pruefbericht: Mapped[str] = mapped_column(Text)
    server_antwort: Mapped[str | None] = mapped_column(Text, nullable=True)
    protokoll_pdf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    betrag: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    aufbewahren_bis: Mapped[date] = mapped_column(Date)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


@event.listens_for(SteuermeldungFreigabeRow, "before_update")
@event.listens_for(SteuermeldungFreigabeRow, "before_delete")
@event.listens_for(SteuermeldungProtokollRow, "before_update")
@event.listens_for(SteuermeldungProtokollRow, "before_delete")
def _nur_anfuegen(*_: object) -> None:
    msg = "Freigaben und Übermittlungsprotokoll sind unveränderbar — nur anfügen"
    raise UnveraenderbarError(msg)


def _trigger(tabelle: str) -> list[str]:
    return [
        f"CREATE TRIGGER {tabelle}_kein_{aktion.lower()} BEFORE {aktion} ON {tabelle} "
        f"BEGIN SELECT RAISE(ABORT, '{tabelle} ist unveränderbar'); END"
        for aktion in ("UPDATE", "DELETE")
    ]


@event.listens_for(SteuermeldungFreigabeRow.__table__, "after_create")
@event.listens_for(SteuermeldungProtokollRow.__table__, "after_create")
def _sqlite_trigger(tabelle: object, verbindung: Connection, **__: object) -> None:
    # SQLite sperrt auch rohes SQL; Postgres verlässt sich auf ORM-Sperre und Hash-Kette
    if verbindung.dialect.name == "sqlite":
        for sql in _trigger(str(getattr(tabelle, "name", ""))):
            verbindung.execute(text(sql))
