"""Tabellen für Anmeldung, Rollen, Sitzungen und API-Token (Baustein 10).

Sie liegen in der Systemdatenbank — ohne Registry der Gesellschaften ist das die
Datenbank der einen Gesellschaft. ``auth_ereignisse`` ist nur anfügbar: das ORM
lehnt Änderungen ab, unter SQLite zusätzlich ein Trigger (``after_create``; beim
Zusammenführen gehört er wie bei ``ustid_pruefungen`` in die Migration).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Connection,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base
from accounti.db.tabellen import UnveraenderbarError


class BenutzerRow(Base):
    __tablename__ = "auth_benutzer"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    anzeigename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    passwort_hash: Mapped[str] = mapped_column(String(300))
    totp_chiffrat: Mapped[str | None] = mapped_column(String(500), nullable=True)
    totp_aktiv: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_letzter_schritt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fehlversuche: Mapped[int] = mapped_column(Integer, default=0)
    gesperrt_bis: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # CLI zählt getrennt vom Browser (eine Flut aus dem Netz sperrt die Shell nicht)
    cli_fehlversuche: Mapped[int] = mapped_column(Integer, default=0)
    cli_gesperrt_bis: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    angelegt_am: Mapped[datetime] = mapped_column(DateTime)
    passwort_geaendert_am: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    letzte_anmeldung_am: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class RollenzuordnungRow(Base):
    __tablename__ = "auth_rollen"
    __table_args__ = (
        UniqueConstraint("benutzer_id", "gesellschaft", "rolle", name="uq_auth_rolle"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    benutzer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("auth_benutzer.id"), index=True
    )
    gesellschaft: Mapped[str] = mapped_column(String(30))
    rolle: Mapped[str] = mapped_column(String(20))


class WiederherstellungscodeRow(Base):
    __tablename__ = "auth_wiederherstellungscodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    benutzer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("auth_benutzer.id"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(300))
    angelegt_am: Mapped[datetime] = mapped_column(DateTime)
    verbraucht_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SitzungRow(Base):
    __tablename__ = "auth_sitzungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    benutzer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("auth_benutzer.id"), index=True
    )
    gesellschaft: Mapped[str] = mapped_column(String(30))
    angelegt_am: Mapped[datetime] = mapped_column(DateTime)
    zuletzt_aktiv_am: Mapped[datetime] = mapped_column(DateTime)
    laeuft_ab_am: Mapped[datetime] = mapped_column(DateTime)
    beendet_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApiTokenRow(Base):
    """Widerrufene Token bleiben stehen; eindeutig ist der Name nur unter den
    aktiven einer Gesellschaft (wie bei den Webhook-Token; Befund Betrieb B9 —
    vorher über alle Gesellschaften, Migration ``6d38d11fc348``)."""

    __tablename__ = "api_tokens"
    __table_args__ = (
        Index(
            "uq_api_token_aktiv",
            "gesellschaft",
            "name",
            unique=True,
            sqlite_where=text("widerrufen_am IS NULL"),
            postgresql_where=text("widerrufen_am IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    gesellschaft: Mapped[str] = mapped_column(String(30))
    rechte: Mapped[list[str]] = mapped_column(JSON)
    angelegt_von: Mapped[str] = mapped_column(String(50))
    angelegt_am: Mapped[datetime] = mapped_column(DateTime)
    gueltig_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    widerrufen_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zuletzt_genutzt_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthMerkerRow(Base):
    """Kleine Merker der Benutzerverwaltung — in der Systemdatenbank deren Kennung
    (``systemkennung``), in jeder Gesellschafts-Datenbank, zu welcher
    Systemdatenbank und Gesellschaft sie gehört (``benutzerverwaltung``)."""

    __tablename__ = "auth_merker"

    schluessel: Mapped[str] = mapped_column(String(40), primary_key=True)
    wert: Mapped[str] = mapped_column(String(500))
    gesetzt_am: Mapped[datetime] = mapped_column(DateTime)


class AuthEreignisRow(Base):
    __tablename__ = "auth_ereignisse"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime, index=True)
    art: Mapped[str] = mapped_column(String(40))
    benutzer: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    gesellschaft: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quelle: Mapped[str] = mapped_column(String(10))
    ok: Mapped[bool] = mapped_column(Boolean)
    hinweis: Mapped[str | None] = mapped_column(String(500), nullable=True)


@event.listens_for(AuthEreignisRow, "before_update")
@event.listens_for(AuthEreignisRow, "before_delete")
def _ereignisse_nur_anfuegen(*_: object) -> None:
    msg = "Das Anmeldeprotokoll ist unveränderbar — Einträge nur anfügen"
    raise UnveraenderbarError(msg)


# SQLite sperrt auch rohes SQL; Postgres verlässt sich auf die ORM-Sperre.
EREIGNIS_TRIGGER = [
    f"CREATE TRIGGER auth_ereignisse_kein_{aktion.lower()} BEFORE {aktion} "
    "ON auth_ereignisse BEGIN "
    "SELECT RAISE(ABORT, 'Anmeldeprotokoll ist unveränderbar'); END"
    for aktion in ("UPDATE", "DELETE")
]


@event.listens_for(AuthEreignisRow.__table__, "after_create")
def _ereignis_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in EREIGNIS_TRIGGER:
            verbindung.execute(text(sql))
