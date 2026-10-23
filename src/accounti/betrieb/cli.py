"""Gesellschaftskontext für die CLI — aufgerufen vom Callback in ``cli.py``."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from typer.core import TyperGroup

from accounti.betrieb.kontext import (
    OHNE_GESELLSCHAFT,
    bestimme_kontext,
    kontext_ohne_registry,
    ruecksetzen,
    setze_kontext,
    standardwerte_fuer,
)
from accounti.konfiguration import KonfigurationError

console = Console(stderr=True)

ARGUMENTE = "accounti.argumente"


class Wurzelgruppe(TyperGroup):
    """Die Gruppe ``accounti``: merkt sich die Argumente hinter den globalen Optionen.

    Click leert sie, bevor es den Callback aufruft — der braucht sie aber, um eine
    Hilfe (``abschluss --help``) von einem Datenbefehl zu unterscheiden (Befund
    Betrieb B11)."""

    def invoke(self, ctx: Any) -> Any:
        geschuetzt = getattr(ctx, "_protected_args", None)  # Click ≥ 8.2
        if geschuetzt is None:
            geschuetzt = ctx.protected_args
        ctx.meta[ARGUMENTE] = [*geschuetzt, *ctx.args]
        return super().invoke(ctx)


def _zeige_hilfe_falls_verlangt(ctx: Any) -> None:
    """Zeigt die Hilfe des aufgerufenen Befehls und endet (Exit 0), wenn Click die
    Argumente als Hilfe liest — sonst nichts.

    Geprüft wird mit Clicks eigenem Parser: Der Befehl wird über die Gruppen
    aufgelöst und mit seinen Argumenten geparst; ``--help`` ist eager und endet dort.
    ``--help`` als Wert einer Option (``--text --help``) ist so keine Hilfe — der
    Befehl liefe sonst ohne Gesellschaft gegen die Standarddatenbank. (Typer bringt
    je nach Version ein eigenes Click mit — daher Duck-Typing statt ``click.Group``.)
    """
    argumente: list[str] = list(ctx.meta.get(ARGUMENTE, []))
    ende = argumente.index("--") if "--" in argumente else len(argumente)
    if not set(ctx.help_option_names) & set(argumente[:ende]):
        return
    gruppe, eltern = ctx.command, ctx
    try:
        while hasattr(gruppe, "resolve_command") and argumente:
            name, befehl, argumente = gruppe.resolve_command(eltern, argumente)
            if name is None or befehl is None:
                return
            if (
                hasattr(befehl, "resolve_command")
                and argumente
                and not argumente[0].startswith("-")
            ):
                gruppe = befehl
                eltern = befehl.context_class(befehl, parent=eltern, info_name=name)
                continue
            befehl.make_context(name, list(argumente), parent=eltern)
            return
    except typer.Exit:
        raise  # die Hilfe wurde gezeigt
    except Exception:  # Fehler beim Parsen: keine Hilfe — Abbruch wie sonst
        return


def richte_kontext_ein(ctx: Any, gesellschaft: str | None) -> None:
    """Kontext bestimmen, ``default_map`` setzen und beim Ende zurücksetzen.

    Lässt sich die Registry nicht lesen, bricht nur ab, wer ausdrücklich eine
    Gesellschaft wählt; alle anderen Befehle laufen mit einem Hinweis weiter —
    wer Gesellschaft oder Rechte braucht, scheitert später an ``Kontext.pruefe``.
    """
    try:
        kontext = bestimme_kontext(gesellschaft)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        if gesellschaft is not None:
            raise typer.Exit(2) from fehler
        kontext = kontext_ohne_registry(str(fehler))
    if (
        kontext.gesellschaft is None
        and kontext.registry.mehrere
        and ctx.invoked_subcommand not in OHNE_GESELLSCHAFT
    ):
        _zeige_hilfe_falls_verlangt(ctx)
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
