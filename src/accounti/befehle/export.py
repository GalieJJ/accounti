"""Befehlsgruppe ``accounti datev`` — Stammdaten, Belege und Kontoauszüge für DATEV.

Der Buchungsstapel ohne Belege bleibt ``accounti export datev``; ``datev belege``
schreibt für denselben Zeitraum einen Buchungsstapel *mit* Beleglink und das
zugehörige Belegpaket — beides zusammen importieren, nicht zusätzlich zum alten Stapel.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from pathlib import Path

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "datev"
befehl = typer.Typer(
    help="DATEV-Übergabe: Debitoren/Kreditoren, Belege mit Beleglink, Kontoauszüge.",
    no_args_is_help=True,
)

ARCHIV_STANDARD = "archiv/belege"
BERATER_OPTION = typer.Option(
    None, help="DATEV-Beraternummer (sonst datev.berater_nummer)"
)
MANDANT_OPTION = typer.Option(
    None, help="DATEV-Mandantennummer (sonst datev.mandanten_nummer)"
)


def zeitraum(text: str) -> tuple[date, date]:
    """``JJJJ-MM`` → erster und letzter Tag des Monats."""
    treffer = re.fullmatch(r"(\d{4})-(\d{2})", text.strip())
    if treffer is None or not 1 <= int(treffer[2]) <= 12:
        console.print(f"[red]Zeitraum {text!r}: Format JJJJ-MM, z.B. 2026-08[/red]")
        raise typer.Exit(1)
    jahr, monat = int(treffer[1]), int(treffer[2])
    return date(jahr, monat, 1), date(jahr, monat, monthrange(jahr, monat)[1])


def _fehler(fehler: Exception) -> typer.Exit:
    console.print(f"[red]{escape(str(fehler))}[/red]")
    return typer.Exit(1)


@befehl.command("stammdaten")
def datev_stammdaten(
    period: str | None = typer.Option(
        None, help="nur Personenkonten mit Buchungen in JJJJ-MM"
    ),
    ausgabe: str = typer.Option("./export", help="Ausgabeverzeichnis"),
    berater: str | None = BERATER_OPTION,
    mandant: str | None = MANDANT_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Debitoren und Kreditoren im DATEV-Format (Kategorie 16, Version 5)."""
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_buchungen, lade_kontakte
    from accounti.export.datev_format import DatevFormatError
    from accounti.export.datev_stammdaten import (
        exportiere_stammdaten,
        lade_datev_mandant,
    )
    from accounti.konfiguration import KonfigurationError
    from accounti.models import KontaktStatus

    von_bis = zeitraum(period) if period else None
    try:
        stichtag = von_bis[0] if von_bis else date.today()
        datev = lade_datev_mandant(config, stichtag, berater, mandant)
    except (KonfigurationError, ValueError) as fehler:
        raise _fehler(fehler) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        kontakte = lade_kontakte(s)
        if von_bis:
            von, bis = von_bis
            konten = {
                konto
                for b in lade_buchungen(s)
                if von <= b.datum <= bis
                for konto in (b.soll_konto, b.haben_konto)
            }
            kontakte = [
                k
                for k in kontakte
                if k.debitor_konto in konten or k.kreditor_konto in konten
            ]
    try:
        pfad, anzahl = exportiere_stammdaten(kontakte, datev, ausgabe)
    except DatevFormatError as fehler:
        raise _fehler(fehler) from fehler
    offen = sum(1 for k in kontakte if k.status is KontaktStatus.ZUR_PRUEFUNG)
    console.print(f"[green]Stammdaten:[/green] {pfad} ({anzahl} Personenkonten)")
    if offen:
        console.print(
            f"[yellow]{offen} Kontakte sind noch nicht bestätigt (accounti kontakte "
            "liste) — sie sind trotzdem enthalten.[/yellow]"
        )


@befehl.command("belege")
def datev_belege(
    period: str = typer.Option(..., help="Zeitraum JJJJ-MM"),
    ausgabe: str = typer.Option(..., help="Belegpaket, z.B. ./belege-08.zip"),
    berater: str | None = BERATER_OPTION,
    mandant: str | None = MANDANT_OPTION,
    archiv: str = typer.Option(ARCHIV_STANDARD, help="Archivverzeichnis"),
    alle: bool = typer.Option(
        False, "--alle", help="Auch ungeprüfte Buchungen exportieren"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Belegpaket (document.xml) und Buchungsstapel mit Beleglink für DATEV."""
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.export.datev_belege import BelegexportError, exportiere_belegpaket
    from accounti.export.datev_format import DatevFormatError
    from accounti.export.datev_stammdaten import lade_datev_mandant
    from accounti.konfiguration import KonfigurationError

    von, bis = zeitraum(period)
    try:
        datev = lade_datev_mandant(config, von, berater, mandant)
        engine, make_session = session_factory(db)
        init_db(engine)
        with make_session() as s:
            ergebnis = exportiere_belegpaket(
                s, BelegArchiv(archiv), datev, von, bis, Path(ausgabe), alle=alle
            )
    except (KonfigurationError, BelegexportError, DatevFormatError) as fehler:
        raise _fehler(fehler) from fehler
    if ergebnis.zip_pfad is None:
        console.print("[yellow]Kein Belegpaket: keine verknüpfbaren Belege.[/yellow]")
    else:
        console.print(
            f"[green]Belegpaket:[/green] {ergebnis.zip_pfad} ({ergebnis.belege} "
            "Belege) — mit DATEV Belegtransfer hochladen, nicht entpacken"
        )
    console.print(
        f"[green]Buchungsstapel:[/green] {ergebnis.stapel_pfad} "
        f"({ergebnis.verknuepft} von {ergebnis.buchungen} Buchungen verknüpft)"
    )
    for befund in ergebnis.befunde:
        console.print(f"  [yellow]{escape(befund)}[/yellow]")
