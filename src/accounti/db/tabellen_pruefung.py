"""Tabellen der Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7).

* ``journal`` — nur anfügen, jeder Eintrag per SHA-256 an seinen Vorgänger gekettet.
  Ändern und Löschen scheitern am ORM, unter SQLite zusätzlich an Triggern (per
  ``after_create`` angelegt).
* ``buchungskorrekturen`` — Storno (und Neubuchung) einer freigegebenen Buchung;
  ebenfalls nur anfügen.
* ``periodenabschluesse`` — festgeschriebene Monate. Ein ORM-Ereignis auf
  ``buchungssaetze`` verweigert wie die Jahressperre (``tabellen_abschluss``) Anlegen,
  Ändern und Löschen von Buchungen in einem gesperrten Monat
  (``PeriodeGesperrtError``, ein ``JahrGesperrtError``); angenommen wird nur der
  Stornovermerk.

Die Journal-Ereignisse auf der Sitzung (``accounti.pruefung.ereignisse``) hängen
``session_factory`` und ``init_db`` ein (``accounti.db.registriere_ereignisse``) — nicht
der Import dieses Moduls.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Connection,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    event,
    inspect,
    select,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from accounti.db import Base
from accounti.db.tabellen import BuchungssatzRow, UnveraenderbarError
from accounti.db.tabellen_abschluss import (
    JahrGesperrtError,
    jahressperre,
    nur_stornovermerk,
    sperrcache,
    vorab_geprueft,
)


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


# --- Monatssperre (Periodenabschluss) --------------------------------------------


class PeriodeGesperrtError(JahrGesperrtError):
    """Der Monat ist festgeschrieben — ändern erst nach ``accounti periode oeffnen``."""


class PeriodenabschlussRow(Base):
    """Ein festgeschriebener (oder wieder geöffneter) Monat."""

    __tablename__ = "periodenabschluesse"

    monat: Mapped[str] = mapped_column(String(7), primary_key=True)  # JJJJ-MM
    gesperrt: Mapped[bool] = mapped_column(Boolean)
    geschlossen_am: Mapped[datetime] = mapped_column(DateTime)
    geschlossen_von: Mapped[str] = mapped_column(String(100))
    geoeffnet_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    geoeffnet_von: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grund: Mapped[str | None] = mapped_column(String(500), nullable=True)


def gesperrte_monate(verbindung: Connection) -> set[str]:
    if not verbindung.dialect.has_table(verbindung, PeriodenabschlussRow.__tablename__):
        return set()
    return set(
        verbindung.execute(
            select(PeriodenabschlussRow.monat).where(
                PeriodenabschlussRow.gesperrt.is_(True)
            )
        ).scalars()
    )


def monat_gesperrt(
    verbindung: Connection, monat: str, cache: dict[str, Any] | None = None
) -> bool:
    if cache is not None:
        if "monate" not in cache:
            cache["monate"] = gesperrte_monate(verbindung)
        return monat in cache["monate"]
    if not verbindung.dialect.has_table(verbindung, PeriodenabschlussRow.__tablename__):
        return False
    gesperrt = verbindung.execute(
        select(PeriodenabschlussRow.gesperrt).where(PeriodenabschlussRow.monat == monat)
    ).scalar()
    return bool(gesperrt)


def monatssperre(
    verbindung: Connection, monat: str, cache: dict[str, Any] | None = None
) -> PeriodeGesperrtError | None:
    """Der Fehler, wenn der Monat festgeschrieben ist — sonst ``None``."""
    if not monat_gesperrt(verbindung, monat, cache):
        return None
    return PeriodeGesperrtError(
        f"Monat {monat} ist festgeschrieben — Buchungen sind gesperrt "
        f"(Änderung nur nach accounti periode oeffnen {monat} --grund …)"
    )


def sperrfehler(
    verbindung: Connection, tag: date, cache: dict[str, Any] | None = None
) -> JahrGesperrtError | None:
    """Jahres- oder Monatssperre am Tag — der Fehler, sonst ``None``."""
    return jahressperre(verbindung, tag.year, cache) or monatssperre(
        verbindung, f"{tag:%Y-%m}", cache
    )


def _monatssperre(verbindung: Connection, ziel: BuchungssatzRow) -> None:
    # das alte Datum steht dank active_history auch nach dem Ablauf in der Historie
    tage = {ziel.datum} if ziel.datum else set()
    tage |= {d for d in inspect(ziel).attrs.datum.history.deleted if d is not None}
    cache = sperrcache(ziel)
    for monat in sorted({f"{d:%Y-%m}" for d in tage}):
        if (fehler := monatssperre(verbindung, monat, cache)) is not None:
            raise fehler


@event.listens_for(BuchungssatzRow, "before_insert")
@event.listens_for(BuchungssatzRow, "before_delete")
def _buchung_im_gesperrten_monat(
    _: Mapper[BuchungssatzRow], verbindung: Connection, ziel: BuchungssatzRow
) -> None:
    _monatssperre(verbindung, ziel)


@event.listens_for(BuchungssatzRow, "before_update")
def _aenderung_im_gesperrten_monat(
    _: Mapper[BuchungssatzRow], verbindung: Connection, ziel: BuchungssatzRow
) -> None:
    if not vorab_geprueft(ziel) and not nur_stornovermerk(ziel):
        _monatssperre(verbindung, ziel)
