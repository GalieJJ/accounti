"""``accounti betrieb`` — geplanter Lauf und Aufbewahrungsbericht (Spec 4.6)."""

from __future__ import annotations

from datetime import date

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "betrieb"
befehl = typer.Typer(
    help="Betrieb: geplanter Lauf (bank + aufgaben) und Aufbewahrungsfristen.",
    no_args_is_help=True,
)


@befehl.command("lauf")
def lauf(
    intervall_minuten: float = typer.Option(
        60, "--intervall-minuten", min=1, help="Abstand zwischen zwei Läufen"
    ),
    nur_einmal: bool = typer.Option(False, "--einmal", help="ein Lauf, dann Ende"),
) -> None:
    """``bank lauf`` und ``aufgaben lauf`` je Gesellschaft, wiederholt (Docker)."""
    from accounti.betrieb import planer
    from accounti.betrieb.kontext import aktueller_kontext
    from accounti.betrieb.protokoll import richte_protokoll_ein
    from accounti.konfiguration import KonfigurationError

    richte_protokoll_ein()
    try:
        kontext = aktueller_kontext().pruefe()
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(2) from fehler
    if nur_einmal:
        ergebnisse = planer.einmal(kontext)
        if any(e.code != 0 for e in ergebnisse):
            raise typer.Exit(1)
        return
    planer.schleife(kontext, intervall_minuten)


def _wirtschaftsjahr_beginn(config: str) -> date | None:
    """``datev.wirtschaftsjahr_beginn`` (Tag und Monat) — ohne: Kalenderjahr."""
    from pathlib import Path

    from accounti.betrieb.gesellschaften import lies_yaml
    from accounti.konfiguration import KonfigurationError

    pfad = Path(config)
    if not pfad.is_file():
        return None
    daten = lies_yaml(pfad)
    datev = daten.get("datev") if isinstance(daten, dict) else None
    wert = datev.get("wirtschaftsjahr_beginn") if isinstance(datev, dict) else None
    if wert is None or isinstance(wert, date):
        return wert
    try:
        return date.fromisoformat(str(wert))
    except ValueError as fehler:
        msg = f"datev.wirtschaftsjahr_beginn {wert!r}: Format JJJJ-MM-TT"
        raise KonfigurationError(msg) from fehler


@befehl.command("aufbewahrung")
def aufbewahrung(
    stichtag: str | None = typer.Option(None, help="JJJJ-MM-TT (heute)"),
    institut: bool = typer.Option(
        False,
        "--institut",
        help="Kreditinstitut, Versicherung oder Wertpapierinstitut: Belege 10 Jahre",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Was frühestens ausgesondert werden dürfte — es wird nichts gelöscht."""
    from accounti.anzeige import datum_de
    from accounti.betrieb.aufbewahrung import bericht
    from accounti.betrieb.kontext import gesellschaft_noetig
    from accounti.db import init_db, session_factory
    from accounti.konfiguration import KonfigurationError

    try:
        gesellschaft_noetig()
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    try:
        tag = date.fromisoformat(stichtag) if stichtag else date.today()
    except ValueError as fehler:
        console.print("[red]--stichtag: Datum im Format JJJJ-MM-TT[/red]")
        raise typer.Exit(1) from fehler
    try:
        beginn = _wirtschaftsjahr_beginn(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler
    engine, fabrik = session_factory(db)
    init_db(engine)
    with fabrik() as s:
        zeilen = bericht(s, tag, institut, wirtschaftsjahr_beginn=beginn)
    engine.dispose()
    tabelle = Table(title=f"Aufbewahrung zum {datum_de(tag)}")
    for spalte in (
        "Unterlagen",
        "Frist",
        "Grundlage",
        "Ältester",
        "Frist abgelaufen",
        "Gesamt",
    ):
        tabelle.add_column(spalte, overflow="fold")
    for z in zeilen:
        tabelle.add_row(
            escape(z.bezeichnung),
            f"{z.frist.jahre} Jahre",
            escape(z.frist.grundlage),
            datum_de(z.aeltester),
            str(z.aussonderbar),
            str(z.gesamt),
        )
    console.print(tabelle)
    console.print(
        "Nichts wird automatisch gelöscht. Vor dem Aussondern prüfen: läuft eine "
        "Festsetzungsfrist, Außenprüfung oder ein Rechtsbehelf "
        "(§ 147 Abs. 3 Satz 3 AO)?",
        soft_wrap=True,
    )
