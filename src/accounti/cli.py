"""accounti CLI — Kommandozeilenschnittstelle."""

import typer
from rich.console import Console

app = typer.Typer(
    name="accounti",
    help="KI-gestützte Buchhaltungsautomatisierung für deutsche Unternehmen.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Zeigt die aktuelle Version an."""
    from accounti import __version__

    console.print(f"accounti {__version__}")


# ---------------------------------------------------------------------------
# Import-Befehle
# ---------------------------------------------------------------------------
import_app = typer.Typer(help="Transaktionen importieren.")
app.add_typer(import_app, name="import")


@import_app.command("bank")
def import_bank(
    datei: str = typer.Argument(help="Pfad zur Bank-CSV-Datei"),
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    format: str = typer.Option("auto", help="Bankformat (auto = erkennen)"),
) -> None:
    """Banktransaktionen importieren."""
    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_transaktion
    from accounti.importers import BANK_IMPORTERS
    from accounti.importers.profil import (
        EINGEBAUTE_PROFILE,
        importer_fuer_datei,
        lade_banken_profile,
        registriere_profile,
    )

    eigene = lade_banken_profile("config/banken.yaml")
    registriere_profile(eigene)

    if format == "auto":
        try:
            importer = importer_fuer_datei(datei, {**EINGEBAUTE_PROFILE, **eigene})
        except ValueError as fehler:
            console.print(f"[red]{fehler}[/red]")
            raise typer.Exit(1) from fehler
    elif format in BANK_IMPORTERS:
        importer = BANK_IMPORTERS[format]
    else:
        verfuegbar = ", ".join(sorted(BANK_IMPORTERS))
        console.print(
            f"[red]Unbekanntes Format '{format}'. Verfügbar: {verfuegbar}[/red]"
        )
        raise typer.Exit(1)

    transaktionen = importer.importiere(datei)
    engine, make_session = session_factory(db)
    init_db(engine)
    with make_session() as s:
        for tx in transaktionen:
            speichere_transaktion(s, tx)
        s.commit()
    console.print(f"[green]{len(transaktionen)}[/green] Transaktionen importiert.")


@import_app.command("banken")
def import_banken() -> None:
    """Verfügbare Bankformate auflisten."""
    from accounti.importers import BANK_IMPORTERS
    from accounti.importers.profil import lade_banken_profile, registriere_profile

    registriere_profile(lade_banken_profile("config/banken.yaml"))
    console.print("[bold]Verfügbare Bankformate:[/bold]")
    for name in sorted(BANK_IMPORTERS):
        console.print(f"  • {name}")
    console.print("  • [dim]auto (automatische Erkennung)[/dim]")


# ---------------------------------------------------------------------------
# Klassifikation
# ---------------------------------------------------------------------------
@app.command()
def classify(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="LLM-Stufe nutzen"),
) -> None:
    """Transaktionen automatisch kontieren."""
    from accounti.buchung.mapper import zu_buchungssatz
    from accounti.db import session_factory
    from accounti.db.repository import lade_transaktionen, speichere_buchung
    from accounti.klassifikation.engine import (
        STANDARD_REGELN,
        KlassifikationsEngine,
        RegelwerkEngine,
    )
    from accounti.klassifikation.llm import LLMEngine
    from accounti.klassifikation.regeln_loader import lade_regeln

    # Eigene Regeln (config/regeln.yaml) haben Vorrang, dann das Standard-Regelwerk.
    regeln = lade_regeln("config/regeln.yaml")
    if regeln:
        regelwerk = RegelwerkEngine(regeln + STANDARD_REGELN)
    else:
        regelwerk = RegelwerkEngine()
    engine = KlassifikationsEngine(
        regelwerk=regelwerk,
        llm=LLMEngine() if llm else None,
    )

    _, make_session = session_factory(db)
    auto = offen = 0
    with make_session() as s:
        for tx in lade_transaktionen(s):
            erg = engine.klassifiziere(tx)
            if erg is None:
                offen += 1
                continue
            speichere_buchung(s, zu_buchungssatz(tx, erg))
            auto += 1
        s.commit()
    console.print(f"[green]{auto}[/green] kontiert, [yellow]{offen}[/yellow] offen.")


# ---------------------------------------------------------------------------
# BWA
# ---------------------------------------------------------------------------
@app.command()
def bwa(
    period: str = typer.Option(..., help="Zeitraum im Format YYYY-MM"),
    vergleich: bool = typer.Option(False, help="Vorjahresvergleich anzeigen"),
) -> None:
    """Betriebswirtschaftliche Auswertung erstellen."""
    console.print(f"[bold]BWA:[/bold] Zeitraum {period}")
    if vergleich:
        console.print("[dim]Mit Vorjahresvergleich[/dim]")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 2[/yellow]")


# ---------------------------------------------------------------------------
# DATEV-Export
# ---------------------------------------------------------------------------
export_app = typer.Typer(help="Daten exportieren.")
app.add_typer(export_app, name="export")


@export_app.command("datev")
def export_datev(
    db: str = typer.Option("sqlite:///accounti.db", help="DB-URL"),
    berater: str = typer.Option(..., help="DATEV Beraternummer"),
    mandant: str = typer.Option(..., help="DATEV Mandantennummer"),
    output: str = typer.Option("./export", help="Ausgabeverzeichnis"),
) -> None:
    """DATEV-konformen Buchungsstapel exportieren."""
    from accounti.db import session_factory
    from accounti.db.repository import lade_buchungen
    from accounti.export.datev import DATEVConfig, DATEVExporter

    _, make_session = session_factory(db)
    with make_session() as s:
        buchungen = lade_buchungen(s)
    cfg = DATEVConfig(berater_nummer=berater, mandanten_nummer=mandant)
    datei = DATEVExporter(cfg).exportiere(buchungen, output)
    console.print(f"[green]Export:[/green] {datei} ({len(buchungen)} Buchungen)")


@app.command()
def lerne(
    muster: str = typer.Option(..., help="Text-Muster (Regex)"),
    soll: str = typer.Option(..., help="Soll-Konto"),
    haben: str = typer.Option(..., help="Haben-Konto"),
    name: str = typer.Option(..., help="Regel-Name"),
    steuer: int | None = typer.Option(None, help="Steuerschlüssel"),
) -> None:
    """Korrektur als neue Regel speichern (Lernschleife)."""
    from pathlib import Path

    import yaml

    pfad = Path("config/regeln.yaml")
    if pfad.exists():
        regeln = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    else:
        regeln = []
    regeln.append(
        {
            "name": name,
            "muster": muster,
            "feld": "verwendungszweck",
            "soll_konto": soll,
            "haben_konto": haben,
            "steuer_schluessel": steuer,
            "buchungstext": name,
        }
    )
    pfad.write_text(
        yaml.safe_dump(regeln, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    console.print(f"[green]Regel '{name}' gespeichert.[/green]")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host-Adresse"),
    port: int = typer.Option(8400, help="Port"),
) -> None:
    """Web-UI für Supervision starten."""
    console.print(f"[bold]accounti server[/bold] → http://{host}:{port}")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 4[/yellow]")


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------
db_app = typer.Typer(help="Datenbank verwalten.")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init(db: str = typer.Option("sqlite:///accounti.db", help="DB-URL")) -> None:
    """Datenbank initialisieren."""
    from accounti.db import init_db, session_factory

    engine, _ = session_factory(db)
    init_db(engine)
    console.print(f"[green]Datenbank initialisiert:[/green] {db}")


if __name__ == "__main__":
    app()
