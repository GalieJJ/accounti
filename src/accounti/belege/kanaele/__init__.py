"""Beleg-Kanäle — liefern Rohdatei plus Herkunft, kennen keine Buchhaltungslogik."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RohBeleg:
    """Eine eingegangene Datei, so wie der Kanal sie geliefert hat."""

    dateiname: str
    inhalt: bytes
    kanal: str
    herkunft: str
    eingegangen_am: datetime = field(default_factory=datetime.now)


class BelegKanal:
    """Basisklasse für Kanäle."""

    name: str = "base"
    beschreibung: str = ""

    def abholen(self) -> Iterator[RohBeleg]:
        raise NotImplementedError

    def bestaetige(self, roh: RohBeleg) -> None:
        """Wird aufgerufen, sobald der Eingang gespeichert ist."""


# Registry: Kanalname -> Kanalklasse (Kanäle brauchen Konfiguration, z.B. einen Pfad).
BELEG_KANAELE: dict[str, type[BelegKanal]] = {}


def registriere(kanal: type[BelegKanal]) -> type[BelegKanal]:
    BELEG_KANAELE[kanal.name] = kanal
    return kanal


from accounti.belege.kanaele import ordner, upload  # noqa: E402, F401
