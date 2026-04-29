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
    datei: str = typer.Argument(help="Pfad zur Bank-CSV/MT940/CAMT-Datei"),
    format: str = typer.Option("auto", help="Bankformat: sparkasse, volksbank, commerzbank, auto"),
) -> None:
    """Banktransaktionen importieren."""
    console.print(f"[bold]Import:[/bold] {datei} (Format: {format})")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 1[/yellow]")


# ---------------------------------------------------------------------------
# Klassifikation
# ---------------------------------------------------------------------------
@app.command()
def classify(
    period: str = typer.Option(..., help="Zeitraum im Format YYYY-MM"),
    dry_run: bool = typer.Option(False, help="Nur anzeigen, nicht speichern"),
) -> None:
    """Transaktionen automatisch kontieren."""
    console.print(f"[bold]Klassifikation:[/bold] Zeitraum {period}")
    if dry_run:
        console.print("[dim]Trockenlauf — keine Änderungen werden gespeichert[/dim]")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 2[/yellow]")


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
    period: str = typer.Option(..., help="Zeitraum im Format YYYY-MM"),
    berater: str = typer.Option(..., help="DATEV Beraternummer"),
    mandant: str = typer.Option(..., help="DATEV Mandantennummer"),
    output: str = typer.Option("./export", help="Ausgabeverzeichnis"),
) -> None:
    """DATEV-konformen Buchungsstapel exportieren."""
    console.print(f"[bold]DATEV-Export:[/bold] {period} → {output}")
    console.print(f"  Berater: {berater}, Mandant: {mandant}")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 1[/yellow]")


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
def db_init() -> None:
    """Datenbank initialisieren."""
    console.print("[bold]Datenbank-Initialisierung[/bold]")
    console.print("[yellow]⚠ Noch nicht implementiert — siehe Roadmap Phase 1[/yellow]")


if __name__ == "__main__":
    app()
