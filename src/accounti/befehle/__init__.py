"""Befehlsgruppen der Bausteine — jedes Modul hier wird automatisch eingehängt.

Ein Modul definiert ``NAME`` (Name der Befehlsgruppe, z.B. ``"zahlung"``) und
``befehl`` (eine ``typer.Typer``-Instanz). ``accounti.cli`` hängt beim Start alle
Module dieses Pakets ein — ein neuer Baustein braucht so keine Änderung an
``cli.py`` und kommt anderen Bausteinen nicht in die Quere.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.markup import escape

if TYPE_CHECKING:
    from accounti.models.auth import Recht

console = Console()
DB_OPTION = typer.Option("sqlite:///accounti.db", help="DB-URL")
KONFIG_OPTION = typer.Option("config/accounti.yaml", "--config", help="Konfiguration")


@contextmanager
def handelnde_person(
    db: str, config: str, recht: Recht, von: str | None
) -> Iterator[str | None]:
    """Wer handelt — mit eingerichteten Benutzern (Baustein 10) geprüft.

    Mit Benutzern braucht die handelnde Person (``--von``, sonst
    ``ACCOUNTI_BENUTZER`` bzw. der Anmeldename) das Recht und ihren Einmalcode;
    zurück kommt der Benutzername — er steht dann in ``geprueft_von``, im
    Protokoll und als Person im Journal (``journal_kontext``), nicht ein frei
    gewählter Text. Ohne Benutzer bleibt alles wie bisher: zurück kommt ``von``
    (auch ``None``). Fehlt das Recht: Meldung und Exit 1."""
    from accounti.auth.cli import befehlsrecht_oder_ende
    from accounti.pruefung.person import aktuelle_person, journal_kontext

    benutzer = befehlsrecht_oder_ende(db, config, recht, aktuelle_person(von))
    if benutzer is not None:
        with journal_kontext(person=benutzer.name, geprueft=True):
            yield benutzer.name
        return
    with journal_kontext(person=von.strip() if von and von.strip() else None):
        yield von


@contextmanager
def laufsperre_oder_ende(db: str, art: str = "bank") -> Iterator[None]:
    """Je Datenbank höchstens ein Lauf der Art ``art`` (``betrieb.laufsperre``) —
    für ``bank lauf`` und jeden seiner Einzelschritte (abrufen, Kreditkarten,
    zuordnen, abgleichen, kontieren): sonst kontieren zwei Prozesse denselben
    Umsatz. Läuft schon einer, Meldung und Exit 1 statt Warten."""
    from accounti.betrieb.laufsperre import LaufLaeuftError, laufsperre

    try:
        with laufsperre(db, art):
            yield
    except LaufLaeuftError as fehler:
        console.print(f"[red]{escape(str(fehler))}[/red]", soft_wrap=True)
        raise typer.Exit(1) from fehler


def befehlsmodule() -> list[ModuleType]:
    """Alle Module dieses Pakets mit ``NAME`` und ``befehl``, nach Name sortiert."""
    gefunden = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        modul = importlib.import_module(f"{__name__}.{info.name}")
        if isinstance(getattr(modul, "befehl", None), typer.Typer) and isinstance(
            getattr(modul, "NAME", None), str
        ):
            gefunden.append(modul)
    return gefunden
