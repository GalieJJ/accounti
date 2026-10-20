"""Tabellen des Zahlungsverkehrs (Baustein 6).

Zwei Sicherungen liegen bewusst in der Datenbankschicht statt nur im Ablauf:

- ``zahlungen.sperre`` trägt die Posten-ID, solange der Lauf aktiv ist, und ist
  eindeutig — ein Posten kann so auch bei parallelen Prozessen nie in zwei aktiven
  Läufen stehen.
- Zahlungen eines Laufs, der kein Entwurf mehr ist, lassen sich über das ORM weder
  ändern (außer dem Freigeben der Sperre) noch löschen; das Protokoll ist nur
  anfügbar (unter SQLite zusätzlich per Trigger).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Connection,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class ZahlungslaufRow(Base):
    __tablename__ = "zahlungslaeufe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    stichtag: Mapped[date] = mapped_column(Date)
    ausfuehrung: Mapped[date] = mapped_column(Date)
    auftraggeber_name: Mapped[str] = mapped_column(String(140))
    auftraggeber_iban: Mapped[str] = mapped_column(String(34))
    auftraggeber_bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    erstellt_von: Mapped[str] = mapped_column(String(100))
    freigabe_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    msg_id: Mapped[str | None] = mapped_column(String(35), nullable=True)
    datei: Mapped[str | None] = mapped_column(Text, nullable=True)
    datei_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eingereicht_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ZahlungRow(Base):
    __tablename__ = "zahlungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lauf_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("zahlungslaeufe.id"), index=True
    )
    nr: Mapped[int] = mapped_column(Integer)
    posten_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offene_posten.id"), index=True
    )
    # Posten-ID, solange der Lauf aktiv ist; NULL nach Storno oder Ausführung.
    sperre: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"))
    empfaenger: Mapped[str] = mapped_column(String(200))
    iban: Mapped[str] = mapped_column(String(34))
    strasse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plz: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ort: Mapped[str | None] = mapped_column(String(100), nullable=True)
    land: Mapped[str | None] = mapped_column(String(2), nullable=True)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    skonto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    restbetrag_vorher: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    verwendungszweck: Mapped[str] = mapped_column(String(140))
    end_to_end_id: Mapped[str] = mapped_column(String(35))
    belegnummer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    belegdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    grund: Mapped[str] = mapped_column(String(500))


def _laufstatus(verbindung: Connection, lauf_id: str) -> str | None:
    return verbindung.execute(
        select(ZahlungslaufRow.status).where(ZahlungslaufRow.id == lauf_id)
    ).scalar_one_or_none()


@event.listens_for(ZahlungRow, "before_update")
def _zahlung_aendern(_: Any, verbindung: Connection, zeile: ZahlungRow) -> None:
    if _laufstatus(verbindung, zeile.lauf_id) in (None, "entwurf"):
        return
    geaendert = {a.key for a in inspect(zeile).attrs if a.history.has_changes()}
    if geaendert - {"sperre"}:
        msg = "Der Zahlungslauf ist freigegeben — Zahlungen sind unveränderbar"
        raise UnveraenderbarError(msg)


@event.listens_for(ZahlungRow, "before_delete")
def _zahlung_loeschen(_: Any, verbindung: Connection, zeile: ZahlungRow) -> None:
    if _laufstatus(verbindung, zeile.lauf_id) not in (None, "entwurf"):
        msg = "Der Zahlungslauf ist freigegeben — Zahlungen sind unveränderbar"
        raise UnveraenderbarError(msg)


class LaufProtokollRow(Base):
    """Protokoll der Zahlungsläufe — nur anfügen."""

    __tablename__ = "zahlungslauf_protokoll"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lauf_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("zahlungslaeufe.id"), index=True
    )
    nr: Mapped[int] = mapped_column(Integer)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    person: Mapped[str] = mapped_column(String(100))
    aktion: Mapped[str] = mapped_column(String(30))
    von_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nach_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text: Mapped[str] = mapped_column(Text)


@event.listens_for(LaufProtokollRow, "before_update")
@event.listens_for(LaufProtokollRow, "before_delete")
def _protokoll_nur_anfuegen(*_: object) -> None:
    msg = "Das Protokoll der Zahlungsläufe ist unveränderbar — Einträge nur anfügen"
    raise UnveraenderbarError(msg)


PROTOKOLL_TRIGGER = [
    f"CREATE TRIGGER zahlungslauf_protokoll_kein_{aktion.lower()} BEFORE {aktion} "
    "ON zahlungslauf_protokoll BEGIN "
    "SELECT RAISE(ABORT, 'Protokoll der Zahlungsläufe ist unveränderbar'); END"
    for aktion in ("UPDATE", "DELETE")
]


@event.listens_for(LaufProtokollRow.__table__, "after_create")
def _protokoll_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in PROTOKOLL_TRIGGER:
            verbindung.execute(text(sql))


class ZahlungssperreRow(Base):
    __tablename__ = "zahlungssperren"

    kontakt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kontakte.id"), primary_key=True
    )
    grund: Mapped[str] = mapped_column(String(500))
    gesetzt_am: Mapped[datetime] = mapped_column(DateTime)
    gesetzt_von: Mapped[str] = mapped_column(String(100))


class IbanKlaerungRow(Base):
    __tablename__ = "zahlung_iban_klaerungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    posten_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offene_posten.id"), index=True
    )
    rechnungs_iban: Mapped[str] = mapped_column(String(34))
    stammsatz_iban: Mapped[str] = mapped_column(String(34))
    grund: Mapped[str] = mapped_column(String(500))
    person: Mapped[str] = mapped_column(String(100))
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
