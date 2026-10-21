"""Abschnitte ``abschluss`` und ``kasse`` in ``config/accounti.yaml`` — optional.

Ohne Abschnitt gelten die Standards des Kontenrahmens aus ``buchhaltung.kontenrahmen``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.abschluss.kontenrahmen import (
    Gewinnermittlung,
    Kontenrahmen,
    lade_kontenrahmen,
)
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError, lade_buchhaltung

_STANDARDS: dict[str, dict[str, Any]] = {
    "SKR03": {
        "ergebnis_konto": "0880",  # Variables Kapital
        "arap_konto": "0980",
        "prap_konto": "0990",
        # Geldtransit, Durchlaufende Posten, Sonstige Verrechnungskonten (Interim)
        "verrechnungskonten": ["1360", "1590", "1792"],
    },
    "SKR04": {
        "ergebnis_konto": "2010",
        "arap_konto": "1900",
        "prap_konto": "3900",
        "verrechnungskonten": ["1460", "1370", "3630"],
    },
}
_KASSE = {"SKR03": "1000", "SKR04": "1600"}


class AbschlussEinstellungen(BaseModel):
    kontenrahmen: str = "SKR03"
    gewinnermittlung: Gewinnermittlung = "euer"
    ergebnis_konto: str
    arap_konto: str
    prap_konto: str
    rap_verzicht_bis_gwg: bool = Field(
        default=False, description="§ 5 Abs. 5 Satz 2 EStG, einheitlich"
    )
    verrechnungskonten: list[str] = Field(default_factory=list)
    kontenzuordnung: str | None = None
    debitoren: tuple[int, int] = (10000, 69999)
    kreditoren: tuple[int, int] = (70000, 99999)
    bank_konto: str = "1200"

    def lade_kontenrahmen(self) -> Kontenrahmen:
        return lade_kontenrahmen(self.kontenrahmen, self.kontenzuordnung)


class KassenEinstellungen(BaseModel):
    konto: str


def _abschnitt(pfad: Path, name: str) -> dict[str, Any]:
    if not pfad.is_file():
        return {}
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get(name) if isinstance(daten, dict) else None
    return dict(abschnitt) if isinstance(abschnitt, dict) else {}


def lade_abschluss(pfad: str | Path = STANDARD_PFAD) -> AbschlussEinstellungen:
    pfad = Path(pfad)
    buchhaltung = lade_buchhaltung(pfad)
    kontenrahmen = buchhaltung.kontenrahmen.upper()
    werte = {
        **_STANDARDS.get(kontenrahmen, _STANDARDS["SKR03"]),
        **_abschnitt(pfad, "abschluss"),
        "kontenrahmen": kontenrahmen,
        "debitoren": (buchhaltung.debitoren_von, buchhaltung.debitoren_bis),
        "kreditoren": (buchhaltung.kreditoren_von, buchhaltung.kreditoren_bis),
        "bank_konto": buchhaltung.bank_konto,
    }
    try:
        return AbschlussEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'abschluss': {fehler}"
        raise KonfigurationError(msg) from fehler


def gewinnermittlung_angegeben(pfad: str | Path = STANDARD_PFAD) -> str | None:
    """``abschluss.gewinnermittlung``, wenn sie ausdrücklich in der Konfiguration steht
    (``bilanz`` oder ``euer``) — sonst ``None`` (der Standard ``euer`` gilt dann nur
    dort, wo er nichts riskiert)."""
    wert = _abschnitt(Path(pfad), "abschluss").get("gewinnermittlung")
    return wert if wert in ("bilanz", "euer") else None


def lade_kasse(pfad: str | Path = STANDARD_PFAD) -> KassenEinstellungen:
    pfad = Path(pfad)
    kontenrahmen = lade_buchhaltung(pfad).kontenrahmen.upper()
    werte = {"konto": _KASSE.get(kontenrahmen, "1000"), **_abschnitt(pfad, "kasse")}
    try:
        return KassenEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        raise KonfigurationError(f"{pfad}: Abschnitt 'kasse': {fehler}") from fehler
