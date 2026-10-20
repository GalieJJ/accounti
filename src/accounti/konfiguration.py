"""Konfiguration — Firmendaten (Mandant) aus ``config/accounti.yaml``.

Die Firmendaten braucht jede Ausgangsrechnung: XRechnung verlangt Anschrift, Kontakt,
elektronische Adresse und Zahlungsdaten des Verkäufers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from accounti.belege.extraktion import iban_gueltig

if TYPE_CHECKING:
    from accounti.kontakte.dienst import Partnerdaten

STANDARD_PFAD = Path("config/accounti.yaml")


class KonfigurationError(ValueError):
    """Die Konfiguration fehlt oder ist unvollständig."""


class Anschrift(BaseModel):
    strasse: str
    plz: str
    ort: str
    land: str = Field(default="DE", min_length=2, max_length=2)


class Kontakt(BaseModel):
    name: str
    telefon: str
    email: str


class Bank(BaseModel):
    iban: str
    bic: str | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, wert: str) -> str:
        iban = wert.replace(" ", "").upper()
        if not iban_gueltig(iban):
            msg = f"IBAN {wert!r} ist ungültig (Prüfziffer)"
            raise ValueError(msg)
        return iban


class Rechnungseinstellungen(BaseModel):
    nummernformat: str = "{jahr}-{nummer:04d}"
    zahlungsziel_tage: int = Field(default=14, ge=0)


class Firma(BaseModel):
    name: str
    kuerzel: str | None = Field(
        default=None, description="Schlüssel des Nummernkreises"
    )
    anschrift: Anschrift
    ust_id: str | None = None
    steuernummer: str | None = None
    email: str = Field(description="Elektronische Adresse für E-Rechnungen (BT-34)")
    kontakt: Kontakt
    bank: Bank
    rechnung: Rechnungseinstellungen = Field(default_factory=Rechnungseinstellungen)
    oss: bool = Field(
        default=False,
        description="OSS-registriert: EU-Privatkunden zahlen den Satz ihres Landes",
    )

    @model_validator(mode="after")
    def _pflichten(self) -> Firma:
        if not (self.ust_id or self.steuernummer):
            msg = "USt-IdNr. oder Steuernummer fehlt (§ 14 Abs. 4 Nr. 2 UStG)"
            raise ValueError(msg)
        if self.kuerzel is None:
            self.kuerzel = self.name
        return self

    @property
    def iban(self) -> str:
        return self.bank.iban

    @property
    def zahlungsziel_tage(self) -> int:
        return self.rechnung.zahlungsziel_tage

    @property
    def nummernkreis(self) -> str:
        return self.kuerzel or self.name

    def nummer(self, jahr: int, laufend: int) -> str:
        """Rechnungsnummer aus Jahr und laufender Nummer, z.B. ``2026-0042``."""
        return self.rechnung.nummernformat.format(jahr=jahr, nummer=laufend)


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"]) or "mandant"
        grund = (
            "fehlt"
            if f["type"] == "missing"
            else str(f["msg"]).removeprefix("Value error, ")
        )
        teile.append(f"mandant.{pfad}: {grund}" if pfad != "mandant" else grund)
    return "; ".join(teile)


def lade_firma(pfad: str | Path = STANDARD_PFAD) -> Firma:
    pfad = Path(pfad)
    if not pfad.is_file():
        msg = (
            f"{pfad} fehlt — Vorlage: config/accounti.example.yaml kopieren und "
            "den Abschnitt 'mandant' ausfüllen"
        )
        raise KonfigurationError(msg)
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    mandant = daten.get("mandant") if isinstance(daten, dict) else None
    if not isinstance(mandant, dict):
        msg = f"{pfad}: Abschnitt 'mandant' fehlt"
        raise KonfigurationError(msg)
    try:
        return Firma.model_validate(mandant)
    except ValidationError as fehler:
        msg = f"{pfad}: {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler


class Buchhaltung(BaseModel):
    """Abschnitt ``buchhaltung`` — optional, ohne ihn gelten die Standards."""

    kontenrahmen: str = "SKR03"
    debitoren_von: int = 10000
    debitoren_bis: int = 69999
    kreditoren_von: int = 70000
    kreditoren_bis: int = 99999
    bank_konto: str = "1200"
    standard_aufwand: str = Field(
        default="4900", description="Sachkonto, wenn nichts Besseres bekannt ist"
    )
    standard_zahlungsziel_tage: int = 14
    skonto_karenz_tage: int = Field(
        default=3,
        description="Skonto gilt noch, wenn die Bank so viele Tage später bucht",
    )
    # Skontokonten je Steuersatz (SKR03); "0" für steuerfreie Rechnungen
    skonto_erhalten: dict[str, str] = Field(
        default_factory=lambda: {"19": "3736", "7": "3731", "0": "3730"}
    )
    skonto_gewaehrt: dict[str, str] = Field(
        default_factory=lambda: {"19": "8736", "7": "8731", "0": "8730"}
    )


def lade_buchhaltung(pfad: str | Path = STANDARD_PFAD) -> Buchhaltung:
    pfad = Path(pfad)
    if not pfad.is_file():
        return Buchhaltung()
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get("buchhaltung") if isinstance(daten, dict) else None
    try:
        return Buchhaltung.model_validate(abschnitt or {})
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'buchhaltung': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler


def lade_eigene_firma(pfad: str | Path = STANDARD_PFAD) -> Partnerdaten | None:
    """Name, USt-IdNr. und IBAN der eigenen Firma — nachsichtig gelesen.

    Anders als `lade_firma` verlangt das keine vollständigen Firmendaten: Es reicht,
    die eigene Firma wiederzuerkennen (z.B. damit sie nie als Kreditor angelegt wird).
    """
    from accounti.kontakte.dienst import Partnerdaten

    pfad = Path(pfad)
    if not pfad.is_file():
        return None
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    mandant = daten.get("mandant") if isinstance(daten, dict) else None
    if not isinstance(mandant, dict) or not mandant.get("name"):
        return None
    bank_roh = mandant.get("bank")
    bank: dict[str, Any] = bank_roh if isinstance(bank_roh, dict) else {}
    return Partnerdaten(
        name=str(mandant["name"]),
        ust_id=mandant.get("ust_id"),
        iban=str(bank.get("iban", "")).replace(" ", "") or None,
    )
