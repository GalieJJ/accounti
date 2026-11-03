"""Gerüst der Oberfläche (Baustein 10c, Plan P1): alles, was ``basis.html`` und die
Navigationsmakros brauchen, an einer Stelle.

Die Navigationsmakros in ``_komponenten.html`` (Seitenleiste, untere Leiste) arbeiten
nur mit ``NavEintrag``. ``geruest()`` befüllt den ``Geruest`` aus der Registry
(``app.state.navigation``), den Rechten der Rolle und — nur für ganze Seiten — den
Zählern über den Lesezugriff (``api.lesezugriff``).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
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
    from accounti.betrieb.gesellschaften import Gesellschaft


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
    initialen: str = ""


# Darstellung am Benutzer → <meta name="color-scheme"> (E16)
COLOR_SCHEME = {"auto": "light dark", "hell": "light", "dunkel": "dark"}


KENNFARBEN = 6
WORT = re.compile(r"[^\W_]+")


def kennfarben(
    kuerzel_alle: Iterable[str], gewaehlt: Mapping[str, int] | None = None
) -> dict[str, int]:
    """Kennfarbe (1–6) je Gesellschaft — **immer** über alle Gesellschaften der
    Registry, damit jeder Benutzer dieselbe Gesellschaft in derselben Farbe sieht (A5).
    Gewählte Farben (P5) zuerst, dann in alphabetischer Reihenfolge der Kürzel
    ``1 + (erste 4 Byte von SHA-256(kuerzel)) % 6``, bei Belegung die nächste freie;
    ab sieben Gesellschaften wiederholen sich Farben."""
    gewaehlt = dict(gewaehlt or {})
    farben = {k: f for k, f in gewaehlt.items() if 1 <= f <= KENNFARBEN}
    belegt = set(farben.values())
    for kuerzel in sorted(set(kuerzel_alle) - set(farben)):
        start = int.from_bytes(hashlib.sha256(kuerzel.encode()).digest()[:4], "big")
        kandidaten = [(start + i) % KENNFARBEN + 1 for i in range(KENNFARBEN)]
        frei = [f for f in kandidaten if f not in belegt]
        farben[kuerzel] = frei[0] if frei else kandidaten[0]
        belegt.add(farben[kuerzel])
    return farben


def monogramme(namen_alle: Mapping[str, str]) -> dict[str, str]:
    """Monogramm (zwei Großbuchstaben) je Gesellschaft — über alle der Registry, in
    alphabetischer Reihenfolge der Kürzel vergeben (Plan P1, B24): Anfangsbuchstaben
    der ersten zwei Wörter des Namens (ein Wort: seine ersten zwei Zeichen); schon
    vergeben → die ersten zwei Zeichen des Registry-Kürzels; auch vergeben → erstes
    Zeichen und eine Ziffer 2–9."""
    vergeben: dict[str, str] = {}
    for kuerzel in sorted(namen_alle):
        woerter: list[str] = WORT.findall(namen_alle[kuerzel])
        erste = (
            woerter[0][0] + woerter[1][0]
            if len(woerter) > 1
            else woerter[0][:2]
            if woerter
            else ""
        ).upper()[:2]
        kandidaten = [erste, kuerzel[:2].upper()]
        anfang = (erste or kuerzel.upper())[:1]
        kandidaten += [f"{anfang}{ziffer}" for ziffer in range(2, 10)]
        frei = [k for k in kandidaten if len(k) == 2 and k not in vergeben.values()]
        vergeben[kuerzel] = frei[0] if frei else kandidaten[-1]
    return vergeben


def marken(
    gesellschaften: Mapping[str, Gesellschaft],
    gewaehlt: Mapping[str, int] | None = None,
) -> dict[str, Marke]:
    """Kennfarbe und Monogramm je Gesellschaft der Registry (Kopf, ``/menue``,
    ``/gesellschaft``)."""
    farben = kennfarben(gesellschaften, gewaehlt)
    zeichen = monogramme({k: g.name for k, g in gesellschaften.items()})
    return {
        k: Marke(k, g.name, farben[k], zeichen[k]) for k, g in gesellschaften.items()
    }


def initialen(name: str) -> str:
    """Initialen für den Avatar: zwei Zeichen aus Anzeigename oder Benutzername."""
    woerter: list[str] = WORT.findall(name)
    if len(woerter) > 1:
        return (woerter[0][0] + woerter[1][0]).upper()[:2]
    return (woerter[0][:2] if woerter else "?").upper()


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


def hilfe_pfad(aktiv: Bereich | None, pfad: str) -> str:
    """Ziel des Hilfe-Links: die Hilfe des aktiven Bereichs, auf der Anmeldung die der
    Anmeldung, auf „Mein Konto“ die des Kontos, sonst die Übersicht der Hilfe."""
    if pfad.startswith("/anmelden"):
        return "/hilfe/anmeldung"
    if pfad == "/konto" or pfad.startswith("/konto/"):
        return "/hilfe/konto"
    return f"/hilfe/{aktiv.value}" if aktiv is not None else "/hilfe"


def _aktiver_bereich(
    punkte: Sequence[Navigationspunkt], rechte: Collection[Recht], pfad: str
) -> Bereich | None:
    treffer = aktiver_punkt([p for p in punkte if p.erlaubt(rechte)], pfad)
    return treffer.bereich if treffer is not None else None


async def geruest(
    request: Request, a: Angemeldet | None, *, zaehler: bool = True
) -> Geruest:
    """Alles, was ``basis.html`` braucht. Zähler nur mit ``zaehler`` (ganze Seiten mit
    Status < 400, ``seite()`` entscheidet) — in **einem** Aufruf des Lesezugriffs mit
    **einer** Sitzung der aktiven Gesellschaft; fehlt eine Zahl, fehlt nur sie."""
    pfad = request.url.path
    if a is None:
        return Geruest(hilfe_pfad=hilfe_pfad(None, pfad))
    dienste = request.app.state.dienste
    punkte: Sequence[Navigationspunkt] = getattr(request.app.state, "navigation", [])
    zahlen: dict[str, int] = {}
    funktionen = zaehlfunktionen(punkte, a.rechte)
    lesezugriff = getattr(request.app.state, "lesezugriff", None)
    if zaehler and funktionen and lesezugriff is not None:
        zahlen = await zaehle(lesezugriff, a.gesellschaft.datenbank, funktionen) or {}
    bereiche, einstellungen, unten = navigation_des_geruests(
        punkte, a.rechte, pfad, zahlen
    )
    alle_marken = marken(dienste.gesellschaften)
    b = a.benutzer
    return Geruest(
        bereiche=bereiche,
        einstellungen=einstellungen,
        unten=unten,
        hilfe_pfad=hilfe_pfad(_aktiver_bereich(punkte, a.rechte, pfad), pfad),
        marke=alle_marken.get(a.gesellschaft.kuerzel),
        marken=alle_marken,
        darstellung=b.darstellung,
        color_scheme=COLOR_SCHEME[b.darstellung],
        tastenkuerzel=b.tastenkuerzel,
        fachansicht=b.fachansicht,
        betraege_verbergen=b.betraege_verbergen,
        druck_datum=dienste.uhr().date(),
        initialen=initialen(b.anzeigename or b.name),
    )
