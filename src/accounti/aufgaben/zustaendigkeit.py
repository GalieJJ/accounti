"""Zuständigkeit: Benutzer oder Rolle — unzugewiesen ist ein sichtbarer Zustand.

Regeln aus dem Abschnitt ``aufgaben.zustaendigkeit`` greifen beim Anlegen einer
Aufgabe: Die erste Regel, deren Bedingungen alle passen, bestimmt Benutzer oder
Rolle. Bedingungen prüfen ``art``, ``objekt_typ`` oder ein Merkmal, das der
Erzeuger mitgibt (z.B. ``bankkonto``, ``kanal``, später ``gesellschaft``);
Platzhalter wie ``beleg_*`` sind erlaubt. Ohne Treffer bleibt die Aufgabe
unzugewiesen und steht in der gemeinsamen Liste.
"""

from __future__ import annotations

import getpass
import os
from collections.abc import Iterable, Mapping, Sequence
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from accounti.models.aufgaben import Aufgabe, Objekt

if TYPE_CHECKING:
    from accounti.aufgaben.einstellungen import AufgabenEinstellungen

GEMEINSAM = "gemeinsam"


class Zustaendigkeitsregel(BaseModel):
    wenn: dict[str, str] = Field(default_factory=dict)
    an: str | None = None
    rolle: str | None = None

    @model_validator(mode="after")
    def _ziel(self) -> Zustaendigkeitsregel:
        if (self.an is None) == (self.rolle is None):
            msg = "Regel braucht genau eins: an oder rolle"
            raise ValueError(msg)
        return self

    def passt(self, art: str, objekt: Objekt, merkmale: Mapping[str, str]) -> bool:
        werte = {**merkmale, "art": art, "objekt_typ": objekt.typ}
        return all(
            schluessel in werte and fnmatchcase(werte[schluessel], muster)
            for schluessel, muster in self.wenn.items()
        )


def bestimme_zustaendigkeit(
    regeln: Sequence[Zustaendigkeitsregel],
    art: str,
    objekt: Objekt,
    merkmale: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """(Benutzer, Rolle) der ersten passenden Regel, sonst (None, None)."""
    for regel in regeln:
        if regel.passt(art, objekt, merkmale):
            return regel.an, regel.rolle
    return None, None


def wer_bin_ich(einstellungen: AufgabenEinstellungen) -> str:
    """``aufgaben.ich``, sonst ``ACCOUNTI_BENUTZER``, sonst der Login-Name.

    Benutzerkonten bringt erst Baustein 10; bis dahin ist der Name eine Zeichenkette.
    """
    if einstellungen.ich:
        return einstellungen.ich
    return os.environ.get("ACCOUNTI_BENUTZER") or getpass.getuser()


def rollen_von(einstellungen: AufgabenEinstellungen, benutzer: str) -> set[str]:
    return {rolle for rolle, wer in einstellungen.rollen.items() if benutzer in wer}


def ist_zustaendig(
    aufgabe: Aufgabe, benutzer: str, einstellungen: AufgabenEinstellungen
) -> bool:
    if aufgabe.zustaendig is not None:
        return aufgabe.zustaendig == benutzer
    return aufgabe.rolle is not None and aufgabe.rolle in rollen_von(
        einstellungen, benutzer
    )


def meine_aufgaben(
    aufgaben: Iterable[Aufgabe], benutzer: str, einstellungen: AufgabenEinstellungen
) -> list[Aufgabe]:
    """Aktive Aufgaben des Benutzers — direkt oder über eine seiner Rollen."""
    return [
        a for a in aufgaben if a.aktiv and ist_zustaendig(a, benutzer, einstellungen)
    ]


def gemeinsame_liste(aufgaben: Iterable[Aufgabe]) -> list[Aufgabe]:
    """Aktive Aufgaben ohne Benutzer und ohne Rolle."""
    return [a for a in aufgaben if a.aktiv and a.unzugewiesen]
