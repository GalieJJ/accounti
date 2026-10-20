"""Tabellen der Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7).

* ``journal`` — nur anfügen, jeder Eintrag per SHA-256 an seinen Vorgänger gekettet.
  Ändern und Löschen scheitern am ORM, unter SQLite zusätzlich an Triggern (per
  ``after_create`` angelegt).
* ``buchungskorrekturen`` — Storno (und Neubuchung) einer freigegebenen Buchung;
  ebenfalls nur anfügen.

Beim Import dieses Moduls werden die Journal-Ereignisse auf der Sitzung eingehängt
(``accounti.pruefung.ereignisse``) — ``init_db`` und ``registriere_tabellen`` laden
es, die CLI über ihre Befehlsgruppen.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Connection, Date, DateTime, Index, Integer, String, Text, event
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class JournalRow(Base):
    """Journal aller buchungsrelevanten Vorgänge — nur anfügen, hash-verkettet."""

    __tablename__ = "journal"

    nr: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    person: Mapped[str] = mapped_column(String(100))
    vorgang: Mapped[str] = mapped_column(String(40), index=True)
    objekt_typ: Mapped[str] = mapped_column(String(30))
    objekt_id: Mapped[str] = mapped_column(String(64))
    vorher: Mapped[str | None] = mapped_column(Text, nullable=True)
    nachher: Mapped[str | None] = mapped_column(Text, nullable=True)
    grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bezug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)

    __table_args__ = (Index("ix_journal_objekt", "objekt_typ", "objekt_id"),)


class BuchungskorrekturRow(Base):
    """Storno einer freigegebenen Buchung — nur anfügen."""

    __tablename__ = "buchungskorrekturen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_id: Mapped[str] = mapped_column(String(36), unique=True)
    storno_id: Mapped[str] = mapped_column(String(36), unique=True)
    neubuchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    datum: Mapped[date] = mapped_column(Date)
    grund: Mapped[str] = mapped_column(String(500))
    person: Mapped[str] = mapped_column(String(100))
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)


@event.listens_for(JournalRow, "before_update")
@event.listens_for(JournalRow, "before_delete")
def _journal_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError("Das Journal ist unveränderbar — Einträge nur anfügen")


@event.listens_for(BuchungskorrekturRow, "before_update")
@event.listens_for(BuchungskorrekturRow, "before_delete")
def _korrektur_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError("Buchungskorrekturen sind unveränderbar")


def _trigger(tabelle: str, text: str) -> list[str]:
    return [
        f"CREATE TRIGGER {tabelle}_kein_{aktion.lower()} BEFORE {aktion} "
        f"ON {tabelle} BEGIN SELECT RAISE(ABORT, '{text}'); END"
        for aktion in ("UPDATE", "DELETE")
    ]


# SQLite sperrt auch rohes SQL; Postgres verlässt sich auf ORM-Sperre und Hash-Kette.
JOURNAL_TRIGGER = _trigger("journal", "Journal ist unveränderbar")
KORREKTUR_TRIGGER = _trigger(
    "buchungskorrekturen", "Buchungskorrekturen sind unveränderbar"
)


@event.listens_for(JournalRow.__table__, "after_create")
def _journal_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in JOURNAL_TRIGGER:
            verbindung.execute(sql_text(sql))


@event.listens_for(BuchungskorrekturRow.__table__, "after_create")
def _korrektur_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in KORREKTUR_TRIGGER:
            verbindung.execute(sql_text(sql))


# Journal-Ereignisse auf der Sitzung einhängen (nach den Tabellen, die es braucht)
import accounti.pruefung.ereignisse  # noqa: E402, F401
