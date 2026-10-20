"""Melde- und Voranmeldungszeiträume: Monat, Kalendervierteljahr, Jahr.

Schreibweise wie in der CLI: ``2026-08`` (Monat), ``2026-Q3`` (Quartal),
``2026`` (Jahr).
Im ELSTER-Datensatz heißt der Zeitraum ``01`` bis ``12`` bzw. ``41`` bis ``44``.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

MONATSNAMEN = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)
_ROEMISCH = ("I", "II", "III", "IV")
_MUSTER = re.compile(r"^(\d{4})(?:-(?:(\d{2})|[Qq]([1-4])))?$")


class ZeitraumError(ValueError):
    """Kein gültiger Zeitraum."""


@dataclass(frozen=True, order=True)
class Zeitraum:
    jahr: int
    monat: int | None = None
    quartal: int | None = None

    @classmethod
    def lies(cls, text: str) -> Zeitraum:
        treffer = _MUSTER.match(text.strip())
        if treffer is None:
            msg = f"Zeitraum {text!r} unverständlich — erwartet z.B. 2026-08, 2026-Q3"
            raise ZeitraumError(msg)
        jahr = int(treffer.group(1))
        if treffer.group(2):
            monat = int(treffer.group(2))
            if not 1 <= monat <= 12:
                raise ZeitraumError(f"Monat {monat} gibt es nicht ({text})")
            return cls(jahr, monat=monat)
        if treffer.group(3):
            return cls(jahr, quartal=int(treffer.group(3)))
        return cls(jahr)

    @classmethod
    def monat_von(cls, tag: date) -> Zeitraum:
        return cls(tag.year, monat=tag.month)

    @property
    def art(self) -> Literal["monat", "quartal", "jahr"]:
        if self.monat is not None:
            return "monat"
        return "quartal" if self.quartal is not None else "jahr"

    @property
    def von(self) -> date:
        if self.monat is not None:
            return date(self.jahr, self.monat, 1)
        if self.quartal is not None:
            return date(self.jahr, self.quartal * 3 - 2, 1)
        return date(self.jahr, 1, 1)

    @property
    def bis(self) -> date:
        if self.monat is not None:
            letzter = self.monat
        elif self.quartal is not None:
            letzter = self.quartal * 3
        else:
            letzter = 12
        return date(self.jahr, letzter, calendar.monthrange(self.jahr, letzter)[1])

    @property
    def elster_code(self) -> str:
        """``01``–``12`` für Monate, ``41``–``44`` für Kalendervierteljahre."""
        if self.monat is not None:
            return f"{self.monat:02d}"
        if self.quartal is not None:
            return f"4{self.quartal}"
        raise ZeitraumError(f"{self}: ein Jahr ist kein Voranmeldungszeitraum")

    @property
    def text(self) -> str:
        if self.monat is not None:
            return f"{MONATSNAMEN[self.monat - 1]} {self.jahr}"
        if self.quartal is not None:
            return f"{_ROEMISCH[self.quartal - 1]}. Quartal {self.jahr}"
        return str(self.jahr)

    def enthaelt(self, tag: date) -> bool:
        return self.von <= tag <= self.bis

    def monate(self) -> list[Zeitraum]:
        start = self.von.month
        return [Zeitraum(self.jahr, monat=m) for m in range(start, self.bis.month + 1)]

    def vorperiode(self) -> Zeitraum:
        if self.monat is not None:
            if self.monat == 1:
                return Zeitraum(self.jahr - 1, monat=12)
            return Zeitraum(self.jahr, monat=self.monat - 1)
        if self.quartal is not None:
            if self.quartal == 1:
                return Zeitraum(self.jahr - 1, quartal=4)
            return Zeitraum(self.jahr, quartal=self.quartal - 1)
        return Zeitraum(self.jahr - 1)

    def vorjahr(self) -> Zeitraum:
        return Zeitraum(self.jahr - 1, self.monat, self.quartal)

    def __str__(self) -> str:
        if self.monat is not None:
            return f"{self.jahr}-{self.monat:02d}"
        if self.quartal is not None:
            return f"{self.jahr}-Q{self.quartal}"
        return str(self.jahr)
