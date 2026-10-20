"""Jahresabschluss (Baustein 12) — Kontoauszugssalden, Abgrenzungen, Abschlüsse."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Kontoauszugssaldo(BaseModel):
    """Saldo laut Kontoauszug zu einem Stichtag — Gegenstück zum Buchbestand."""

    id: UUID = Field(default_factory=uuid4)
    bankkonto_id: UUID
    stichtag: date
    saldo: Decimal
    erfasst_am: datetime = Field(default_factory=datetime.now)
    erfasst_von: str | None = None


class AbgrenzungArt(str, enum.Enum):
    ARAP = "arap"  # Ausgabe vor dem Stichtag für Aufwand danach (aktiv)
    PRAP = "prap"  # Einnahme vor dem Stichtag für Ertrag danach (passiv)


class AbgrenzungStatus(str, enum.Enum):
    VORGESCHLAGEN = "vorgeschlagen"
    BESTAETIGT = "bestaetigt"  # Abgrenzung und Auflösung gebucht
    ABGELEHNT = "abgelehnt"


class Abgrenzung(BaseModel):
    """Vorschlag einer Rechnungsabgrenzung — mit der Auflösung im Folgejahr."""

    id: UUID = Field(default_factory=uuid4)
    nr: int = 0
    jahr: int
    buchung_id: UUID = Field(description="die abzugrenzende Buchung")
    art: AbgrenzungArt
    konto: str = Field(description="Aufwands- bzw. Ertragskonto")
    rap_konto: str
    betrag: Decimal
    von: date
    bis: date
    rechenweg: str
    status: AbgrenzungStatus = AbgrenzungStatus.VORGESCHLAGEN
    abgrenzung_buchung_id: UUID | None = None
    aufloesung_buchung_id: UUID | None = None
    erstellt_am: datetime = Field(default_factory=datetime.now)
    entschieden_am: datetime | None = None
    entschieden_von: str | None = None


class Jahresabschluss(BaseModel):
    jahr: int
    gesperrt: bool
    gewinnermittlung: str
    ergebnis: Decimal
    abgeschlossen_am: datetime
    von: str


class Protokolleintrag(BaseModel):
    """Eintrag im Abschlussprotokoll — nur anfügen, per Hash verkettet."""

    nr: int = 0
    jahr: int
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    aktion: str = Field(description="abgeschlossen, geoeffnet, eroeffnung")
    von: str
    grund: str | None = None
    details: str = Field(default="{}", description="JSON")
    vorgaenger_hash: str = ""
    hash: str = ""
