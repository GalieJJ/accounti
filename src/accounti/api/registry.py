"""Router-Registry — jedes Modul eines Pakets mit ``router`` wird eingehängt.

Muster wie ``accounti.befehle``: Ein neues Modul in ``accounti/api/seiten/`` (HTML,
Sitzung) oder ``accounti/api/rest/`` (JSON, Token) mit ``router = APIRouter()``
braucht keine Änderung an ``app.py``. Optional ``NAVIGATION`` (Liste von
``Navigationspunkt``) für das Menü im Grundlayout.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType

from fastapi import APIRouter
from fastapi.routing import APIRoute

from accounti.models.auth import Recht


@dataclass(frozen=True)
class Navigationspunkt:
    titel: str
    pfad: str
    recht: Recht = Recht.LESEN
    reihenfolge: int = 100


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
    return sorted(punkte, key=lambda p: (p.reihenfolge, p.titel))


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
