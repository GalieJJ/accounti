"""``accounti gesellschaft`` — eingetragene Gesellschaften anzeigen (Spec 4.4, 4.7).

Kontenrahmen und Wirtschaftsjahr liest jede Gesellschaft aus **ihrer** Datenbank
(``mit_quelle``, Baustein 10c P4, M2) — nicht unter dem Stand des Befehls.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import console
from accounti.betrieb.gesellschaften import Gesellschaft

NAME = "gesellschaft"
befehl = typer.Typer(
    help="Eigene Gesellschaften: je eine Datenbank, ein Archiv, eine Konfiguration.",
    no_args_is_help=True,
)


def _ende(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


@contextmanager
def _eigene_einstellungen(g: Gesellschaft) -> Iterator[None]:
    """Die Einstellungen der Gesellschaft: ihre Datenbank, ihre Datei."""
    from accounti.einstellungen.leser import DatenbankQuelle, mit_quelle

    with mit_quelle(DatenbankQuelle(g.datenbank), g.konfiguration):
        yield


def _wirtschaftsjahr(konfiguration: str) -> str:
    """``datev.wirtschaftsjahr_beginn`` (Tag und Monat; auch ohne Datei, D25)."""
    from accounti.abschluss.konfiguration import lade_wirtschaftsjahr_beginn

    beginn = lade_wirtschaftsjahr_beginn(konfiguration)
    return f"{beginn:%d.%m.}" if beginn else "Kalenderjahr"


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
    from accounti.einstellungen.leser import EinstellungenNichtLesbar
    from accounti.konfiguration import lade_buchhaltung

    for kuerzel in sorted(registry.eintraege):
        eintrag = registry.eintraege[kuerzel]
        try:
            g = registry.finde(kuerzel)
            with _eigene_einstellungen(g):
                rahmen = lade_buchhaltung(g.konfiguration).kontenrahmen
        except (KonfigurationError, EinstellungenNichtLesbar) as fehler:
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
    from accounti.einstellungen.leser import EinstellungenNichtLesbar
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung

    kontext = aktueller_kontext()
    nicht_lesbar: EinstellungenNichtLesbar | None = None
    try:
        g = kontext.pruefe().registry.finde(kuerzel)
        system = kontext.systemdatenbank(g.datenbank)
        try:
            with _eigene_einstellungen(g):
                rahmen = lade_buchhaltung(g.konfiguration).kontenrahmen
                wirtschaftsjahr = _wirtschaftsjahr(g.konfiguration)
        except EinstellungenNichtLesbar as fehler:
            # die übrigen Angaben helfen gerade dann — die Einstellungen nicht raten
            nicht_lesbar = fehler
            rahmen = wirtschaftsjahr = "— (Datenbank nicht lesbar)"
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
        ("Wirtschaftsjahr ab", wirtschaftsjahr),
        ("Systemdatenbank", ohne_passwort(system)),
    ):
        console.print(f"{titel:<20} {escape(wert)}", soft_wrap=True)
    if nicht_lesbar is not None:
        raise _ende(str(nicht_lesbar))
