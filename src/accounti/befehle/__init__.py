"""Befehlsgruppen der Bausteine — jedes Modul hier wird automatisch eingehängt.

Ein Modul definiert ``NAME`` (Name der Befehlsgruppe, z.B. ``"zahlung"``) und
``befehl`` (eine ``typer.Typer``-Instanz). ``accounti.cli`` hängt beim Start alle
Module dieses Pakets ein — ein neuer Baustein braucht so keine Änderung an
``cli.py`` und kommt anderen Bausteinen nicht in die Quere.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import typer
from rich.console import Console

console = Console()
DB_OPTION = typer.Option("sqlite:///accounti.db", help="DB-URL")
KONFIG_OPTION = typer.Option("config/accounti.yaml", "--config", help="Konfiguration")


def befehlsmodule() -> list[ModuleType]:
    """Alle Module dieses Pakets mit ``NAME`` und ``befehl``, nach Name sortiert."""
    gefunden = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        modul = importlib.import_module(f"{__name__}.{info.name}")
        if isinstance(getattr(modul, "befehl", None), typer.Typer) and isinstance(
            getattr(modul, "NAME", None), str
        ):
            gefunden.append(modul)
    return gefunden
