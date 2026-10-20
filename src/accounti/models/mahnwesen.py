"""Mahnwesen (Baustein 6): Mahnungen mit Zinsabschnitten, Einstellungen je Kontakt."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MahnungStatus(str, enum.Enum):
    ENTWURF = "entwurf"  # berechnet, noch nicht verschickt — zählt nicht
    VERSENDET = "versendet"  # Mahnstufe am Posten hochgezählt, unveränderbar
    VERWORFEN = "verworfen"


class Zinsabschnitt(BaseModel):
    """Zeitraum mit gleichem Kapital und gleichem Zinssatz."""

    von: date
    bis: date  # einschließlich
    tage: int
    kapital: Decimal
    basiszins: Decimal
    satz: Decimal  # Basiszinssatz + Aufschlag, Prozent im Jahr
    zinsen: Decimal  # auf Cent gerundet


class Mahnung(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nr: int = 0
    posten_id: UUID
    kontakt_id: UUID
    stufe: int = Field(description="1 = erste konfigurierte Stufe")
    stufe_name: str
    datum: date = Field(description="Mahndatum = Stichtag des Laufs")
    belegnummer: str | None = None
    belegdatum: date
    faellig_am: date
    rechnungsbetrag: Decimal
    restbetrag: Decimal
    verzug_ab: date | None = Field(default=None, description="erster Zinstag")
    verzug_grund: str | None = Field(
        default=None, description="warum ab da Verzug (§ 286 BGB)"
    )
    zinsen: Decimal = Decimal("0.00")
    zinsabschnitte: list[Zinsabschnitt] = Field(default_factory=list)
    gebuehren_kumuliert: Decimal = Field(
        default=Decimal("0.00"), description="Summe der Stufengebühren bis hier"
    )
    gebuehren: Decimal = Field(
        default=Decimal("0.00"), description="verlangt — nach Anrechnung"
    )
    pauschale: Decimal = Decimal("0.00")
    summe: Decimal
    zahlungsfrist: date
    unternehmer: bool
    einstufung: str = Field(description="warum B2B oder B2C")
    status: MahnungStatus = MahnungStatus.ENTWURF
    versendet_am: datetime | None = None
    versand_weg: str | None = Field(default=None, description="pdf, text, email")
    datei_hash: str | None = Field(default=None, description="PDF im Belegarchiv")
    erstellt_am: datetime = Field(default_factory=datetime.now)


class MahnKontakt(BaseModel):
    """Mahnsperre und B2B/B2C-Einstufung eines Kunden."""

    kontakt_id: UUID
    mahnsperre: bool = False
    sperrgrund: str | None = None
    unternehmer: bool | None = Field(
        default=None, description="None = nicht eingestuft"
    )
