"""``accounti zm`` — Zusammenfassende Meldung (§ 18a UStG, Baustein 9)."""

from __future__ import annotations

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

NAME = "zm"
befehl = typer.Typer(help="Zusammenfassende Meldung: je USt-IdNr., als Portaldatei.")


@befehl.callback(invoke_without_command=True)
def zm(
    period: str = typer.Option(
        ..., "--period", help="Monat oder Quartal, z.B. 2026-Q3"
    ),
    csv_datei: str | None = typer.Option(
        None, "--csv", help="Datei für den ZM-Import im ELSTER-Portal schreiben"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """ZM eines Meldezeitraums — Fehler (z. B. unbestätigte USt-IdNr.) verhindern
    die Datei."""
    from pathlib import Path

    from rich.table import Table

    from accounti.anzeige import datum_de
    from accounti.befehle.ustva import euro, zeige_befunde
    from accounti.db import init_db, session_factory
    from accounti.elster.konfiguration import lade_elster
    from accounti.elster.ustva import bereite_zm_vor
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_ustid_pruefung,
    )
    from accounti.steuer.fristen import zm_frist
    from accounti.steuer.plausibilitaet import freigabe_gesperrt
    from accounti.steuer.zeitraum import Zeitraum, ZeitraumError
    from accounti.steuer.zusammenfassende_meldung import ARTEN

    try:
        zeitraum = Zeitraum.lies(period)
        if zeitraum.art == "jahr":
            raise ZeitraumError("ZM-Meldezeitraum ist der Monat oder das Quartal")
        buchhaltung = lade_buchhaltung(config)
        einstellungen = lade_elster(config)
        max_alter = lade_ustid_pruefung(config).max_alter_tage
    except (ZeitraumError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(2) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        meldung, befunde = bereite_zm_vor(
            s,
            zeitraum,
            buchhaltung=buchhaltung,
            einstellungen=einstellungen,
            ustid_max_alter_tage=max_alter,
        )
    engine.dispose()

    frist = zm_frist(zeitraum)
    if not meldung.zeilen and not befunde and not meldung.ohne_ustid:
        console.print(
            f"{zeitraum.text}: keine EU-Umsätze — keine Zusammenfassende Meldung nötig"
        )
        return
    tabelle = Table(title=f"Zusammenfassende Meldung {zeitraum.text}")
    for spalte in ("USt-IdNr.", "Abnehmer", "Art", "Summe (Euro)"):
        tabelle.add_column(spalte, overflow="fold")
    for z in meldung.zeilen:
        tabelle.add_row(z.ust_id, z.name, z.art, euro(z.betrag))
    console.print(tabelle)
    summen = " · ".join(
        f"{name} {euro(meldung.summe(art))} €"
        for art, name in ARTEN.items()
        if meldung.summe(art)
    )
    console.print(f"  {summen}")
    console.print(
        f"  Abgabe beim BZSt bis {datum_de(frist.faellig_am)}"
        + (
            f" (statt {datum_de(frist.gesetzlich)}, {frist.grund})"
            if frist.verschoben
            else ""
        )
    )
    zeige_befunde(befunde, "ZM nicht abgabereif", "ZM abgabereif[/green]")
    if freigabe_gesperrt(befunde):
        raise typer.Exit(1)
    if csv_datei:
        Path(csv_datei).write_text(meldung.als_csv(), encoding="utf-8")
        console.print(
            f"[green]{len(meldung.zeilen)} Zeilen → {escape(csv_datei)}[/green] "
            "(ELSTER-Portal: ZM-Import, CSV-Version 3.0)"
        )
