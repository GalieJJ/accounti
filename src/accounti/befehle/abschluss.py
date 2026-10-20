"""``accounti abschluss …`` — Jahresabschluss (Baustein 12)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console
from accounti.befehle._anlagen_abschluss import betrag, datum, ende, lade, sitzung

NAME = "abschluss"
befehl = typer.Typer(
    help="Jahresabschluss: Prüfungen, Salden, Abgrenzungen, EÜR, Saldovortrag."
)

CSV_OPTION = typer.Option("--csv", help="zusätzlich als CSV")


def _einstellungen(config: str):  # type: ignore[no-untyped-def]
    from accounti.abschluss.konfiguration import lade_abschluss

    return lade(lade_abschluss, config)


@befehl.command("saldo")
def saldo(
    konto: str = typer.Option(..., "--konto", help="IBAN des eingerichteten Kontos"),
    stichtag: str = typer.Option(..., "--stichtag", help="z.B. 2026-12-31"),
    saldo_text: str = typer.Option(..., "--saldo", help="Saldo laut Kontoauszug"),
    von: str | None = typer.Option(None, help="Wer erfasst"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,  # noqa: ARG001
) -> None:
    """Saldo laut Kontoauszug zum Stichtag erfassen (für die Bank-Abstimmung)."""
    from accounti.abschluss.pruefungen import erfasse_kontoauszugssaldo
    from accounti.anzeige import betrag_de

    tag = datum(stichtag, "--stichtag")
    wert = betrag(saldo_text, "--saldo")
    with sitzung(db)() as s:
        try:
            erfasse_kontoauszugssaldo(s, konto, tag, wert, von)
        except ValueError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[green]Erfasst:[/green] {escape(konto)} Saldo {betrag_de(wert)} € zum "
        f"{tag:%d.%m.%Y}"
    )


def _befunde_ausgeben(befunde: list) -> None:  # type: ignore[type-arg]
    from accounti.abschluss.pruefungen import Schwere

    farben = {Schwere.FEHLER: "red", Schwere.WARNUNG: "yellow", Schwere.HINWEIS: "dim"}
    for b in befunde:
        f = farben[b.schwere]
        console.print(
            f"[{f}]{b.schwere.value.upper()}[/{f}] {b.pruefung}: {escape(b.text)}"
        )


@befehl.command("pruefen")
def pruefen(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Abschlussprüfungen — Fehler blockieren den Saldovortrag."""
    from accounti.abschluss.pruefungen import blockiert, kontext, pruefe_abschluss

    with sitzung(db)() as s:
        try:
            befunde = pruefe_abschluss(kontext(s, jahr, config))
        except ValueError as fehler:
            ende(str(fehler))
    _befunde_ausgeben(befunde)
    if blockiert(befunde):
        console.print(f"[red]Abschluss {jahr} gesperrt — Fehler beheben.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Abschluss {jahr}: keine Fehler.[/green]")


@befehl.command("susa")
def susa(
    jahr: int = typer.Option(..., help="Geschäftsjahr"),
    bis: str | None = typer.Option(None, help="Stichtag (31.12.)"),
    csv: Annotated[Path | None, CSV_OPTION] = None,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Summen- und Saldenliste (nur freigegebene Buchungen)."""
    from accounti.abschluss.ausgabe import susa_csv
    from accounti.abschluss.salden import summen_und_salden
    from accounti.anzeige import betrag_de

    einst = _einstellungen(config)
    with sitzung(db)() as s:
        liste = summen_und_salden(
            s,
            jahr,
            einst.lade_kontenrahmen(),
            einst.gewinnermittlung,
            datum(bis, "--bis") if bis else None,
        )
    t = Table(title=f"Summen- und Saldenliste {jahr} (bis {liste.bis:%d.%m.%Y})")
    t.add_column("Konto")
    t.add_column("Bezeichnung", overflow="fold")
    for spalte in ("EB", "Soll", "Haben", "Saldo"):
        t.add_column(spalte, justify="right", no_wrap=True)
    for z in liste.zeilen:
        t.add_row(
            z.konto,
            escape(z.bezeichnung),
            betrag_de(z.eb),
            betrag_de(z.soll),
            betrag_de(z.haben),
            betrag_de(z.saldo),
        )
    t.add_row(
        "", "Summe", "", betrag_de(liste.summe_soll), betrag_de(liste.summe_haben), ""
    )
    console.print(t)
    console.print(f"Ergebnis (Erfolgskonten): {betrag_de(liste.ergebnis)} €")
    if csv is not None:
        csv.write_text(susa_csv(liste), encoding="utf-8")
        console.print(f"[green]CSV:[/green] {csv}")
