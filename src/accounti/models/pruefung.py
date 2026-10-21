"""Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7) — Domänenmodelle.

* **Journaleintrag** — ein buchungsrelevanter Vorgang im hash-verketteten, nur
  anfügbaren Journal (GoBD Rz. 58 f., 107 ff.; § 146 Abs. 4 AO).
* **Buchungskorrektur** — Storno einer freigegebenen Buchung, optional mit Neubuchung;
  verbindet Original, Storno und Neubuchung (GoBD Rz. 64: rückbeziehbar).
* **Periodenabschluss** — ein festgeschriebener Monat.
* **Befund** — was eine Prüfregel feststellt; Prüfregeln ändern nie Daten.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Journaleintrag(BaseModel):
    """Ein Eintrag im Journal — laufende Nummer, Person, Vorgang, Vorher/Nachher."""

    nr: int = 0
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    person: str
    vorgang: str = Field(description="z.B. buchung_angelegt, buchung_storniert")
    objekt_typ: str = Field(description="buchung, beleg, zahlungslauf, periode …")
    objekt_id: str
    vorher: str | None = Field(default=None, description="kanonisches JSON")
    nachher: str | None = Field(default=None, description="kanonisches JSON")
    grund: str | None = None
    bezug: str | None = Field(default=None, description="z.B. Storno ↔ Original")
    vorgaenger_hash: str = ""
    hash: str = ""


class Buchungskorrektur(BaseModel):
    """Storno einer freigegebenen Buchung, mit oder ohne Neubuchung."""

    id: UUID = Field(default_factory=uuid4)
    original_id: UUID
    storno_id: UUID
    neubuchung_id: UUID | None = None
    datum: date = Field(description="Datum von Storno und Neubuchung")
    grund: str
    person: str
    zeitpunkt: datetime = Field(default_factory=datetime.now)


class Periodenabschluss(BaseModel):
    """Ein Monat, der festgeschrieben ist (oder wieder geöffnet wurde)."""

    monat: str = Field(description="JJJJ-MM")
    gesperrt: bool
    geschlossen_am: datetime
    geschlossen_von: str
    geoeffnet_am: datetime | None = None
    geoeffnet_von: str | None = None
    grund: str | None = Field(default=None, description="Grund des letzten Öffnens")


class Schwere(str, enum.Enum):
    HINWEIS = "hinweis"
    WARNUNG = "warnung"
    FEHLER = "fehler"

    @property
    def rang(self) -> int:
        return {"hinweis": 0, "warnung": 1, "fehler": 2}[self.value]


class Kategorie(str, enum.Enum):
    VOLLSTAENDIGKEIT = "vollstaendigkeit"
    RICHTIGKEIT = "richtigkeit"
    ZEITGERECHTHEIT = "zeitgerechtheit"
    ORDNUNG = "ordnung"


class Befund(BaseModel):
    """Eine Feststellung einer Prüfregel — mit Begründung im Klartext."""

    regel: str
    kategorie: Kategorie
    schwere: Schwere
    objekt_typ: str = Field(description="transaktion, beleg, buchung, posten …")
    objekt_id: str
    text: str = Field(description="Begründung im Klartext")
    datum: date | None = None
    betrag: Decimal | None = None
    gegenpartei: str | None = None
    abhilfe: str | None = None
