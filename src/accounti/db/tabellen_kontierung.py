"""Tabellen für Herkunft und gelernte Regeln (Baustein 10b).

* ``kontierungsgruende`` — nur anfügen: Ändern und Löschen scheitern am ORM, unter
  SQLite zusätzlich an Triggern (``after_create`` und Migration). ``buchung_id`` ist
  indiziert, aber **ohne** Fremdschlüssel: Der Kreditkartenabgleich löscht vorläufige
  Buchungen wieder (``repo_bank.loesche_buchung``) — der Grund bleibt dann wie ein
  Journaleintrag zur verworfenen Buchung stehen.
* ``kontierungsregeln`` — gelernte Regeln der Gesellschaft. Gelöscht wird nie, geändert
  nur ``aktiv`` von an nach aus samt ``deaktiviert_*``. Anlage und Deaktivierung stehen
  im Journal (``pruefung.ereignisse``), der Bestand wird mit dem Journal abgeglichen
  (``journal.BESTAND``) — eine an accounti vorbei geänderte Regel meldet
  ``accounti journal pruefen``.

Beide Tabellen stehen in ``db.GESCHUETZT`` (keine Massenwege über das ORM).
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
    event,
    inspect,
    select,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class KontierungsgrundRow(Base):
    """Herkunft und Begründung eines Buchungsvorschlags — nur anfügen."""

    __tablename__ = "kontierungsgruende"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    buchung_id: Mapped[str] = mapped_column(String(36), index=True)
    quelle: Mapped[str] = mapped_column(String(20))
    regel: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    modell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    begruendung: Mapped[str] = mapped_column(String(500))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)


class KontierungsregelRow(Base):
    """Gelernte Kontierungsregel — nur deaktivierbar."""

    __tablename__ = "kontierungsregeln"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    muster: Mapped[str] = mapped_column(String(200))
    ist_text: Mapped[bool] = mapped_column(Boolean)
    feld: Mapped[str] = mapped_column(String(20))
    richtung: Mapped[str | None] = mapped_column(String(10), nullable=True)
    soll_konto: Mapped[str] = mapped_column(String(10))
    haben_konto: Mapped[str] = mapped_column(String(10))
    steuer_schluessel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buchungstext: Mapped[str | None] = mapped_column(String(60), nullable=True)
    quelle_buchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    herkunft: Mapped[str] = mapped_column(String(20))
    # Stelle in der Regeldatei (nur ``uebernahme``) — Vorrang untereinander
    rang: Mapped[int | None] = mapped_column(Integer, nullable=True)
    angelegt_von: Mapped[str] = mapped_column(String(100))
    angelegt_am: Mapped[datetime] = mapped_column(DateTime)
    aktiv: Mapped[bool] = mapped_column(Boolean, index=True)
    deaktiviert_von: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deaktiviert_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deaktiviert_grund: Mapped[str | None] = mapped_column(String(500), nullable=True)


@event.listens_for(KontierungsgrundRow, "before_update")
@event.listens_for(KontierungsgrundRow, "before_delete")
def _grund_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError("Kontierungsgründe sind unveränderbar — nur anfügen")


@event.listens_for(KontierungsregelRow, "before_delete")
def _regel_nie_loeschen(*_: object) -> None:
    raise UnveraenderbarError(
        "Gelernte Regeln werden nicht gelöscht — deaktivieren (accounti regeln "
        "deaktivieren)"
    )


_DEAKTIVIERUNG = frozenset(
    {"aktiv", "deaktiviert_von", "deaktiviert_am", "deaktiviert_grund"}
)


@event.listens_for(KontierungsregelRow, "before_update")
def _regel_nur_deaktivieren(_: Mapper[Any], verbindung: Connection, ziel: Any) -> None:
    """Erlaubt ist genau ein Weg: aktiv → aus, mit ``deaktiviert_*``."""
    t = KontierungsregelRow.__table__
    zustand: Any = inspect(ziel)
    schluessel = zustand.identity[0] if zustand.identity else ziel.id
    gespeichert = (
        verbindung.execute(select(t).where(t.c.id == schluessel)).mappings().first()
    )
    if gespeichert is None:  # pragma: no cover — Zeile verschwunden
        return
    # die in dieser Sitzung gesetzten Attribute (auch abgelaufene) mit neuem Wert
    neu = {k: zustand.dict.get(k) for k in zustand.committed_state}
    geaendert = {k for k, w in neu.items() if k in t.c and w != gespeichert[k]}
    if not geaendert:
        return
    if (
        geaendert - _DEAKTIVIERUNG
        or not gespeichert["aktiv"]
        or neu.get("aktiv", True)
        or not neu.get("deaktiviert_von")
    ):
        felder = ", ".join(sorted(geaendert))
        raise UnveraenderbarError(
            f"Gelernte Regel {gespeichert['name']} lässt sich nicht ändern ({felder}) "
            "— nur deaktivieren und neu lernen"
        )


def _trigger(tabelle: str, text: str) -> list[str]:
    return [
        f"CREATE TRIGGER IF NOT EXISTS {tabelle}_kein_{aktion.lower()} BEFORE "
        f"{aktion} ON {tabelle} BEGIN SELECT RAISE(ABORT, '{text}'); END"
        for aktion in ("UPDATE", "DELETE")
    ]


# SQLite sperrt auch rohes SQL (wie journal in tabellen_pruefung.py)
GRUND_TRIGGER = _trigger("kontierungsgruende", "Kontierungsgründe sind unveränderbar")


@event.listens_for(KontierungsgrundRow.__table__, "after_create")
def _grund_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in GRUND_TRIGGER:
            verbindung.execute(sql_text(sql))
