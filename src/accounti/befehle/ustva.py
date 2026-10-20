"""``accounti ustva`` — Umsatzsteuer-Voranmeldung (Baustein 9)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from accounti.elster.ustva import Vorbereitung
    from accounti.steuer.plausibilitaet import Befund

NAME = "ustva"
befehl = typer.Typer(
    help="Umsatzsteuer-Voranmeldung: Kennziffern, Prüfung, Freigabe, Übermittlung."
)

PERIOD_OPTION = typer.Option(
    None, "--period", help="Zeitraum, z.B. 2026-08 oder 2026-Q3"
)
_ZEICHEN = {"fehler": "[red]✗ Fehler[/red]", "warnung": "[yellow]! Warnung[/yellow]"}


def euro(wert: object) -> str:
    """Bemessungsgrundlage in vollen Euro mit Tausenderpunkt."""
    from decimal import Decimal

    from accounti.anzeige import betrag_de

    if isinstance(wert, Decimal) and wert == wert.to_integral_value():
        return f"{int(wert):,}".replace(",", ".")
    return betrag_de(wert if isinstance(wert, Decimal) else None)


def vorbereitung(period: str | None, db: str, config: str) -> Vorbereitung:
    """Konfiguration und Daten laden, Zeitraum vorbereiten — oder klar beenden."""
    from accounti.db import init_db, session_factory
    from accounti.elster.konfiguration import lade_elster, lade_oss
    from accounti.elster.ustva import bereite_vor
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_ustid_pruefung,
    )
    from accounti.steuer.zeitraum import Zeitraum, ZeitraumError

    if period is None:
        console.print("[red]Zeitraum fehlt — z.B. --period 2026-08[/red]")
        raise typer.Exit(2)
    try:
        zeitraum = Zeitraum.lies(period)
        buchhaltung = lade_buchhaltung(config)
        einstellungen = lade_elster(config)
        ustid = lade_ustid_pruefung(config)
        oss = lade_oss(config)
    except (ZeitraumError, KonfigurationError) as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]")
        raise typer.Exit(2) from fehler
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        ergebnis = bereite_vor(
            s,
            zeitraum,
            buchhaltung=buchhaltung,
            einstellungen=einstellungen,
            ustid_max_alter_tage=ustid.max_alter_tage,
            oss_aktiv=oss,
        )
    engine.dispose()
    return ergebnis


def zeige_befunde(befunde: list[Befund]) -> None:
    from accounti.steuer.plausibilitaet import freigabe_gesperrt

    for b in befunde:
        zeichen = _ZEICHEN.get(b.schweregrad.value, "[dim]i Hinweis[/dim]")
        console.print(f"  {zeichen}  {escape(b.text)}")
    fehler = sum(1 for b in befunde if b.schweregrad.value == "fehler")
    if freigabe_gesperrt(befunde):
        console.print(
            f"[red bold]Freigabe gesperrt:[/red bold] {fehler} Fehler — erst beheben"
        )
    else:
        console.print("[green]Freigabe möglich[/green] (accounti ustva freigeben)")


def zeige_kennziffern(v: Vorbereitung) -> None:
    from rich.table import Table

    from accounti.anzeige import betrag_de
    from accounti.steuer.voranmeldung import KENNZIFFERN_2026, Art

    va = v.voranmeldung
    tabelle = Table(title=f"Umsatzsteuer-Voranmeldung {v.zeitraum.text}")
    for spalte, ausrichtung in (
        ("Zeile", "right"),
        ("Kz", "right"),
        ("Bezeichnung", "left"),
        ("Bemessungsgrundlage", "right"),
        ("Steuer", "right"),
    ):
        tabelle.add_column(
            spalte,
            justify=ausrichtung,  # type: ignore[arg-type]
            overflow="fold",
        )
    werte = va.formularwerte()
    summen = [
        (37, "37", "Umsatzsteuer", va.umsatzsteuer),
        (45, "38–44", "Vorsteuer", va.vorsteuer),
    ]
    for kz in sorted(werte, key=lambda k: KENNZIFFERN_2026[k].zeile):
        k = KENNZIFFERN_2026[kz]
        while summen and summen[0][0] <= k.zeile:
            _, zeile, name, betrag = summen.pop(0)
            tabelle.add_row(zeile, "", name, "", betrag_de(betrag), style="bold")
        if kz == 83:
            continue
        if k.art is Art.BMG:
            steuer = betrag_de(va.steuer(kz)) if k.satz is not None else ""
            tabelle.add_row(
                str(k.zeile), str(kz), k.bezeichnung, euro(werte[kz]), steuer
            )
        else:
            tabelle.add_row(
                str(k.zeile), str(kz), k.bezeichnung, "", betrag_de(werte[kz])
            )
    art = "Überschuss (Erstattung)" if va.ist_erstattung else "Vorauszahlung"
    tabelle.add_row("50", "83", art, "", betrag_de(va.kz83), style="bold")
    console.print(tabelle)


def als_json(v: Vorbereitung) -> str:
    va = v.voranmeldung
    return json.dumps(
        {
            "zeitraum": str(v.zeitraum),
            "kennziffern": {str(kz): str(w) for kz, w in va.formularwerte().items()},
            "umsatzsteuer": str(va.umsatzsteuer),
            "vorsteuer": str(va.vorsteuer),
            "befunde": [
                {"regel": b.regel, "schweregrad": b.schweregrad.value, "text": b.text}
                for b in v.befunde
            ],
            "freigabe_gesperrt": v.gesperrt,
        },
        ensure_ascii=False,
        indent=2,
    )


@befehl.callback(invoke_without_command=True)
def ustva(
    ctx: typer.Context,
    period: str | None = PERIOD_OPTION,
    json_ausgabe: bool = typer.Option(False, "--json", help="Maschinenlesbar"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Kennziffern (Vordruck 2026) und Plausibilisierung eines Zeitraums."""
    if ctx.invoked_subcommand is not None:
        return
    v = vorbereitung(period, db, config)
    if json_ausgabe:
        typer.echo(als_json(v))
        return
    zeige_kennziffern(v)
    zeige_befunde(v.befunde)


@befehl.command("pruefen")
def pruefen(
    period: str | None = PERIOD_OPTION,
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Nur die Plausibilisierung — Exit 1, wenn die Freigabe gesperrt ist."""
    v = vorbereitung(period, db, config)
    console.print(f"[bold]Prüfung {v.zeitraum.text}[/bold]")
    zeige_befunde(v.befunde)
    if v.gesperrt:
        raise typer.Exit(1)
