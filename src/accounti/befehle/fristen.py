"""``accounti fristen`` — Fristenkalender der Umsatzsteuer-Meldungen (Baustein 9)."""

from __future__ import annotations

from datetime import date

import typer
from rich.markup import escape

from accounti.befehle import KONFIG_OPTION, console

NAME = "fristen"
befehl = typer.Typer(help="Fristenkalender: UStVA, Sondervorauszahlung, ZM, OSS.")


@befehl.callback(invoke_without_command=True)
def fristen(
    jahr: int = typer.Option(date.today().year, "--jahr", help="Meldejahr"),
    quartal: bool | None = typer.Option(
        None, "--quartal/--monat", help="Voranmeldungszeitraum (sonst Konfiguration)"
    ),
    dauerfrist: bool | None = typer.Option(
        None, "--dauerfrist/--ohne-dauerfrist", help="Dauerfristverlängerung"
    ),
    zm: str | None = typer.Option(
        None, "--zm", help="ZM-Meldezeitraum: monat, quartal"
    ),
    oss: bool = typer.Option(False, "--oss", help="OSS-Fristen zeigen"),
    bundesland: str | None = typer.Option(
        None, "--bundesland", help="Feiertage des Landes, z.B. BY"
    ),
    config: str = KONFIG_OPTION,
) -> None:
    """Fristen eines Jahres — verschoben nach § 108 Abs. 3 AO."""
    from rich.table import Table

    from accounti.anzeige import datum_de
    from accounti.elster.konfiguration import (
        BUNDESLAENDER,
        KonfigurationError,
        lade_elster,
        lade_oss,
    )
    from accounti.steuer.fristen import fristenkalender

    try:
        einstellungen = lade_elster(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(2) from fehler
    land = (bundesland or einstellungen.bundesland or "").upper() or None
    if land is not None and land not in BUNDESLAENDER:
        console.print(f"[red]Bundesland {escape(land)} unbekannt[/red]")
        raise typer.Exit(2)
    if zm not in (None, "monat", "quartal"):
        console.print("[red]--zm erwartet monat oder quartal[/red]")
        raise typer.Exit(2)
    art = einstellungen.voranmeldungszeitraum
    if quartal is not None:
        art = "quartal" if quartal else "monat"
    kalender = fristenkalender(
        jahr,
        voranmeldungszeitraum=art,
        dauerfrist=(
            einstellungen.dauerfristverlaengerung if dauerfrist is None else dauerfrist
        ),
        zm="quartal" if zm == "quartal" else "monat" if zm == "monat" else None,
        oss=oss or lade_oss(config),
        bundesland=land,
    )
    feiertage = BUNDESLAENDER[land] if land else "bundeseinheitliche Feiertage"
    tabelle = Table(title=f"Fristenkalender {jahr} ({feiertage})")
    for spalte in ("Fällig am", "Meldung", "Zeitraum", "Hinweis"):
        tabelle.add_column(spalte, overflow="fold")
    heute = date.today()
    for f in kalender:
        hinweis = f"statt {datum_de(f.gesetzlich)} ({f.grund})" if f.verschoben else ""
        stil = "dim" if f.faellig_am < heute else None
        tabelle.add_row(datum_de(f.faellig_am), f.art, f.zeitraum, hinweis, style=stil)
    console.print(tabelle)
    namen = {f.art: f.bezeichnung for f in kalender}
    console.print(
        "[dim]" + " · ".join(f"{a} = {n}" for a, n in namen.items()) + "[/dim]"
    )
    console.print(
        "[dim]§ 108 Abs. 3 AO: Fristende an Samstag, Sonntag oder Feiertag → nächster "
        "Werktag; ZM mit den Feiertagen am Sitz des BZSt (NW); OSS unverschoben.[/dim]"
    )
