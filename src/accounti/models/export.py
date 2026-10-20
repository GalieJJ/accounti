"""Domänenmodelle für Exporte (Baustein 11): festgeschriebene Kontoauszüge.

Ein *Kontoauszug* fasst die Umsätze eines Finanzkontos (Bank, PayPal) für einen
Kalendermonat zusammen. Auszüge sind je Finanzkonto und Jahr ab 1 lückenlos nummeriert,
jeder beginnt mit dem Endsaldo seines Vorgängers. Einmal erstellt, ändert sich ein
Auszug nicht mehr: Umsätze, die später für einen abgeschlossenen Monat eintreffen,
kommen als *Nachtrag* in den nächsten Auszug. Eine Hash-Kette über alle Auszüge eines
Finanzkontos macht nachträgliche Änderungen sichtbar.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Kontoauszug(BaseModel):
    """Ein festgeschriebener Monatsauszug eines Finanzkontos."""

    id: UUID = Field(default_factory=uuid4)
    finanzkonto: str = Field(description="Sachkonto, z.B. 1200 (Bank) oder 1210")
    jahr: int
    nummer: int = Field(ge=1, description="je Finanzkonto und Jahr ab 1 lückenlos")
    von: date
    bis: date
    waehrung: str = Field(default="EUR", max_length=3)
    anfangssaldo: Decimal
    endsaldo: Decimal
    umsaetze: list[UUID] = Field(
        default_factory=list, description="Transaktionen in Auszugsreihenfolge"
    )
    nachtraege: list[UUID] = Field(
        default_factory=list,
        description="Teilmenge von umsaetze: Umsätze eines früheren Monats",
    )
    kontrollsaldo: Decimal | None = Field(
        default=None, description="Saldo laut Bank zum Monatsende, falls angegeben"
    )
    erstellt_am: datetime = Field(default_factory=datetime.now)
    vorgaenger_hash: str = ""
    hash: str = ""


class Auszugsbefund(BaseModel):
    """Eine Feststellung zu Kontoauszügen — Grundlage für Baustein 7."""

    code: str = Field(
        description="nachtrag, vor_beginn, fremdwaehrung, luecke, nummer, "
        "saldensprung, summe, hash, umsatz_fehlt, kontrollsaldo"
    )
    text: str
    finanzkonto: str | None = None
    nummer: int | None = None
    jahr: int | None = None
