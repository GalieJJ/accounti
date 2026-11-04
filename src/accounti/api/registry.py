"""Router-Registry — jedes Modul eines Pakets mit ``router`` wird eingehängt.

Muster wie ``accounti.befehle``: Ein neues Modul in ``accounti/api/seiten/`` (HTML,
Sitzung) oder ``accounti/api/rest/`` (JSON, Token) mit ``router = APIRouter()``
braucht keine Änderung an ``app.py``. Optional ``NAVIGATION`` (Liste von
``Navigationspunkt``) für die Navigation des Gerüsts (Baustein 10c, Plan P1): Jeder
Punkt gehört zu einem ``Bereich``; je Bereich zeigt die Navigation einen Eintrag (den
erlaubten mit der kleinsten ``reihenfolge``), ein Bereich ohne Seite oder ohne Recht
entfällt. Das Symbol muss im Sprite stehen; ein Zähler liest nur (Lesezugriff).
"""

from __future__ import annotations

import enum
import importlib
import pkgutil
from collections.abc import Callable, Collection
from dataclasses import dataclass
from types import ModuleType

from fastapi import APIRouter
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from accounti.api.symbole import symbol_url
from accounti.models.auth import Recht


class Bereich(str, enum.Enum):
    """Bereiche der Navigation in der Reihenfolge aus Spec 10c A1; Einstellungen stehen
    abgesetzt."""

    UEBERSICHT = "uebersicht"
    PRUEFEN = "pruefen"
    BELEGE = "belege"
    BANK = "bank"
    RECHNUNGEN = "rechnungen"
    STEUERN = "steuern"
    AUSWERTUNGEN = "auswertungen"
    FREIGABEN = "freigaben"
    EINSTELLUNGEN = "einstellungen"


# Ziele der unteren Leiste (schmal), dazu immer „Mehr“ (A4)
UNTEN = (Bereich.UEBERSICHT, Bereich.PRUEFEN, Bereich.BELEGE, Bereich.FREIGABEN)
REIHENFOLGE = {b: i for i, b in enumerate(Bereich)}


@dataclass(frozen=True)
class Navigationspunkt:
    """Ein Ziel der Navigation. ``recht`` als Menge heißt „eines genügt“ (Freigaben:
    Zahlung oder Steuer freigeben); ``zaehler`` liest nur (eine Sitzung des
    Lesezugriffs, nur für ganze Seiten); ``kurztitel`` für die untere Leiste."""

    titel: str
    pfad: str
    bereich: Bereich
    symbol: str
    recht: Recht | frozenset[Recht] = Recht.LESEN
    reihenfolge: int = 100
    zaehler: Callable[[Session], int] | None = None
    zaehler_betont: bool = False
    kurztitel: str | None = None

    def __post_init__(self) -> None:
        symbol_url(self.symbol)  # ValueError, wenn das Symbol nicht im Sprite steht

    def erlaubt(self, rechte: Collection[Recht]) -> bool:
        if isinstance(self.recht, frozenset):
            return any(r in rechte for r in self.recht)
        return self.recht in rechte


def routermodule(paket: ModuleType) -> list[ModuleType]:
    """Alle Module des Pakets mit ``router``, nach Name sortiert."""
    gefunden = []
    for info in sorted(pkgutil.iter_modules(paket.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        modul = importlib.import_module(f"{paket.__name__}.{info.name}")
        if isinstance(getattr(modul, "router", None), APIRouter):
            gefunden.append(modul)
    return gefunden


def navigation(module: list[ModuleType]) -> list[Navigationspunkt]:
    punkte: list[Navigationspunkt] = []
    for modul in module:
        punkte.extend(getattr(modul, "NAVIGATION", []))
    return sorted(
        punkte, key=lambda p: (REIHENFOLGE[p.bereich], p.reihenfolge, p.titel)
    )


@dataclass(frozen=True)
class Endpunkt:
    methode: str
    pfad: str
    modul: str


def endpunkte(module: list[ModuleType], praefix: str = "") -> list[Endpunkt]:
    """Alle Endpunkte der Router — für die Rechte-Matrix und die Doku."""
    gefunden = []
    for modul in module:
        for route in modul.router.routes:
            if isinstance(route, APIRoute):
                for methode in sorted(route.methods or ()):
                    gefunden.append(
                        Endpunkt(methode, praefix + route.path, modul.__name__)
                    )
    return gefunden
