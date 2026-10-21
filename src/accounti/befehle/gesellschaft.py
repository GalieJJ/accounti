"""``accounti gesellschaft`` — eingetragene Gesellschaften anzeigen (Spec 4.4, 4.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from rich.markup import escape
from rich.table import Table

from accounti.befehle import console

NAME = "gesellschaft"
befehl = typer.Typer(
    help="Eigene Gesellschaften: je eine Datenbank, ein Archiv, eine Konfiguration.",
    no_args_is_help=True,
)


def _ende(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


def _wirtschaftsjahr(konfiguration: str) -> str:
    pfad = Path(konfiguration)
    if not pfad.is_file():
        return "—"
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    datev = daten.get("datev") if isinstance(daten, dict) else None
    beginn = datev.get("wirtschaftsjahr_beginn") if isinstance(datev, dict) else None
    return str(beginn) if beginn else "Kalenderjahr"


@befehl.command("liste")
def liste() -> None:
    """Alle Gesellschaften der Registry (Abschnitt gesellschaften)."""
    from accounti.betrieb.kontext import aktueller_kontext
    from accounti.konfiguration import KonfigurationError

    kontext = aktueller_kontext()
    try:
        kontext.pruefe()
    except KonfigurationError as fehler:
        raise _ende(str(fehler)) from fehler
    registry = kontext.registry
    if not registry.eintraege:
        console.print(
            "Eine Gesellschaft ([bold]standard[/bold]) — Datenbank, Archiv und "
            "Konfiguration aus den Optionen bzw. ACCOUNTI_DB, ACCOUNTI_ARCHIV, "
            "ACCOUNTI_KONFIG. Mehrere: Abschnitt gesellschaften in "
            f"{escape(kontext.globale_konfiguration)}.",
            soft_wrap=True,
        )
        return
    tabelle = Table(title="Gesellschaften")
    for spalte in ("Kürzel", "Name", "Kontenrahmen", "Standard"):
        tabelle.add_column(spalte, overflow="fold")
    from accounti.konfiguration import lade_buchhaltung

    for kuerzel in sorted(registry.eintraege):
        eintrag = registry.eintraege[kuerzel]
        try:
            g = registry.finde(kuerzel)
            rahmen = lade_buchhaltung(g.konfiguration).kontenrahmen
        except KonfigurationError as fehler:
            rahmen = f"[red]{escape(str(fehler))}[/red]"
        tabelle.add_row(
            kuerzel,
            escape(eintrag.name),
            rahmen,
            "✓" if kuerzel == registry.standard else "",
        )
    console.print(tabelle)


@befehl.command("zeigen")
def zeigen(kuerzel: str = typer.Argument(help="Kürzel der Gesellschaft")) -> None:
    """Datenbank, Archiv, Konfiguration, Kontenrahmen und Wirtschaftsjahr."""
    from accounti.betrieb.kontext import aktueller_kontext, ohne_passwort
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    kontext = aktueller_kontext()
    try:
        g = kontext.pruefe().registry.finde(kuerzel)
        rahmen = lade_buchhaltung(g.konfiguration).kontenrahmen
        system = kontext.systemdatenbank(g.datenbank)
    except KonfigurationError as fehler:
        raise _ende(str(fehler)) from fehler
    for titel, wert in (
        ("Kürzel", g.kuerzel),
        ("Name", g.name),
        ("Datenbank", ohne_passwort(g.datenbank)),
        ("Belegarchiv", g.archiv),
        ("Konfiguration", g.konfiguration),
        ("Regeln", g.regeln),
        ("Kontenrahmen", rahmen),
        ("Wirtschaftsjahr ab", _wirtschaftsjahr(g.konfiguration)),
        ("Systemdatenbank", ohne_passwort(system)),
    ):
        console.print(f"{titel:<20} {escape(wert)}", soft_wrap=True)
