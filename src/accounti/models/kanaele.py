"""Datenmodell der Beleg-Kanäle: Gedächtnis, Webhook-Tokens, Zugänge."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AbgeholteNachricht(BaseModel):
    """Eine verarbeitete Nachricht (E-Mail, Portaldokument, Webhook-Aufruf).

    Der Schlüssel macht die Nachricht innerhalb von Kanal und Quelle eindeutig —
    bei IMAP ``Ordner:UIDVALIDITY:UID``, bei einem Portal die Dokument-ID. Der
    Absender ist ein Hinweis auf den Kreditor, keine Zuordnung.
    """

    id: UUID = Field(default_factory=uuid4)
    kanal: str
    quelle: str = Field(description="Postfach, Connector oder Tokenname")
    schluessel: str
    message_id: str | None = None
    absender: str | None = Field(default=None, description="Adresse oder Kennung")
    absender_name: str | None = None
    betreff: str | None = None
    gesendet_am: datetime | None = None
    abgeholt_am: datetime = Field(default_factory=datetime.now)
    datei_hashes: list[str] = Field(
        default_factory=list, description="aufgenommene Dateien (SHA-256)"
    )
    hinweis: str | None = Field(
        default=None, description="z.B. übersprungene Anhänge mit Grund"
    )


class WebhookToken(BaseModel):
    """Zugang eines Fremdsystems zum Webhook — gespeichert wird nur der Hash."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    token_hash: str = Field(description="SHA-256 des Tokens, hexadezimal")
    erstellt_am: datetime = Field(default_factory=datetime.now)
    widerrufen_am: datetime | None = None
    zuletzt_genutzt_am: datetime | None = None

    @property
    def aktiv(self) -> bool:
        return self.widerrufen_am is None


class KanalZugang(BaseModel):
    """Geheimnis eines Kanals (Passwort, API-Schlüssel) — nur verschlüsselt."""

    id: UUID = Field(default_factory=uuid4)
    kanal: str
    name: str
    chiffrat: str
    geaendert_am: datetime = Field(default_factory=datetime.now)
