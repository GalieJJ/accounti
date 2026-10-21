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
from sqlalchemy.exc import SQLAlchemyError

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
OHNE_ARCHIV_OPTION = typer.Option(False, "--ohne-archiv", help="nur die Datenbank")
SYSTEM_OPTION = typer.Option(
    False,
    "--system",
    help="die Systemdatenbank (Benutzer, Rollen, Token) statt einer Gesellschaft",
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
    if e.system:
        console.print(
            f"[green]{wort}[/green] (Systemdatenbank): {len(e.tabellen)} Tabellen, "
            f"{e.zeilen} Zeilen (davon {e.tabellen.get('auth_benutzer', 0)} Benutzer)",
            soft_wrap=True,
        )
        return
    console.print(
        f"[green]{wort}[/green]: {len(e.tabellen)} Tabellen, {e.zeilen} Zeilen "
        f"(davon {e.tabellen.get('buchungssaetze', 0)} Buchungen, "
        f"{e.tabellen.get('belege', 0)} Belege), {e.dateien} Archivdateien "
        f"({e.bytes_archiv / 1024 / 1024:.1f} MB)",
        soft_wrap=True,
    )
    if e.fehlende:
        console.print(
            f"[yellow]{e.fehlende} Belege ohne Datei im Archiv[/yellow] (Hashes im "
            "Manifest unter fehlende_archivdateien)",
            soft_wrap=True,
        )


def _nicht_erreichbar(db: str, fehler: Exception) -> typer.Exit:
    """Datenbank nicht erreichbar oder abgelehnt — die Art und die Adresse ohne
    Passwort, nicht die Meldung des Treibers."""
    from accounti.betrieb.kontext import ohne_passwort

    return _ende(
        f"Die Datenbank ist nicht erreichbar oder lehnt ab ({type(fehler).__name__}) "
        f"— Adresse {ohne_passwort(db)} prüfen"
    )


def _ausdruecklich(ctx: typer.Context, name: str) -> bool:
    """Stand die Option auf der Befehlszeile (nicht aus Gesellschaft/Standard)?"""
    quelle = ctx.get_parameter_source(name)
    return getattr(quelle, "name", "") == "COMMANDLINE"


def _systemdatenbank(ctx: typer.Context, db: str) -> str:
    """``--db`` von der Befehlszeile, sonst die Systemdatenbank des Kontexts."""
    from accounti.betrieb.kontext import aktueller_kontext

    if _ausdruecklich(ctx, "db"):
        return db
    return aktueller_kontext().pruefe().systemdatenbank(db)


def freier_name(ordner: Path, bezeichnung: str) -> Path:
    """``accounti-<bezeichnung>-<stempel>.sicherung`` — in derselben Sekunde mit
    ``-2``, ``-3`` … statt eines Fehlers."""
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    basis = f"accounti-{bezeichnung}-{stempel}"
    datei = ordner / f"{basis}.sicherung"
    nummer = 2
    while datei.exists():
        datei = ordner / f"{basis}-{nummer}.sicherung"
        nummer += 1
    return datei


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
    ctx: typer.Context,
    ziel: str = ZIEL_OPTION,
    db: str = DB_OPTION,
    archiv: str = ARCHIV_OPTION,
    ohne_archiv: bool = OHNE_ARCHIV_OPTION,
    system: bool = SYSTEM_OPTION,
) -> None:
    """Datenbank und Belegarchiv verschlüsselt in eine Datei sichern."""
    from accounti.betrieb.kontext import gesellschaft_noetig
    from accounti.betrieb.sicherung import SicherungError, erstelle
    from accounti.konfiguration import KonfigurationError

    kuerzel: str | None = None
    try:
        if system:
            quelle = _systemdatenbank(ctx, db)
        else:
            kuerzel = gesellschaft_noetig().kuerzel
            quelle = db
    except KonfigurationError as fehler:
        raise _ende(str(fehler)) from fehler
    datei = Path(ziel)
    if ziel.endswith(("/", "\\")) or datei.is_dir():
        # Ordner: Dateiname mit Gesellschaft (bzw. „system“) und Zeitstempel
        datei.mkdir(parents=True, exist_ok=True)
        datei = freier_name(datei, kuerzel or "system")
    try:
        e = erstelle(
            quelle,
            None if ohne_archiv or system else Path(archiv),
            datei,
            _schluessel(),
            gesellschaft=kuerzel,
            system=system,
        )
    except (SicherungError, OSError) as fehler:
        raise _ende(str(fehler)) from fehler
    except SQLAlchemyError as fehler:
        raise _nicht_erreichbar(quelle, fehler) from fehler
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
    if not e.system and e.manifest.get("gesellschaft"):
        console.print(
            f"Gesellschaft {escape(str(e.manifest['gesellschaft']))}", soft_wrap=True
        )
    console.print(
        f"Erstellt {escape(str(e.manifest.get('erstellt_am')))} mit accounti "
        f"{escape(str(e.manifest.get('accounti')))} aus "
        f"{escape(str(e.manifest.get('datenbank')))}",
        soft_wrap=True,
    )


