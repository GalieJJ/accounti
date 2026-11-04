"""Gesellschaftskontext für die CLI — aufgerufen vom Callback in ``cli.py``.

Dazu der Stand der Einstellungen (Baustein 10c P4, D3): je Befehl ein neuer Stand;
jeder Parameter ``db`` im Befehlsbaum bindet ihn beim Parsen an seine Datenbank und
nimmt sofort den Schnappschuss — vor dem Rumpf, also bevor der Befehl selbst die
Datenbank sperrt. Ohne Bindung gilt beim ersten Lesen der Standard der Gesellschaft
bzw. ``ACCOUNTI_DB``, sonst ``befehle.STANDARD_DB``.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from typer.core import TyperGroup

from accounti.betrieb.kontext import (
    OHNE_GESELLSCHAFT,
    Kontext,
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
        from sqlalchemy.exc import OperationalError, ProgrammingError

        from accounti.einstellungen.leser import (
            EinstellungenNichtLesbar,
            EinstellungsquelleFehlt,
        )

        ctx.meta[ARGUMENTE] = _rest(ctx)
        try:
            return super().invoke(ctx)
        except (EinstellungenNichtLesbar, EinstellungsquelleFehlt) as fehler:
            # fail-closed (D5): Meldung statt Traceback, nie still die Datei
            console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
            raise typer.Exit(1) from fehler
        except (OperationalError, ProgrammingError) as fehler:
            # eine Tabelle oder Spalte dieses Codes fehlt: die Datenbank ist nicht
            # migriert — Hinweis statt Traceback, für jeden Befehl (gw-migration N-3)
            grund = schema_fehlt(fehler)
            if grund is None:
                raise
            console.print(
                f"[red]Datenbankfehler: {escape(grund)} — die Datenbank ist nicht "
                "auf dem Stand dieser Version: zuerst 'accounti db upgrade' (mit "
                "derselben --db bzw. -g; docs/betrieb.md, Upgrades). Ist es nicht "
                "die Datenbank von accounti, --db prüfen.[/red]",
                soft_wrap=True,
            )
            raise typer.Exit(1) from fehler


# SQLSTATE fehlende Spalte bzw. Tabelle (PostgreSQL)
_SCHEMA_SQLSTATE = frozenset({"42703", "42P01"})


def schema_fehlt(fehler: Exception) -> str | None:
    """Die Meldung der Datenbank, wenn sie eine Tabelle oder Spalte nicht kennt
    (SQLite „no such column/table“, PostgreSQL SQLSTATE 42703/42P01) — sonst
    ``None``."""
    ursache = getattr(fehler, "orig", None) or fehler
    text = (str(ursache).strip().splitlines() or [""])[0]
    zustand = getattr(ursache, "sqlstate", None) or getattr(ursache, "pgcode", None)
    if zustand in _SCHEMA_SQLSTATE:
        return text
    if text.startswith(("no such column", "no such table")):
        return text
    return None


def _rest(ctx: Any) -> list[str]:
    """Argumente, die Click nach den Optionen einer Gruppe übrig lässt (Unterbefehl
    und dessen Argumente)."""
    geschuetzt = getattr(ctx, "_protected_args", None)  # Click ≥ 8.2
    if geschuetzt is None:
        geschuetzt = ctx.protected_args
    return [*geschuetzt, *ctx.args]


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
            kontext = befehl.make_context(name, list(argumente), parent=eltern)
            if not hasattr(befehl, "resolve_command"):
                return
            # Gruppe mit eigenen Optionen (``ustva --period … pruefen --help``,
            # Nachprüfung N1): mit dem Rest weiter absteigen
            gruppe, eltern, argumente = befehl, kontext, _rest(kontext)
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
    richte_stand_ein(ctx, kontext)


def richte_stand_ein(ctx: Any, kontext: Kontext) -> None:
    """Ein neuer Stand der Einstellungen für diesen Befehl (am Ende zurückgesetzt) und
    die Bindung über die Parameter ``db`` (D3, D5)."""
    from accounti.befehle import STANDARD_DB
    from accounti.einstellungen.leser import DatenbankQuelle, neuer_stand

    def ersatz() -> DatenbankQuelle:
        return DatenbankQuelle(kontext.standardwerte.get("db") or STANDARD_DB)

    stand = ctx.with_resource(
        neuer_stand(ersatz=ersatz, fremde_pfade=_fremde_konfigurationen(kontext))
    )
    stand.kuerzel = kontext.kuerzel
    binde_datenbank_parameter(ctx.command)


def _fremde_konfigurationen(kontext: Kontext) -> frozenset[str]:
    """Konfigurationen der anderen Gesellschaften der Registry (aufgelöst) — die liest
    ein Befehl nur unter ``mit_quelle`` ihrer Datenbank (D5, M2)."""
    from accounti.betrieb.gesellschaften import pfad_schluessel

    eigene = kontext.gesellschaft.konfiguration if kontext.gesellschaft else None
    eigene_schluessel = pfad_schluessel(eigene) if eigene else None
    fremde = set()
    for kuerzel in kontext.registry.eintraege:
        try:
            g = kontext.registry.finde(kuerzel)
        except KonfigurationError:
            continue  # fehlende Variable: die Gesellschaft scheitert erst beim Gebrauch
        schluessel = pfad_schluessel(g.konfiguration)
        if schluessel != eigene_schluessel:
            fremde.add(schluessel)
    return frozenset(fremde)


_BINDET = "_accounti_bindet_einstellungen"


def binde_datenbank_parameter(befehl: Any) -> None:
    """An jeden Parameter ``db`` im Befehlsbaum (alle Ebenen) einen Callback hängen,
    der den Stand an diese Datenbank bindet; ein vorhandener Callback läuft vorher. Je
    Parameter einmal (markiert)."""
    for parameter in getattr(befehl, "params", []) or []:
        if parameter.name == "db" and not getattr(parameter, _BINDET, False):
            parameter.callback = _bindend(parameter.callback)
            setattr(parameter, _BINDET, True)
    for kind in (getattr(befehl, "commands", {}) or {}).values():
        binde_datenbank_parameter(kind)


def _bindend(vorher: Any) -> Any:
    def rueckruf(ctx: Any, parameter: Any, wert: Any) -> Any:
        if vorher is not None:
            wert = vorher(ctx, parameter, wert)
        if isinstance(wert, str) and wert and not ctx.resilient_parsing:
            binde_datenbank(wert)
        return wert

    return rueckruf


def binde_datenbank(url: str) -> None:
    """Den Stand des Befehls an ``url`` binden (sofort mit Schnappschuss)."""
    from accounti.einstellungen.leser import DatenbankQuelle, aktueller_stand

    stand = aktueller_stand()
    if stand is not None:
        stand.binde(DatenbankQuelle(url), kuerzel=stand.kuerzel)
