"""Domänenmodelle für Kreditkarten (Baustein 5, Paket 3).

Eine Kreditkarte ist ein eigenes Bankkonto (``Bankkonto``) mit eigenem Sachkonto;
``Kreditkarte`` ergänzt, wo ihre Sammelbelastung herkommt. Eine
``Kreditkartenabrechnung`` fasst die Einzelumsätze eines Abrechnungszeitraums
zusammen und hält fest, ob die Belastung auf dem Girokonto dazu passt.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Kreditkarte(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    bankkonto_id: UUID = Field(description="Kartenkonto mit eigenem Sachkonto")
    girokonto_id: UUID = Field(description="Konto, auf dem die Sammelbelastung liegt")
    endziffern: str | None = Field(
        default=None, description="letzte Ziffern der Kartennummer — nie die ganze"
    )
    muster: str | None = Field(
        default=None, description="eigenes Muster für die Sammelbelastung (Regex)"
    )
    abrechnungstag: int | None = Field(
        default=None, ge=1, le=31, description="Stichtag der Monatsabrechnung"
    )
    erstellt_am: datetime = Field(default_factory=datetime.now)


class AbrechnungStatus(str, enum.Enum):
    OFFEN = "offen"  # Belastung auf dem Girokonto noch nicht gefunden
    ABGEGLICHEN = "abgeglichen"  # Belastung = Summe der Einzelumsätze, centgenau
    ABWEICHUNG = "abweichung"  # Befund — kein Rundungsposten


class Kreditkartenabrechnung(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kreditkarte_id: UUID
    stichtag: date = Field(description="Abrechnungsdatum")
    von: date | None = Field(default=None, description="erster Tag des Zeitraums")
    beleg_id: UUID | None = Field(default=None, description="PDF-Abrechnung")
    summe: Decimal = Field(description="Summe der Einzelumsätze, Belastung negativ")
    anzahl: int = Field(ge=0)
    belastung_id: UUID | None = Field(
        default=None, description="Sammelbelastung auf dem Girokonto"
    )
    belastung_betrag: Decimal | None = None
    status: AbrechnungStatus = AbrechnungStatus.OFFEN
    befund: str | None = None
    erstellt_am: datetime = Field(default_factory=datetime.now)

    @property
    def differenz(self) -> Decimal | None:
        """Belastung minus Summe — bei ``abgeglichen`` immer 0."""
        if self.belastung_betrag is None:
            return None
        return self.belastung_betrag - self.summe
