"""``accounti elster`` — Protokoll, Zahllast nachholen, Zertifikats-PIN (Baustein 9)."""

from __future__ import annotations

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "elster"
befehl = typer.Typer(
    help="ELSTER: Übermittlungsprotokoll, Zahllast nachholen, Zertifikats-PIN."
)


@befehl.command("protokoll")
def protokoll(
    zeitraum: str | None = typer.Argument(
        None, help="Nur dieser Zeitraum, z.B. 2026-08"
    ),
    csv_datei: str | None = typer.Option(
        None, "--csv", help="Protokoll als CSV (Semikolon) exportieren"
    ),
    db: str = DB_OPTION,
    archiv: str = typer.Option("archiv/belege", "--archiv", help="Archivverzeichnis"),
) -> None:
    """Übermittlungsprotokoll — mit Prüfung von Hash-Kette und Archivdateien."""
    import csv
    from pathlib import Path

    from rich.table import Table

    from accounti.anzeige import betrag_de, datum_de
    from accounti.belege.archiv import BelegArchiv
    from accounti.db import init_db, session_factory
    from accounti.db.repo_elster import lade_uebermittlungen
    from accounti.elster.protokoll import pruefe_protokoll
    from accounti.models.elster import Meldeart, Uebermittlung

    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        alle = lade_uebermittlungen(s)
    engine.dispose()
    befunde = pruefe_protokoll(
        alle, BelegArchiv(archiv) if Path(archiv).is_dir() else None
    )
    eintraege = [u for u in alle if zeitraum is None or u.zeitraum == zeitraum]

    if eintraege:
        tabelle = Table(title="Übermittlungsprotokoll")
        for spalte in ("Nr", "Zeitpunkt", "Meldung", "Modus", "Ticket", "Ergebnis"):
            tabelle.add_column(spalte, overflow="fold")
        for u in eintraege:
            meldung = f"{u.art.value} {u.zeitraum}" + (
                " (ber.)" if u.berichtigt else ""
            )
            kz = 83 if u.art is Meldeart.USTVA else 38  # Sondervorauszahlung
            ergebnis = f"{u.ergebnis} · Kz {kz} {betrag_de(u.betrag)} €"
            if u.freigegeben_von:
                ergebnis += f" · frei: {u.freigegeben_von}"
            tabelle.add_row(
                str(u.nr),
                f"{datum_de(u.zeitpunkt.date())} {u.zeitpunkt:%H:%M:%S}",
                meldung,
                f"{u.modus.value} ({u.weg})",
                u.ticket or "—",
                escape(ergebnis),
                style=None if u.erfolgreich else "red",
            )
        console.print(tabelle)
    else:
        console.print("[dim]Keine Einträge.[/dim]")
    if csv_datei:
        with Path(csv_datei).open("w", encoding="utf-8", newline="") as datei:
            schreiber = csv.DictWriter(
                datei, fieldnames=list(Uebermittlung.model_fields), delimiter=";"
            )
            schreiber.writeheader()
            for u in eintraege:
                zeile = u.model_dump(mode="json")
                zeile["datensatz"] = zeile["datensatz"].replace("\n", " ")
                zeile["pruefbericht"] = zeile["pruefbericht"].replace("\n", " ")
                schreiber.writerow(zeile)
        console.print(f"[dim]{len(eintraege)} Einträge → {escape(csv_datei)}[/dim]")
    if befunde:
        console.print("[red]Protokoll beschädigt:[/red]")
        for befund in befunde:
            console.print(f"  [red]{escape(befund)}[/red]")
        raise typer.Exit(1)
    console.print(
        "[green]Protokoll vollständig und unverändert[/green] — "
        f"{len(alle)} {'Eintrag' if len(alle) == 1 else 'Einträge'}, Hash-Kette geprüft"
    )


@befehl.command("zahllast")
def zahllast(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
    """Fehlende Zahllast-Buchungen zu erfolgreichen Abgaben nachholen."""
    from accounti.befehle.ustva import zeige_zahllast
    from accounti.db import init_db, session_factory
    from accounti.elster.konfiguration import KonfigurationError, lade_elster
    from accounti.elster.ustva import kontext_aus
    from accounti.elster.zahllast import buche_fehlende
    from accounti.konfiguration import lade_buchhaltung

    try:
        einstellungen = lade_elster(config)
        buchhaltung = lade_buchhaltung(config)
        kontext = kontext_aus(config, einstellungen)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(2) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    try:
        with make_session() as s:
            gebucht = buche_fehlende(
                s,
                buchhaltung=buchhaltung,
                einstellungen=einstellungen,
                steuernummer=kontext.steuernummer,
            )
            s.commit()
    finally:
        engine.dispose()
    if not gebucht:
        console.print("[green]Alle Abgaben sind gebucht[/green] — nichts nachzubuchen")
    for z in gebucht:
        zeige_zahllast(z)


@befehl.command("pin")
def pin(config: str = KONFIG_OPTION) -> None:
    """PIN des ELSTER-Zertifikats verschlüsselt ablegen (elster.eric.pin_datei)."""
    from accounti.bank.tresor import TresorError, lade_schluessel
    from accounti.elster.konfiguration import KonfigurationError, lade_elster
    from accounti.elster.pin import PinError, speichere_pin

    try:
        einstellungen = lade_elster(config)
    except KonfigurationError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(2) from fehler
    ziel = einstellungen.eric.pin_datei
    if not ziel:
        console.print("[red]elster.eric.pin_datei fehlt in der Konfiguration[/red]")
        raise typer.Exit(2)
    try:
        schluessel = lade_schluessel()
    except TresorError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(2) from fehler
    eingabe = typer.prompt(
        "PIN des ELSTER-Zertifikats", hide_input=True, confirmation_prompt=True
    )
    try:
        speichere_pin(ziel, eingabe, schluessel)
    except PinError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(1) from fehler
    console.print(f"[green]PIN verschlüsselt abgelegt[/green] → {escape(ziel)}")
