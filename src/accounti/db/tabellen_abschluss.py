"""Tabellen des Jahresabschlusses (Baustein 12) und die Jahressperre.

Ist ein Jahr abgeschlossen (Saldovortrag), lassen sich Buchungen dieses Jahres nicht
mehr anlegen, ändern oder löschen — das prüft ein ORM-Ereignis auf ``buchungssaetze``.
Es greift für jeden Code, der dieses Modul geladen hat (``init_db`` und
``registriere_tabellen`` tun das). Rohes SQL umgeht es; einen Datenbanktrigger gibt es
nicht, weil das Sperrjahr im Datum steckt.
"""

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
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from accounti.db import Base
from accounti.db.tabellen import BuchungssatzRow, UnveraenderbarError


class JahrGesperrtError(RuntimeError):
    """Das Geschäftsjahr ist abgeschlossen — Änderung nur nach erneutem Öffnen."""


class KontoauszugssaldoRow(Base):
    __tablename__ = "kontoauszugssalden"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    bankkonto_id: Mapped[str] = mapped_column(String(36), index=True)
    stichtag: Mapped[date] = mapped_column(Date, index=True)
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    erfasst_am: Mapped[datetime] = mapped_column(DateTime)
    erfasst_von: Mapped[str | None] = mapped_column(String(50), nullable=True)


class AbgrenzungRow(Base):
    __tablename__ = "abgrenzungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    jahr: Mapped[int] = mapped_column(Integer, index=True)
    # je Buchung genau ein Vorschlag — auch ein abgelehnter kommt nicht wieder
    buchung_id: Mapped[str] = mapped_column(String(36), unique=True)
    art: Mapped[str] = mapped_column(String(10))
    konto: Mapped[str] = mapped_column(String(10))
    rap_konto: Mapped[str] = mapped_column(String(10))
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    von: Mapped[date] = mapped_column(Date)
    bis: Mapped[date] = mapped_column(Date)
    rechenweg: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    abgrenzung_buchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    aufloesung_buchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    entschieden_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entschieden_von: Mapped[str | None] = mapped_column(String(50), nullable=True)


class AbschlussRow(Base):
    """Ein abgeschlossenes (gesperrtes) oder wieder geöffnetes Geschäftsjahr."""

    __tablename__ = "abschluesse"

    jahr: Mapped[int] = mapped_column(Integer, primary_key=True)
    gesperrt: Mapped[bool] = mapped_column(Boolean)
    gewinnermittlung: Mapped[str] = mapped_column(String(10))
    ergebnis: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    abgeschlossen_am: Mapped[datetime] = mapped_column(DateTime)
    von: Mapped[str] = mapped_column(String(50))


class ProtokollRow(Base):
    """Abschlussprotokoll — nur anfügen, verkettet per Hash."""

    __tablename__ = "abschlussprotokoll"

    nr: Mapped[int] = mapped_column(Integer, primary_key=True)
    jahr: Mapped[int] = mapped_column(Integer, index=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    aktion: Mapped[str] = mapped_column(String(20))
    von: Mapped[str] = mapped_column(String(50))
    grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[str] = mapped_column(Text)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


@event.listens_for(ProtokollRow, "before_update")
@event.listens_for(ProtokollRow, "before_delete")
def _protokoll_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError("Das Abschlussprotokoll ist unveränderbar")


PROTOKOLL_TRIGGER = [
    f"CREATE TRIGGER abschlussprotokoll_kein_{aktion.lower()} BEFORE {aktion} "
    "ON abschlussprotokoll BEGIN "
    "SELECT RAISE(ABORT, 'Abschlussprotokoll ist unveränderbar'); END"
    for aktion in ("UPDATE", "DELETE")
]


@event.listens_for(ProtokollRow.__table__, "after_create")
def _protokoll_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in PROTOKOLL_TRIGGER:
            verbindung.execute(text(sql))


# --- Jahressperre -----------------------------------------------------------------


def jahr_gesperrt(verbindung: Connection, jahr: int) -> bool:
    if not verbindung.dialect.has_table(verbindung, AbschlussRow.__tablename__):
        return False
    gesperrt = verbindung.execute(
        select(AbschlussRow.gesperrt).where(AbschlussRow.jahr == jahr)
    ).scalar()
    return bool(gesperrt)


def gesperrte_jahre(verbindung: Connection) -> set[int]:
    if not verbindung.dialect.has_table(verbindung, AbschlussRow.__tablename__):
        return set()
    return set(
        verbindung.execute(
            select(AbschlussRow.jahr).where(AbschlussRow.gesperrt.is_(True))
        ).scalars()
    )


def _sperre_pruefen(verbindung: Connection, ziel: BuchungssatzRow) -> None:
    jahre = {ziel.datum.year} if ziel.datum else set()
    alt = inspect(ziel).attrs.datum.history.deleted
    jahre |= {d.year for d in alt if d is not None}
    for jahr in sorted(jahre):
        if jahr_gesperrt(verbindung, jahr):
            msg = (
                f"Geschäftsjahr {jahr} ist abgeschlossen — Buchungen sind gesperrt "
                f"(Änderung nur nach accounti abschluss oeffnen --jahr {jahr})"
            )
            raise JahrGesperrtError(msg)


@event.listens_for(BuchungssatzRow, "before_insert")
@event.listens_for(BuchungssatzRow, "before_update")
@event.listens_for(BuchungssatzRow, "before_delete")
def _buchung_im_gesperrten_jahr(
    _: Mapper[BuchungssatzRow], verbindung: Connection, ziel: BuchungssatzRow
) -> None:
    _sperre_pruefen(verbindung, ziel)