@befehl.command("wiederherstellen")
def wiederherstellen(
    ctx: typer.Context,
    datei: Path = DATEI_ARGUMENT,
    db: str = DB_OPTION,
    archiv: str = ARCHIV_OPTION,
    ohne_archiv: bool = OHNE_ARCHIV_OPTION,
    system: bool = SYSTEM_OPTION,
    fremde: bool = typer.Option(
        False,
        "--fremde-gesellschaft",
        help="Sicherung einer anderen Gesellschaft bewusst übernehmen",
    ),
) -> None:
    """In eine LEERE Datenbank und ein leeres Archiv — alles oder nichts."""
    from accounti.betrieb.kontext import gesellschaft_noetig
    from accounti.betrieb.sicherung import SicherungError, stelle_wieder_her
    from accounti.betrieb.verschluesselung import (
        ManipuliertError,
        SicherungsschluesselError,
    )
    from accounti.konfiguration import KonfigurationError

    kuerzel: str | None = None
    try:
        if system:
            ziel_db = _systemdatenbank(ctx, db)
        else:
            kuerzel = gesellschaft_noetig().kuerzel
            ziel_db = db
    except KonfigurationError as fehler:
        raise _ende(str(fehler)) from fehler
    try:
        e = stelle_wieder_her(
            datei,
            ziel_db,
            None if ohne_archiv or system else Path(archiv),
            _schluessel(),
            gesellschaft=kuerzel,
            fremde=fremde,
            system=system,
        )
    except (SicherungError, ManipuliertError, SicherungsschluesselError, OSError) as f:
        raise _ende(str(f)) from f
    except SQLAlchemyError as fehler:
        raise _nicht_erreichbar(ziel_db, fehler) from fehler
    _zusammenfassung("Wiederhergestellt", e)
    if fremde and kuerzel is not None:
        _binde_neu(ziel_db, kuerzel)


def _binde_neu(db: str, kuerzel: str) -> None:
    """Merker der Herkunft durch die Bindung an das Ziel ersetzen (Nachprüfung)."""
    from accounti.auth.cli import binde_neu
    from accounti.auth.fehler import AuthError
    from accounti.konfiguration import KonfigurationError

    try:
        binde_neu(db, kuerzel)
    except (AuthError, KonfigurationError) as fehler:
        console.print(
            f"[yellow]Die Bindung an die Benutzerverwaltung ließ sich nicht neu "
            f"setzen: {escape(str(fehler))}[/yellow]",
            soft_wrap=True,
        )
        return
    console.print(
        f"Bindung an die Benutzerverwaltung jetzt: Gesellschaft {escape(kuerzel)}",
        soft_wrap=True,
    )
