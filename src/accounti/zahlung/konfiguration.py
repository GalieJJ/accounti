"""Abschnitt ``zahlung`` in ``config/accounti.yaml`` — optional, mit Standards.

Der Auftraggeber (eigenes Konto) kommt aus ``zahlung.auftraggeber``; was dort fehlt,
wird aus ``mandant.name`` und ``mandant.bank`` ergänzt.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.zahlung.iban import gueltig, normalisiere

_BIC = re.compile(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?")


class Auftraggeber(BaseModel):
    name: str | None = None
    iban: str | None = None
    bic: str | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, wert: str | None) -> str | None:
        if wert is None:
            return None
        if not gueltig(wert):
            msg = f"IBAN {wert!r} ist ungültig (Prüfziffer)"
            raise ValueError(msg)
        return normalisiere(wert)

    @field_validator("bic")
    @classmethod
    def _bic(cls, wert: str | None) -> str | None:
        if wert is None:
            return None
        bic = wert.replace(" ", "").upper()
        if not _BIC.fullmatch(bic):
            msg = f"BIC {wert!r} hat nicht 8 oder 11 Stellen im SWIFT-Format"
            raise ValueError(msg)
        return bic


class ZahlungEinstellungen(BaseModel):
    vorlauf_tage: int = Field(
        default=3, ge=0, description="Fristen so weit voraus einplanen"
    )
    skonto_ziehen: bool = True
    mindestbetrag: Decimal | None = Field(default=None, ge=0)
    hoechstbetrag: Decimal | None = Field(default=None, gt=0)
    hoechstbetrag_zahlung: Decimal | None = Field(
        default=None, gt=0, description="Prüfung: größere Einzelzahlungen blockieren"
    )
    vier_augen: bool = Field(
        default=False,
        description="zwei verschiedene Personen (Anmeldename) geben frei",
    )
    freigeber: list[str] = Field(
        default_factory=list,
        description="nur diese Personen dürfen freigeben; leer = alle",
    )
    einzelbuchung: bool = Field(
        default=True, description="BtchBookg=false — nur mit Bankvereinbarung"
    )
    auftraggeber: Auftraggeber = Field(default_factory=Auftraggeber)


def _fehlertext(fehler: ValidationError) -> str:
    return "; ".join(
        ".".join(str(x) for x in f["loc"])
        + ": "
        + str(f["msg"]).removeprefix("Value error, ")
        for f in fehler.errors()
    )


def lade_zahlung(pfad: str | Path = STANDARD_PFAD) -> ZahlungEinstellungen:
    pfad = Path(pfad)
    daten: Any = {}
    if pfad.is_file():
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    if not isinstance(daten, dict):
        daten = {}
    abschnitt = daten.get("zahlung")
    werte: dict[str, Any] = dict(abschnitt) if isinstance(abschnitt, dict) else {}
    auftraggeber = werte.get("auftraggeber")
    auftraggeber = dict(auftraggeber) if isinstance(auftraggeber, dict) else {}
    mandant = daten.get("mandant")
    if isinstance(mandant, dict):
        bank_roh = mandant.get("bank")
        bank: dict[str, Any] = bank_roh if isinstance(bank_roh, dict) else {}
        if not auftraggeber.get("iban"):
            auftraggeber.setdefault("name", mandant.get("name"))
            auftraggeber["iban"] = bank.get("iban")
            auftraggeber["bic"] = bank.get("bic")
        auftraggeber.setdefault("name", mandant.get("name"))
    werte["auftraggeber"] = auftraggeber
    try:
        return ZahlungEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'zahlung': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
