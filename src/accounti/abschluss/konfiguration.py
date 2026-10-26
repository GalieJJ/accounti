"""Abschnitte ``abschluss`` und ``kasse`` in ``config/accounti.yaml`` — optional.

Ohne Abschnitt gelten die Standards des Kontenrahmens aus ``buchhaltung.kontenrahmen``.

Das Wirtschaftsjahr kommt aus ``datev.wirtschaftsjahr_beginn`` (nur Tag und Monat;
ohne Angabe das Kalenderjahr). ``wirtschaftsjahr(jahr, beginn)`` ist der eine Helfer,
mit dem alle Abschlussmodule rechnen. Konvention: ``--jahr`` bezeichnet das
Wirtschaftsjahr über das Kalenderjahr seines **Endes** — 2026 ist bei Beginn 1. Juli
das Wirtschaftsjahr 01.07.2025–30.06.2026 (so gilt der Gewinn bei Gewerbetreibenden
als bezogen, § 4a Abs. 2 Nr. 2 EStG). Ein abweichendes Wirtschaftsjahr haben Land- und
Forstwirte (§ 4a Abs. 1 Satz 2 Nr. 1 EStG, auch mit EÜR) und im Handelsregister
eingetragene Gewerbetreibende (Nr. 2); es umfasst zwölf Monate (§ 8b EStDV,
Rumpfwirtschaftsjahre unterstützt accounti nicht).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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


@dataclass(frozen=True)
class Wirtschaftsjahr:
    """Ein Wirtschaftsjahr, benannt nach dem Kalenderjahr seines Endes."""

    jahr: int
    von: date
    bis: date

    @property
    def abweichend(self) -> bool:
        """Weicht vom Kalenderjahr ab (§ 4a EStG)?"""
        return (self.von.month, self.von.day) != (1, 1)

    @property
    def bezeichnung(self) -> str:
        """„2026“ bzw. „2025/2026“."""
        if not self.abweichend:
            return str(self.jahr)
        return f"{self.von.year}/{self.bis.year}"

    @property
    def zeitraum(self) -> str:
        return f"{self.von:%d.%m.%Y}–{self.bis:%d.%m.%Y}"

    def enthaelt(self, tag: date) -> bool:
        return self.von <= tag <= self.bis

    @property
    def kalenderjahre(self) -> list[tuple[int, int]]:
        """(Kalenderjahr, letzter Monat im Wirtschaftsjahr) je berührtem Kalenderjahr —
        für Läufe, die im Kalenderjahr rechnen (AfA-Lauf)."""
        if self.von.year == self.bis.year:
            return [(self.bis.year, self.bis.month)]
        return [(self.von.year, 12), (self.bis.year, self.bis.month)]


def _beginn_im_jahr(jahr: int, beginn: date | None) -> date:
    monat, tag = (beginn.month, beginn.day) if beginn else (1, 1)
    return date(jahr, monat, min(tag, 28) if monat == 2 else tag)


def wirtschaftsjahr(jahr: int, beginn: date | None = None) -> Wirtschaftsjahr:
    """Das Wirtschaftsjahr, das im Kalenderjahr ``jahr`` endet.

    ``beginn``: irgendein Beginn aus der Konfiguration, maßgeblich sind Tag und Monat
    (wie ``export/datev_stammdaten.wirtschaftsjahr_beginn``); ohne: Kalenderjahr."""
    start = _beginn_im_jahr(jahr, beginn)
    if (start.month, start.day) == (1, 1):
        return Wirtschaftsjahr(jahr, start, date(jahr, 12, 31))
    von = _beginn_im_jahr(jahr - 1, beginn)
    return Wirtschaftsjahr(jahr, von, start - timedelta(days=1))


def wirtschaftsjahr_zum(tag: date, beginn: date | None = None) -> Wirtschaftsjahr:
    """Das Wirtschaftsjahr, in dem ``tag`` liegt."""
    wj = wirtschaftsjahr(tag.year, beginn)
    return wj if tag <= wj.bis else wirtschaftsjahr(tag.year + 1, beginn)


def lade_wirtschaftsjahr_beginn(pfad: str | Path = STANDARD_PFAD) -> date | None:
    """``datev.wirtschaftsjahr_beginn`` (Tag und Monat) — ohne: Kalenderjahr."""
    wert = _abschnitt(Path(pfad), "datev").get("wirtschaftsjahr_beginn")
    if wert is None or isinstance(wert, date):
        return wert
    try:
        return date.fromisoformat(str(wert))
    except ValueError as fehler:
        msg = f"{pfad}: datev.wirtschaftsjahr_beginn {wert!r}: Format JJJJ-MM-TT"
        raise KonfigurationError(msg) from fehler


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
    wirtschaftsjahr_beginn: date | None = Field(
        default=None, description="aus datev.wirtschaftsjahr_beginn (Tag und Monat)"
    )

    def lade_kontenrahmen(self) -> Kontenrahmen:
        return lade_kontenrahmen(self.kontenrahmen, self.kontenzuordnung)

    def wirtschaftsjahr(self, jahr: int) -> Wirtschaftsjahr:
        """Das Wirtschaftsjahr ``jahr`` (Kalenderjahr seines Endes)."""
        return wirtschaftsjahr(jahr, self.wirtschaftsjahr_beginn)

    def wirtschaftsjahr_zum(self, tag: date) -> Wirtschaftsjahr:
        return wirtschaftsjahr_zum(tag, self.wirtschaftsjahr_beginn)

    @property
    def abweichendes_wirtschaftsjahr(self) -> bool:
        return self.wirtschaftsjahr(2000).abweichend


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
        "wirtschaftsjahr_beginn": lade_wirtschaftsjahr_beginn(pfad),
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
