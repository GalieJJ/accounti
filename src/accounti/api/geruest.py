"""Gerüst der Oberfläche (Baustein 10c, Plan P1): alles, was ``basis.html`` und die
Navigationsmakros brauchen, an einer Stelle.

Die Navigationsmakros in ``_komponenten.html`` (Seitenleiste, untere Leiste) arbeiten
nur mit ``NavEintrag``. ``geruest()`` befüllt den ``Geruest`` aus der Registry
(``app.state.navigation``), den Rechten der Rolle und — nur für ganze Seiten — den
Zählern über den Lesezugriff (``api.lesezugriff``).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from accounti.api.lesezugriff import Zaehler, zaehle
from accounti.api.registry import UNTEN, Bereich, Navigationspunkt
from accounti.i18n import N_
from accounti.models.auth import Recht

if TYPE_CHECKING:
    from fastapi import Request

    from accounti.api.sitzung import Angemeldet


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


MEHR = NavEintrag(N_("Mehr"), "/menue", "menu")


def aktiver_punkt(
    punkte: Sequence[Navigationspunkt], pfad: str
) -> Navigationspunkt | None:
    """Der Punkt mit dem längsten Pfadpräfix der Anfrage; ``/`` nur genau."""
    beste: Navigationspunkt | None = None
    for p in punkte:
        if p.pfad == "/":
            treffer = pfad == "/"
        else:
            treffer = pfad == p.pfad or pfad.startswith(p.pfad.rstrip("/") + "/")
        if treffer and (beste is None or len(p.pfad) > len(beste.pfad)):
            beste = p
    return beste


def bereichspunkte(
    punkte: Sequence[Navigationspunkt], rechte: Collection[Recht]
) -> dict[Bereich, Navigationspunkt]:
    """Je Bereich der erlaubte Punkt mit der kleinsten Reihenfolge (A2) — in der
    Reihenfolge der Bereiche (A1)."""
    gewaehlt: dict[Bereich, Navigationspunkt] = {}
    for p in sorted(punkte, key=lambda p: (p.reihenfolge, p.titel)):
        if p.erlaubt(rechte) and p.bereich not in gewaehlt:
            gewaehlt[p.bereich] = p
    return {b: gewaehlt[b] for b in Bereich if b in gewaehlt}


def _eintrag(
    p: Navigationspunkt, zahlen: Mapping[str, int], aktiv: Bereich | None
) -> NavEintrag:
    return NavEintrag(
        titel=p.titel,
        pfad=p.pfad,
        symbol=p.symbol,
        kurztitel=p.kurztitel or "",
        zaehler=zahlen.get(p.bereich.value) if p.zaehler is not None else None,
        betont=p.zaehler_betont,
        aktiv=p.bereich is aktiv,
    )


def navigation_des_geruests(
    punkte: Sequence[Navigationspunkt],
    rechte: Collection[Recht],
    pfad: str,
    zahlen: Mapping[str, int],
) -> tuple[tuple[NavEintrag, ...], NavEintrag | None, tuple[NavEintrag, ...]]:
    """Bereiche (Seitenleiste, ``/menue``), abgesetzt Einstellungen, untere Leiste
    (höchstens vier Bereiche und „Mehr“)."""
    gewaehlt = bereichspunkte(punkte, rechte)
    treffer = aktiver_punkt([p for p in punkte if p.erlaubt(rechte)], pfad)
    aktiv = treffer.bereich if treffer is not None else None
    eintraege = {b: _eintrag(p, zahlen, aktiv) for b, p in gewaehlt.items()}
    bereiche = tuple(e for b, e in eintraege.items() if b is not Bereich.EINSTELLUNGEN)
    mehr = NavEintrag(MEHR.titel, MEHR.pfad, MEHR.symbol, aktiv=pfad == MEHR.pfad)
    unten = (*(eintraege[b] for b in UNTEN if b in eintraege), mehr)
    return bereiche, eintraege.get(Bereich.EINSTELLUNGEN), unten


def zaehlfunktionen(
    punkte: Sequence[Navigationspunkt], rechte: Collection[Recht]
) -> dict[str, Zaehler]:
    return {
        b.value: p.zaehler
        for b, p in bereichspunkte(punkte, rechte).items()
        if p.zaehler is not None
    }


async def geruest(
    request: Request, a: Angemeldet | None, *, zaehler: bool = True
) -> Geruest:
    """Alles, was ``basis.html`` braucht. Zähler nur mit ``zaehler`` (ganze Seiten mit
    Status < 400, ``seite()`` entscheidet) — in **einem** Aufruf des Lesezugriffs mit
    **einer** Sitzung der aktiven Gesellschaft; fehlt eine Zahl, fehlt nur sie."""
    if a is None:
        return Geruest()
    punkte: Sequence[Navigationspunkt] = getattr(request.app.state, "navigation", [])
    zahlen: dict[str, int] = {}
    funktionen = zaehlfunktionen(punkte, a.rechte)
    lesezugriff = getattr(request.app.state, "lesezugriff", None)
    if zaehler and funktionen and lesezugriff is not None:
        zahlen = await zaehle(lesezugriff, a.gesellschaft.datenbank, funktionen) or {}
    bereiche, einstellungen, unten = navigation_des_geruests(
        punkte, a.rechte, request.url.path, zahlen
    )
    return Geruest(bereiche=bereiche, einstellungen=einstellungen, unten=unten)
