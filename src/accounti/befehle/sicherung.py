"""``accounti sicherung`` — Datenbank und Belegarchiv verschlüsselt sichern (Spec 4.6).

Schlüssel aus ``ACCOUNTI_SICHERUNG_SCHLUESSEL`` (sonst ``ACCOUNTI_SCHLUESSEL``) — ohne
Schlüssel wird nichts geschrieben. Den Schlüssel getrennt von den Sicherungen
aufbewahren: Wer beides hat, hat alle Buchungen und Belege.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, console

NAME = "sicherung"
befehl = typer.Typer(
    help="Datenbank und Belegarchiv sichern: erstellen, prüfen, wiederherstellen.",
    no_args_is_help=True,
)

ARCHIV_OPTION = typer.Option("archiv/belege", "--archiv", help="Belegarchiv")
ZIEL_OPTION = typer.Option(
    ..., "--ziel", help="Datei oder vorhandener Ordner (dann mit Zeitstempel)"
)
DATEI_ARGUMENT = typer.Argument(help="Sicherungsdatei")
OHNE_ARCHIV_OPTION = typer.Option(
    False, "--ohne-archiv", help="nur die Datenbank (z.B. die Systemdatenbank)"
)


def _ende(text: str) -> typer.Exit:
    console.print(f"[red]{escape(text)}[/red]", soft_wrap=True)
    return typer.Exit(1)


def _schluessel() -> bytes:
    from accounti.betrieb.verschluesselung import (
        SicherungsschluesselError,
        lade_sicherungsschluessel,
    )

    try:
        return lade_sicherungsschluessel()
    except SicherungsschluesselError as fehler:
        raise _ende(str(fehler)) from fehler


def _zusammenfassung(wort: str, e: object) -> None:
    from accounti.betrieb.sicherung import Ergebnis

    assert isinstance(e, Ergebnis)
    console.print(
        f"[green]{wort}[/green]: {len(e.tabellen)} Tabellen, {e.zeilen} Zeilen "
        f"(davon {e.tabellen.get('buchungssaetze', 0)} Buchungen, "
        f"{e.tabellen.get('belege', 0)} Belege), {e.dateien} Archivdateien "
        f"({e.bytes_archiv / 1024 / 1024:.1f} MB)",
        soft_wrap=True,
    )


@befehl.command("schluessel")
def schluessel() -> None:
    """Neuen 256-Bit-Schlüssel für ACCOUNTI_SICHERUNG_SCHLUESSEL ausgeben."""
    from accounti.bank.tresor import neuer_schluessel

    console.print(neuer_schluessel(), markup=False, highlight=False)
    console.print(
        "[dim]In die Umgebung (ACCOUNTI_SICHERUNG_SCHLUESSEL) und getrennt von den "
        "Sicherungen aufbewahren — ohne ihn ist keine Sicherung lesbar.[/dim]",
        soft_wrap=True,
    )


@befehl.command("erstellen")
def erstellen(
    ziel: str = ZIEL_OPTION,
    db: str = DB_OPTION,
    archiv: str = ARCHIV_OPTION,
    ohne_archiv: bool = OHNE_ARCHIV_OPTION,
) -> None:
    """Datenbank und Belegarchiv verschlüsselt in eine Datei sichern."""
    from accounti.betrieb.kontext import gesellschaft_noetig
    from accounti.betrieb.sicherung import SicherungError, erstelle
    from accounti.konfiguration import KonfigurationError

    try:
        kontext = gesellschaft_noetig()
    except KonfigurationError as fehler:
        raise _ende(str(fehler)) from fehler
    datei = Path(ziel)
    if ziel.endswith(("/", "\\")) or datei.is_dir():
        # Ordner: Dateiname mit Gesellschaft und Zeitstempel
        datei.mkdir(parents=True, exist_ok=True)
        stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
        datei = datei / f"accounti-{kontext.kuerzel}-{stempel}.sicherung"
    try:
        e = erstelle(
            db,
            None if ohne_archiv else Path(archiv),
            datei,
            _schluessel(),
            gesellschaft=kontext.kuerzel,
        )
    except (SicherungError, OSError) as fehler:
        raise _ende(str(fehler)) from fehler
    _zusammenfassung(f"Gesichert nach {escape(str(datei))}", e)
    console.print(
        "[dim]Wiederherstellung üben: accounti sicherung wiederherstellen DATEI "
        "--db sqlite:////tmp/probe/x.db --archiv /tmp/probe/archiv[/dim]",
        soft_wrap=True,
    )


@befehl.command("pruefen")
def pruefen(datei: Path = DATEI_ARGUMENT) -> None:
    """Entschlüsseln und gegen das Manifest prüfen, ohne etwas zu schreiben."""
    from accounti.betrieb.sicherung import SicherungError, pruefe
    from accounti.betrieb.verschluesselung import (
        ManipuliertError,
        SicherungsschluesselError,
    )

    try:
        e = pruefe(datei, _schluessel())
    except (SicherungError, ManipuliertError, SicherungsschluesselError, OSError) as f:
        raise _ende(str(f)) from f
    _zusammenfassung("Sicherung vollständig und unverändert", e)
    console.print(
        f"Erstellt {escape(str(e.manifest.get('erstellt_am')))} mit accounti "
        f"{escape(str(e.manifest.get('accounti')))} aus "
        f"{escape(str(e.manifest.get('datenbank')))}",
        soft_wrap=True,
    )


@befehl.command("wiederherstellen")
def wiederherstellen(
    datei: Path = DATEI_ARGUMENT,
    db: str = DB_OPTION,
    archiv: str = ARCHIV_OPTION,
    ohne_archiv: bool = OHNE_ARCHIV_OPTION,
) -> None:
    """In eine LEERE Datenbank und ein leeres Archiv — alles oder nichts."""
    from accounti.betrieb.kontext import gesellschaft_noetig
    from accounti.betrieb.sicherung import SicherungError, stelle_wieder_her
    from accounti.betrieb.verschluesselung import (
        ManipuliertError,
        SicherungsschluesselError,
    )
    from accounti.konfiguration import KonfigurationError

    try:
        gesellschaft_noetig()
    except KonfigurationError as fehler:
        raise _ende(str(fehler)) from fehler
    try:
        e = stelle_wieder_her(
            datei, db, None if ohne_archiv else Path(archiv), _schluessel()
        )
    except (SicherungError, ManipuliertError, SicherungsschluesselError, OSError) as f:
        raise _ende(str(f)) from f
    _zusammenfassung("Wiederhergestellt", e)
