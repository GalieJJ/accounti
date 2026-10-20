"""Anlagenbuchhaltung (Baustein 12) — Anlagegüter und ihre AfA-Vorgänge."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AfaArt(str, enum.Enum):
    """Wie ein Anlagegut abgeschrieben wird."""

    LINEAR = "linear"  # § 7 Abs. 1 EStG, zeitanteilig nach Monaten
    DEGRESSIV = "degressiv"  # § 7 Abs. 2 EStG, nur in den gesetzlichen Fenstern
    GWG = "gwg"  # § 6 Abs. 2 EStG, Sofortabzug
    SAMMELPOSTEN = "sammelposten"  # § 6 Abs. 2a EStG, 1/5 je Jahr
    DIGITAL = "digital"  # Computerhardware/Software, ND 1 Jahr (BMF 22.02.2022)
    E_FAHRZEUG = "e_fahrzeug"  # § 7 Abs. 2a EStG, feste Staffel
    KEINE = "keine"  # nicht abnutzbar (Grund und Boden, Finanzanlagen)


class AbgangArt(str, enum.Enum):
    VERKAUF = "verkauf"
    ENTNAHME = "entnahme"
    VERSCHROTTUNG = "verschrottung"


class Anlagegut(BaseModel):
    """Ein Wirtschaftsgut des Anlagevermögens.

    Die Anschaffungskosten sind netto (ohne abziehbare Vorsteuer, § 9b EStG) — daran
    messen sich GWG- und Sammelpostengrenze. Der Restbuchwert wird aus dem AfA-Plan
    berechnet, nicht gespeichert.
    """

    id: UUID = Field(default_factory=uuid4)
    nr: int = Field(default=0, description="Inventarnummer, vergibt das Repository")
    bezeichnung: str
    konto: str = Field(description="Anlagekonto, z.B. 0420")
    afa_konto: str | None = Field(
        default=None, description="Aufwandskonto; sonst aus den Einstellungen"
    )
    anschaffungsdatum: date
    anschaffungskosten: Decimal = Field(gt=0, description="netto")
    nutzungsdauer: int | None = Field(default=None, ge=1, description="in Jahren")
    afa_art: AfaArt
    wechsel_linear: bool = Field(
        default=True, description="degressiv: Übergang zur linearen AfA (§ 7 Abs. 3)"
    )
    immateriell: bool = False
    beleg_id: UUID | None = None
    typ: str | None = Field(default=None, description="Schlüssel der AfA-Tabelle")
    abgang_datum: date | None = None
    abgang_art: AbgangArt | None = None
    abgang_erloes: Decimal | None = Field(default=None, description="netto")
    notiz: str | None = None
    erstellt_am: datetime = Field(default_factory=datetime.now)

    @property
    def objekt(self) -> str:
        """Schlüssel, unter dem die AfA-Vorgänge dieses Anlageguts stehen."""
        return f"anlage:{self.id}"


def sammelposten_objekt(konto: str, jahr: int) -> str:
    """Schlüssel eines Sammelpostens (je Anlagekonto und Anschaffungsjahr)."""
    return f"sammelposten:{konto}:{jahr}"


class AfaVorgang(BaseModel):
    """Eine gebuchte AfA (oder Korrektur) für ein Anlagegut oder einen Sammelposten."""

    id: UUID = Field(default_factory=uuid4)
    objekt: str = Field(description="anlage:<id> oder sammelposten:<konto>:<jahr>")
    anlage_id: UUID | None = None
    jahr: int
    bis_monat: int = Field(ge=1, le=12)
    betrag: Decimal = Field(description="negativ bei einer Korrektur")
    buchung_id: UUID | None = None
    begruendung: str
    erstellt_am: datetime = Field(default_factory=datetime.now)
