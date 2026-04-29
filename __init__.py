"""accounti Datenmodell — die zentralen Entitäten der Buchhaltungspipeline."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Kontenrahmen(str, enum.Enum):
    """Unterstützte Kontenrahmen."""

    SKR03 = "SKR03"
    SKR04 = "SKR04"


class TransaktionQuelle(str, enum.Enum):
    """Herkunft einer Transaktion."""

    BANK = "bank"
    JTL_WAWI = "jtl_wawi"
    AMAZON = "amazon"
    EBAY = "ebay"
    SHOPIFY = "shopify"
    PAYPAL = "paypal"
    MANUELL = "manuell"


class BuchungStatus(str, enum.Enum):
    """Status eines Buchungssatzes in der Pipeline."""

    ENTWURF = "entwurf"          # Vom System vorgeschlagen
    AUTO_GEBUCHT = "auto"        # Automatisch gebucht (hohe Confidence)
    ZUR_PRUEFUNG = "pruefung"    # Muss vom Supervisor geprüft werden
    GEPRUEFT = "geprueft"        # Vom Supervisor bestätigt
    KORRIGIERT = "korrigiert"    # Vom Supervisor korrigiert
    EXPORTIERT = "exportiert"    # In DATEV exportiert


# ---------------------------------------------------------------------------
# Transaktion — Rohdaten aus Import
# ---------------------------------------------------------------------------


class Transaktion(BaseModel):
    """Eine importierte Transaktion (Bankbuchung, ERP-Vorgang, etc.)."""

    id: UUID = Field(default_factory=uuid4)
    datum: date
    betrag: Decimal = Field(description="Positiv = Einnahme, Negativ = Ausgabe")
    waehrung: str = Field(default="EUR", max_length=3)
    verwendungszweck: str
    gegenkonto_name: str | None = Field(default=None, description="Name des Kontoinhabers")
    gegenkonto_iban: str | None = None
    quelle: TransaktionQuelle
    quelle_referenz: str | None = Field(default=None, description="z.B. JTL-Rechnungsnummer")
    rohtext: str = Field(description="Originalzeile aus Import, für Debugging")
    importiert_am: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Konto — aus Kontenrahmen (SKR03/SKR04)
# ---------------------------------------------------------------------------


class Konto(BaseModel):
    """Ein Konto aus dem Kontenrahmen."""

    nummer: str = Field(description="z.B. '8400' oder '4970'")
    name: str = Field(description="z.B. 'Erlöse 19% USt'")
    typ: str = Field(description="aktiv, passiv, erloes, aufwand")
    kontenrahmen: Kontenrahmen
    bwa_zeile: int | None = Field(default=None, description="Zuordnung zur BWA-Zeile")
    steuer_schluessel: int | None = Field(default=None, description="DATEV-Steuerschlüssel")
    steuer_automatik: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Buchungssatz — das Herzstück
# ---------------------------------------------------------------------------


class Buchungssatz(BaseModel):
    """Ein vollständiger Buchungssatz (Soll an Haben)."""

    id: UUID = Field(default_factory=uuid4)
    transaktion_id: UUID
    datum: date
    soll_konto: str = Field(description="Kontonummer Soll-Seite")
    haben_konto: str = Field(description="Kontonummer Haben-Seite")
    betrag_netto: Decimal
    steuer_schluessel: int | None = None
    steuer_betrag: Decimal | None = None
    buchungstext: str = Field(description="Kurztext für den Buchungssatz")
    beleg_nummer: str | None = None
    kostenstelle: str | None = None
    status: BuchungStatus = Field(default=BuchungStatus.ENTWURF)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence der KI-Klassifikation (0.0-1.0)",
    )
    erstellt_am: datetime = Field(default_factory=datetime.now)
    geprueft_am: datetime | None = None
    geprueft_von: str | None = None


# ---------------------------------------------------------------------------
# Klassifikationsergebnis — Ausgabe der KI-Engine
# ---------------------------------------------------------------------------


class Klassifikationsergebnis(BaseModel):
    """Ergebnis der KI-Kontierung für eine Transaktion."""

    transaktion_id: UUID
    soll_konto: str
    haben_konto: str
    steuer_schluessel: int | None = None
    buchungstext: str
    confidence: float = Field(ge=0.0, le=1.0)
    begruendung: str = Field(description="Erklärung der KI warum dieses Konto gewählt wurde")
    quelle: str = Field(description="'regelwerk' oder 'llm'")


# ---------------------------------------------------------------------------
# BWA-Zeile
# ---------------------------------------------------------------------------


class BWAZeile(BaseModel):
    """Eine Zeile der Betriebswirtschaftlichen Auswertung."""

    nummer: int
    bezeichnung: str
    betrag_aktuell: Decimal = Field(default=Decimal("0.00"))
    betrag_vorjahr: Decimal | None = None
    betrag_kumuliert: Decimal = Field(default=Decimal("0.00"))


class BWA(BaseModel):
    """Vollständige Betriebswirtschaftliche Auswertung."""

    mandant: str
    zeitraum: str = Field(description="z.B. '2026-04'")
    kontenrahmen: Kontenrahmen
    zeilen: list[BWAZeile] = Field(default_factory=list)
    erstellt_am: datetime = Field(default_factory=datetime.now)
