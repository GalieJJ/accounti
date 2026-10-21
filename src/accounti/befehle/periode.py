"""``accounti periode …`` — Monate festschreiben und (begründet) wieder öffnen."""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, console
from accounti.befehle._anlagen_abschluss import ende, sitzung

NAME = "periode"
befehl = typer.Typer(
    help="Periodenabschluss: Monat festschreiben, begründet wieder öffnen.",
    no_args_is_help=True,
)


@befehl.command("schliessen")
def schliessen(
    monat: str = typer.Argument(help="Monat JJJJ-MM, z.B. 2026-08"),
    trotzdem: bool = typer.Option(
        False, "--trotzdem", help="auch mit ungebuchten Umsätzen schließen"
    ),
    von: str | None = typer.Option(None, help="Wer schließt"),
    db: str = DB_OPTION,
) -> None:
    """Monat festschreiben — danach nimmt er keine Buchung mehr an."""
    from accounti.pruefung.perioden import PeriodeError, schliesse
    from accounti.pruefung.person import aktuelle_person

    with sitzung(db)() as s:
        try:
            p = schliesse(s, monat, aktuelle_person(von), trotzdem=trotzdem)
            s.commit()
        except PeriodeError as fehler:
            ende(str(fehler))
    console.print(
        f"[green]{p.monat} festgeschrieben[/green] von {escape(p.geschlossen_von)} — "
        "Korrekturen nur noch per Storno in einem offenen Monat"
    )


@befehl.command("oeffnen")
def oeffnen(
    monat: str = typer.Argument(help="Monat JJJJ-MM"),
    grund: str = typer.Option(..., "--grund", help="Begründung (Pflicht)"),
    von: str | None = typer.Option(None, help="Wer öffnet"),
    db: str = DB_OPTION,
) -> None:
    """Monat wieder öffnen — protokolliert und begründet."""
    from accounti.pruefung.perioden import PeriodeError, oeffne
    from accounti.pruefung.person import aktuelle_person

    with sitzung(db)() as s:
        try:
            p = oeffne(s, monat, aktuelle_person(von), grund)
            s.commit()
        except PeriodeError as fehler:
            ende(str(fehler))
    console.print(
        f"[yellow]{p.monat} wieder geöffnet[/yellow] von "
        f"{escape(p.geoeffnet_von or '')}: {escape(p.grund or '')}"
    )


@befehl.command("liste")
def liste(db: str = DB_OPTION) -> None:
    """Festgeschriebene und wieder geöffnete Monate, gesperrte Geschäftsjahre."""
    from accounti.db.repo_abschluss import lade_gesperrte_jahre
    from accounti.pruefung.perioden import lade_perioden

    with sitzung(db)() as s:
        perioden = lade_perioden(s)
        jahre = sorted(lade_gesperrte_jahre(s))
    if not perioden and not jahre:
        console.print("[yellow]Kein Monat und kein Jahr abgeschlossen.[/yellow]")
        return
    if jahre:
        console.print(
            "[bold]Geschäftsjahre abgeschlossen:[/bold] "
            + ", ".join(str(j) for j in jahre)
            + " [dim](accounti abschluss oeffnen)[/dim]"
        )
    if perioden:
        tabelle = Table(title="Monate")
        for spalte in ("Monat", "Stand", "geschlossen", "geöffnet", "Grund"):
            tabelle.add_column(spalte, overflow="fold")
        for p in perioden:
            tabelle.add_row(
                p.monat,
                "festgeschrieben" if p.gesperrt else "offen",
                f"{p.geschlossen_am:%d.%m.%Y} {escape(p.geschlossen_von)}",
                (
                    f"{p.geoeffnet_am:%d.%m.%Y} {escape(p.geoeffnet_von or '')}"
                    if p.geoeffnet_am
                    else ""
                ),
                escape(p.grund or ""),
            )
        console.print(tabelle)
