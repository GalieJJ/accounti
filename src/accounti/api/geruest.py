"""Gerüst der Oberfläche (Baustein 10c, Plan P1): alles, was ``basis.html`` und die
Navigationsmakros brauchen, an einer Stelle.

Schritt 4 legt die Datentypen an; die Navigationsmakros in ``_komponenten.html``
(Seitenleiste, untere Leiste) arbeiten nur mit ``NavEintrag``. Befüllt werden sie aus
der Registry, den Vorlieben und der Gesellschaft ab Schritt 6/7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class NavEintrag:
    """Ein Ziel der Navigation (Seitenleiste, untere Leiste, ``/menue``).

    ``titel`` und ``kurztitel`` sind Texte des Katalogs (``N_()``), die Makros
    übersetzen sie; ``zaehler`` fehlt (``None``), wenn es keinen gibt oder er nicht
    rechtzeitig kam; ``betont`` zeichnet ihn im Akzent (Prüfen)."""

    titel: str
    pfad: str
    symbol: str
    kurztitel: str = ""
    zaehler: int | None = None
    betont: bool = False
    aktiv: bool = False

    @property
    def kurz(self) -> str:
        return self.kurztitel or self.titel


@dataclass(frozen=True)
class Marke:
    """Kennfarbe (``marke-1`` … ``marke-6``) und Monogramm einer Gesellschaft (A5)."""

    kuerzel: str
    name: str
    farbe: int
    monogramm: str


@dataclass(frozen=True)
class Geruest:
    bereiche: tuple[NavEintrag, ...] = ()
    einstellungen: NavEintrag | None = None
    unten: tuple[NavEintrag, ...] = ()
    brotkrumen: tuple[tuple[str, str | None], ...] = ()
    hilfe_pfad: str = "/hilfe"
    marke: Marke | None = None
    marken: dict[str, Marke] = field(default_factory=dict)
    darstellung: str = "auto"
    color_scheme: str = "light dark"
    tastenkuerzel: bool = True
    fachansicht: bool = False
    betraege_verbergen: bool = False
    druck_datum: date | None = None
