"""Kassenbuch (Baustein 12) — ein Eintrag je Bargeschäft, nur anfügen."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Kassenart(str, enum.Enum):
    ANFANGSBESTAND = "anfangsbestand"
    EINNAHME = "einnahme"
    AUSGABE = "ausgabe"
    STORNO = "storno"


class Kassenvorgang(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nr: int = Field(default=0, description="laufende Nummer, vergibt das Kassenbuch")
    datum: date
    betrag: Decimal = Field(description="Einnahme positiv, Ausgabe negativ")
    art: Kassenart
    text: str
    belegnummer: str | None = None
    gegenkonto: str | None = None
    steuersatz: Decimal | None = Field(default=None, description="in Prozent")
    transaktion_id: UUID | None = None
    buchung_id: UUID | None = None
    storno_von: int | None = Field(default=None, description="Nr. des stornierten")
    erfasst_am: datetime = Field(default_factory=datetime.now)
    erfasst_von: str | None = None
