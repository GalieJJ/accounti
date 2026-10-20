"""Tabellen für Aufgaben & Rückfragen (Baustein 8)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class AufgabeRow(Base):
    __tablename__ = "aufgaben"
    __table_args__ = (Index("ix_aufgaben_objekt", "objekt_typ", "objekt_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nr: Mapped[int] = mapped_column(Integer, unique=True)
    # Idempotenz: eine Aufgabe je (Art, Objekt) — auch bei parallelen Läufen
    schluessel: Mapped[str] = mapped_column(String(200), unique=True)
    art: Mapped[str] = mapped_column(String(40), index=True)
    titel: Mapped[str] = mapped_column(String(200))
    beschreibung: Mapped[str] = mapped_column(Text)
    objekt_typ: Mapped[str] = mapped_column(String(40))
    objekt_id: Mapped[str] = mapped_column(String(100))
    zustaendig: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rolle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    faellig_am: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    prioritaet: Mapped[str] = mapped_column(String(10))
    erzeugt_von: Mapped[str] = mapped_column(String(100))
    merkmale: Mapped[str] = mapped_column(Text)  # JSON
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    aktualisiert_am: Mapped[datetime] = mapped_column(DateTime)
    quittiert_von: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erledigt_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    abschluss_grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erinnerungsstufe: Mapped[int] = mapped_column(Integer, default=0)
    gemeldet_am: Mapped[date | None] = mapped_column(Date, nullable=True)
    # jede Änderung zählt hoch; geschrieben wird nur, wenn sie seit dem Lesen gleich
    # blieb — ein Lauf überschreibt so kein „erledigt“, das ein Mensch gerade setzte
    version: Mapped[int] = mapped_column(Integer, default=0)


class KommentarRow(Base):
    """Kommentare, Rückfragen und Verlauf — nur anfügen."""

    __tablename__ = "aufgaben_kommentare"
    __table_args__ = (
        Index("ix_aufgaben_kommentare_objekt", "objekt_typ", "objekt_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aufgabe_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("aufgaben.id"), nullable=True, index=True
    )
    objekt_typ: Mapped[str | None] = mapped_column(String(40), nullable=True)
    objekt_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    art: Mapped[str] = mapped_column(String(20))
    autor: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, index=True)
    anhang_beleg_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


@event.listens_for(KommentarRow, "before_update")
@event.listens_for(KommentarRow, "before_delete")
def _verlauf_nur_anfuegen(*_: object) -> None:
    msg = "Kommentare und Verlauf sind unveränderbar — nur neue Einträge anfügen"
    raise UnveraenderbarError(msg)


class BenachrichtigungRow(Base):
    """Protokoll der Tagesübersichten je Empfänger, Kanal und Tag."""

    __tablename__ = "aufgaben_benachrichtigungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tag: Mapped[date] = mapped_column(Date, index=True)
    empfaenger: Mapped[str] = mapped_column(String(100))
    kanal: Mapped[str] = mapped_column(String(20))
    adresse: Mapped[str | None] = mapped_column(String(500), nullable=True)
    aufgaben: Mapped[str] = mapped_column(Text)  # JSON-Liste der Nummern
    erfolgreich: Mapped[bool] = mapped_column(Boolean)
    fehler: Mapped[str | None] = mapped_column(Text, nullable=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
