"""Jahresabschluss (Baustein 12) — Kontoauszugssalden, Abgrenzungen, Abschlüsse."""

from __future__ import annotations

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
