"""Tabellen der Beleg-Kanäle (E-Mail, Webhook, Connector)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from accounti.db import Base


class KanalNachrichtRow(Base):
    """Verarbeitete Nachrichten — damit nichts zweimal abgeholt wird."""

    __tablename__ = "kanal_nachrichten"
    __table_args__ = (
        UniqueConstraint("kanal", "quelle", "schluessel", name="uq_kanal_nachricht"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kanal: Mapped[str] = mapped_column(String(20))
    quelle: Mapped[str] = mapped_column(String(100))
    schluessel: Mapped[str] = mapped_column(String(300))
    message_id: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )
    absender: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    absender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    betreff: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gesendet_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    abgeholt_am: Mapped[datetime] = mapped_column(DateTime)
    hinweis: Mapped[str | None] = mapped_column(Text, nullable=True)


class KanalNachrichtDateiRow(Base):
    """Welche Datei kam mit welcher Nachricht — Absender als Hinweis zum Beleg."""

    __tablename__ = "kanal_nachricht_dateien"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nachricht_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kanal_nachrichten.id"), index=True
    )
    nr: Mapped[int] = mapped_column(Integer)
    datei_hash: Mapped[str] = mapped_column(String(64), index=True)


class WebhookTokenRow(Base):
    __tablename__ = "webhook_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime)
    widerrufen_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zuletzt_genutzt_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KanalZugangRow(Base):
    """Geheimnisse der Kanäle, AES-GCM-verschlüsselt (accounti.bank.tresor)."""

    __tablename__ = "kanal_zugaenge"
    __table_args__ = (UniqueConstraint("kanal", "name", name="uq_kanal_zugang"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kanal: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    chiffrat: Mapped[str] = mapped_column(Text)
    geaendert_am: Mapped[datetime] = mapped_column(DateTime)
