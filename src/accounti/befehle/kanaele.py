"""Befehlsgruppe ``kanaele`` — Postfächer, Webhook und Connectoren der Belegerfassung.

Abgeholt wird mit ``accounti belege abholen --kanal email|connector``; hier liegen
Zugänge, das Gedächtnis der verarbeiteten Nachrichten und der Webhook.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import typer

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from accounti.belege.kanaele import BelegKanal

NAME = "kanaele"
befehl = typer.Typer(
    help="Beleg-Kanäle: E-Mail-Postfächer, Webhook und Connectoren einrichten."
)


def _ende(text: str) -> None:
    from rich.markup import escape

    console.print(f"[red]{escape(text)}[/red]")
    raise typer.Exit(1)


def _sitzungen(db: str) -> sessionmaker[Session]:
    from accounti.db import init_db, session_factory

    engine, make_session = session_factory(db)
    init_db(engine)
    return make_session


def hole_ab(
    kanal: str,
    quelle: str | None,
    config: str,
    db: str,
    aufnehmen: Callable[[BelegKanal], None],
) -> None:
    """Alle konfigurierten Quellen eines Kanals abholen (für ``belege abholen``).

    Scheitert eine Quelle, geht es mit der nächsten weiter; der Befehl endet dann
    mit Exit-Code 1.
    """
    from rich.markup import escape

    from accounti.belege.kanaele.abholung import KanalError
    from accounti.belege.kanaele.aufbau import baue_kanaele
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.konfiguration import KonfigurationError

    try:
        kanaele = baue_kanaele(kanal, lade_belegkanaele(config), _sitzungen(db), quelle)
    except KonfigurationError as fehler:
        _ende(str(fehler))
        return
    gescheitert = 0
    for k in kanaele:
        console.print(f"[bold]{escape(k.bezeichnung)}[/bold]")
        try:
            aufnehmen(k)
        except KanalError as fehler:
            console.print(f"[red]{escape(str(fehler))}[/red]")
            gescheitert += 1
        for hinweis in k.hinweise:
            console.print(f"  [yellow]Hinweis:[/yellow] {escape(hinweis)}")
    if gescheitert:
        raise typer.Exit(1)


@befehl.command("zugang")
def zugang(
    kanal: str = typer.Argument(help="email oder connector"),
    name: str = typer.Argument(help="Name des Postfachs bzw. Connectors"),
    config: str = KONFIG_OPTION,
    db: str = DB_OPTION,
) -> None:
    """Passwort bzw. API-Schlüssel verdeckt abfragen und verschlüsselt speichern."""
    from rich.markup import escape

    from accounti.bank.tresor import TresorError, lade_schluessel
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.belege.kanaele.zugaenge import speichere_zugang
    from accounti.konfiguration import KonfigurationError

    try:
        einstellungen = lade_belegkanaele(config)
        if kanal == "email":
            einstellungen.postfach(name)
        elif kanal == "connector":
            einstellungen.connector(name)
        else:
            _ende(f"Zugänge gibt es für 'email' und 'connector', nicht für '{kanal}'")
        schluessel = lade_schluessel()
    except (KonfigurationError, TresorError) as fehler:
        _ende(str(fehler))
        return
    frage = "Passwort" if kanal == "email" else "API-Schlüssel"
    geheimnis = typer.prompt(frage, hide_input=True)
    make_session = _sitzungen(db)
    with make_session() as s:
        speichere_zugang(s, kanal, name, geheimnis, schluessel)
        s.commit()
    console.print(
        f"[green]Gespeichert:[/green] Zugang für {kanal} {escape(name)} "
        "— verschlüsselt (ACCOUNTI_SCHLUESSEL)"
    )


@befehl.command("nachrichten")
def nachrichten(
    kanal: str | None = typer.Option(None, help="email, connector oder webhook"),
    quelle: str | None = typer.Option(None, help="Postfach, Connector oder Token"),
    anzahl: int = typer.Option(50, help="höchstens so viele, die jüngsten zuerst"),
    db: str = DB_OPTION,
) -> None:
    """Verarbeitete Nachrichten mit Absender — der Hinweis auf den Kreditor."""
    from rich.markup import escape
    from rich.table import Table

    from accounti.db.repo_kanaele import lade_nachrichten

    with _sitzungen(db)() as s:
        liste = lade_nachrichten(s, kanal=kanal, quelle=quelle, limit=anzahl)
    if not liste:
        console.print("[dim]Keine verarbeiteten Nachrichten.[/dim]")
        return
    tabelle = Table(title="Verarbeitete Nachrichten")
    for spalte in ("Abgeholt", "Kanal", "Quelle", "Absender", "Betreff", "Dateien"):
        tabelle.add_column(spalte, overflow="fold")
    tabelle.add_column("Hinweis", overflow="fold")
    for n in liste:
        absender = n.absender or ""
        if n.absender_name:
            absender = (
                f"{n.absender_name} <{absender}>" if absender else n.absender_name
            )
        tabelle.add_row(
            f"{n.abgeholt_am:%d.%m.%Y %H:%M}",
            n.kanal,
            escape(n.quelle),
            escape(absender or "—"),
            escape(n.betreff or ""),
            str(len(n.datei_hashes)),
            escape(n.hinweis or ""),
        )
    console.print(tabelle)
