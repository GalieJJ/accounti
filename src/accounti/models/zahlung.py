"""Zahlungsverkehr (Baustein 6): Zahlungsläufe, Zahlungen, Protokoll, Sperren."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class LaufStatus(str, enum.Enum):
    """Zustand eines Zahlungslaufs — Übergänge regelt ``accounti.zahlung.freigabe``."""

    ENTWURF = "entwurf"  # frei änderbar
    FREIGEGEBEN = "freigegeben"  # unveränderbar, Datei darf erzeugt werden
    EINGEREICHT = "eingereicht"  # Datei erzeugt — Geld kann fließen
    AUSGEFUEHRT = "ausgefuehrt"  # alle Posten durch Bankumsätze ausgeglichen
    STORNIERT = "storniert"  # verworfen, Posten wieder frei


AKTIVE_STATUS = frozenset(
    {LaufStatus.ENTWURF, LaufStatus.FREIGEGEBEN, LaufStatus.EINGEREICHT}
)


class Zahlung(BaseModel):
    """Eine Überweisung im Lauf — eingefroren, wie sie freigegeben wird."""

    id: UUID = Field(default_factory=uuid4)
    lauf_id: UUID
    nr: int = Field(description="Position im Lauf, ab 1")
    posten_id: UUID
    kontakt_id: UUID
    empfaenger: str
    iban: str
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = None
    betrag: Decimal = Field(description="zu überweisen, nach Skonto")
    skonto: Decimal = Field(default=Decimal("0.00"), description="abgezogen")
    restbetrag_vorher: Decimal = Field(description="Rest des Postens bei der Anlage")
    verwendungszweck: str
    end_to_end_id: str
    belegnummer: str | None = None
    belegdatum: date | None = None
    grund: str = Field(description="warum vorgeschlagen")


class Zahlungslauf(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nr: int = 0
    status: LaufStatus = LaufStatus.ENTWURF
    stichtag: date
    ausfuehrung: date = Field(description="gewünschter Ausführungstag")
    auftraggeber_name: str
    auftraggeber_iban: str
    auftraggeber_bic: str | None = None
    erstellt_am: datetime = Field(default_factory=datetime.now)
    erstellt_von: str
    freigabe_hash: str | None = None
    msg_id: str | None = None
    datei: str | None = Field(default=None, description="pain.001 wie eingereicht")
    datei_hash: str | None = None
    eingereicht_am: datetime | None = None
    zahlungen: list[Zahlung] = Field(default_factory=list)

    @property
    def summe(self) -> Decimal:
        return sum((z.betrag for z in self.zahlungen), Decimal("0.00"))

    @property
    def skonto(self) -> Decimal:
        return sum((z.skonto for z in self.zahlungen), Decimal("0.00"))


class LaufProtokoll(BaseModel):
    """Eintrag im Protokoll eines Zahlungslaufs — nur anfügen."""

    id: UUID = Field(default_factory=uuid4)
    lauf_id: UUID
    nr: int = 0
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    person: str
    aktion: str = Field(description="angelegt, entfernt, freigabe, storniert, …")
    von_status: LaufStatus | None = None
    nach_status: LaufStatus | None = None
    text: str = ""


class Zahlungssperre(BaseModel):
    """Sperrvermerk: an diesen Kontakt wird nichts überwiesen."""

    kontakt_id: UUID
    grund: str
    gesetzt_am: datetime = Field(default_factory=datetime.now)
    gesetzt_von: str


class IbanKlaerung(BaseModel):
    """Ein Mensch hat geklärt: trotz anderer IBAN auf der Rechnung an den Stammsatz."""

    id: UUID = Field(default_factory=uuid4)
    posten_id: UUID
    rechnungs_iban: str
    stammsatz_iban: str
    grund: str
    person: str
    zeitpunkt: datetime = Field(default_factory=datetime.now)
