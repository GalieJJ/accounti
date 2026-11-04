"""Tabellen der Einstellungen in der Datenbank der Gesellschaft (Baustein 10c, P4).

* ``einstellungen`` — je Abschnitt nummerierte Versionen, **nur anfügen**: Ändern,
  Löschen und Ersetzen scheitern am ORM, an ``db.GESCHUETZT`` (Massenwege) und an
  Triggern unter SQLite (auch gegen ``REPLACE INTO``) und PostgreSQL
  (``db/schutz.py``, ``after_create`` und Migration). Jede
  Version trägt den Hash ihrer Spalten und den ihres Vorgängers im selben Abschnitt
  (``repo_einstellungen.versionshash``); ``daten`` ist kanonisches JSON in Normalform.
* ``einstellungsantraege`` — Anträge auf eine Lockerung (K3): veränderlich nur aus
  „offen“ heraus und nur in Status und Entscheidungsfeldern, nie gelöscht — über ORM
  und ``db.GESCHUETZT`` (D11), ohne Trigger.
* ``geheimnisse`` — Chiffrate (Tresor, ``ACCOUNTI_SCHLUESSEL``), je Name eines;
  veränderlich (Setzen ersetzt, Entfernen löscht).

Die JSON-Spalten sind Text; Lesen und Schreiben geht über ``repo_einstellungen``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Connection,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from accounti.db import Base
from accounti.db.schutz import nur_anfuegen_sql
from accounti.db.tabellen import UnveraenderbarError

QUELLEN = ("browser", "cli", "assistent", "datei_uebernahme", "antrag")
ANTRAGSSTATUS = ("offen", "bestaetigt", "abgelehnt", "abgelaufen", "veraltet")
TRIGGER_TEXT = "Die Einstellungsversion"
# eindeutige Schlüssel von ``einstellungen`` — der SQLite-Trigger gegen ``REPLACE``
# prüft jeden (``db/schutz.py``; Strukturtest gegen die Tabelle)
EINDEUTIG = (("id",), ("abschnitt", "version"), ("hash",))


class EinstellungRow(Base):
    """Eine Version eines Abschnitts — nur anfügen."""

    __tablename__ = "einstellungen"
    __table_args__ = (
        UniqueConstraint("abschnitt", "version", name="uq_einstellungen_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    abschnitt: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    daten: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer)
    vollstaendig: Mapped[bool] = mapped_column(Boolean)
    fehlend: Mapped[str] = mapped_column(Text)
    person: Mapped[str] = mapped_column(String(100))
    grund: Mapped[str] = mapped_column(String(500))
    quelle: Mapped[str] = mapped_column(String(20))
    antrag_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datei_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))


class EinstellungsantragRow(Base):
    """Antrag auf eine Änderung, die eine zweite Person bestätigt (K3)."""

    __tablename__ = "einstellungsantraege"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aenderungen: Mapped[str] = mapped_column(Text)  # JSON: Abschnitt, Basis, Daten
    inhalt_hash: Mapped[str] = mapped_column(String(64))
    grund: Mapped[str] = mapped_column(String(500))
    antragsteller: Mapped[str] = mapped_column(String(100))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    gueltig_bis: Mapped[datetime] = mapped_column(DateTime)
    kontrolle: Mapped[str] = mapped_column(String(40))
    recht: Mapped[str] = mapped_column(String(40))
    felder: Mapped[str] = mapped_column(Text)  # JSON-Liste der Feldpfade
    status: Mapped[str] = mapped_column(String(20), index=True)
    entschieden_von: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entschieden_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entscheidungsgrund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    versionen: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class GeheimnisRow(Base):
    """Ein Geheimnis als Chiffrat (gebunden an ``<kuerzel>:<name>``)."""

    __tablename__ = "geheimnisse"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    chiffrat: Mapped[str] = mapped_column(Text)
    gesetzt_am: Mapped[datetime] = mapped_column(DateTime)
    gesetzt_von: Mapped[str] = mapped_column(String(100))


@event.listens_for(EinstellungRow, "before_update")
@event.listens_for(EinstellungRow, "before_delete")
def _version_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError(
        "Einstellungsversionen sind unveränderbar — eine Änderung ist eine neue Version"
    )


@event.listens_for(EinstellungsantragRow, "before_delete")
def _antrag_nie_loeschen(*_: object) -> None:
    raise UnveraenderbarError("Ein Antrag wird nicht gelöscht — ablehnen oder ablaufen")


_ENTSCHEIDUNG = frozenset(
    {"status", "entschieden_von", "entschieden_am", "entscheidungsgrund", "versionen"}
)


@event.listens_for(EinstellungsantragRow, "before_update")
def _antrag_nur_entscheiden(_: Mapper[Any], verbindung: Connection, ziel: Any) -> None:
    """Erlaubt ist genau ein Weg: aus „offen“ in einen der anderen Status, dabei nur
    Status und Entscheidungsfelder."""
    t = EinstellungsantragRow.__table__
    zustand: Any = inspect(ziel)
    schluessel = zustand.identity[0] if zustand.identity else ziel.id
    gespeichert = (
        verbindung.execute(select(t).where(t.c.id == schluessel)).mappings().first()
    )
    if gespeichert is None:  # pragma: no cover — Zeile verschwunden
        return
    neu = {k: zustand.dict.get(k) for k in zustand.committed_state}
    geaendert = {k for k, w in neu.items() if k in t.c and w != gespeichert[k]}
    if not geaendert:
        return
    if gespeichert["status"] != "offen":
        raise UnveraenderbarError(
            f"Antrag {gespeichert['id']} ist nicht mehr offen "
            f"({gespeichert['status']}) — nicht mehr änderbar"
        )
    status = neu.get("status", gespeichert["status"])
    if geaendert - _ENTSCHEIDUNG or status not in ANTRAGSSTATUS or status == "offen":
        felder = ", ".join(sorted(geaendert))
        raise UnveraenderbarError(
            f"Antrag {gespeichert['id']} lässt sich so nicht ändern ({felder}) — nur "
            "bestätigen, ablehnen, ablaufen oder veralten"
        )


@event.listens_for(EinstellungRow.__table__, "after_create")
def _version_trigger(_: object, verbindung: Connection, **__: object) -> None:
    for sql in nur_anfuegen_sql(
        "einstellungen", TRIGGER_TEXT, verbindung.dialect.name, eindeutig=EINDEUTIG
    ):
        verbindung.execute(sql_text(sql))
