"""Gesellschaftskontext für die CLI — aufgerufen vom Callback in ``cli.py``."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.markup import escape

from accounti.betrieb.kontext import (
    OHNE_GESELLSCHAFT,
    bestimme_kontext,
    ruecksetzen,
    setze_kontext,
    standardwerte_fuer,
)
from accounti.konfiguration import KonfigurationError

console = Console(stderr=True)


def richte_kontext_ein(ctx: Any, gesellschaft: str | None) -> None:
    """Kontext bestimmen, ``default_map`` setzen und beim Ende zurücksetzen."""
    try:
        kontext = bestimme_kontext(gesellschaft)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(2) from fehler
    if (
        kontext.gesellschaft is None
        and kontext.registry.mehrere
        and ctx.invoked_subcommand not in OHNE_GESELLSCHAFT | {"benutzer", "token"}
    ):
        bekannt = ", ".join(sorted(kontext.registry.eintraege))
        console.print(
            f"[red]Mehrere Gesellschaften eingerichtet ({escape(bekannt)}) — "
            "--gesellschaft angeben oder gesellschaften.standard setzen[/red]",
            soft_wrap=True,
        )
        raise typer.Exit(2)
    if kontext.standardwerte:
        ctx.default_map = standardwerte_fuer(ctx.command, kontext.standardwerte)
    token = setze_kontext(kontext)
    ctx.call_on_close(lambda: ruecksetzen(token))
