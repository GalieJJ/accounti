"""``accounti pruefen`` — Prüfregeln über einen Zeitraum (Baustein 7, Spec 4.1)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

import accounti.db.tabellen_pruefung  # noqa: F401 — Journal und Sperren
from accounti.befehle import DB_OPTION, KONFIG_OPTION, console
from accounti.befehle._anlagen_abschluss import datum, ende, sitzung

NAME = "pruefen"
befehl = typer.Typer(
    help="Prüfregeln: Vollständigkeit, Richtigkeit, Zeitgerechtheit, Ordnung."
)

_FARBE = {"fehler": "red", "warnung": "yellow", "hinweis": "cyan"}


@befehl.callback(invoke_without_command=True)
def pruefen(
    ctx: typer.Context,
    period: str | None = typer.Option(
        None, "--period", help="Zeitraum JJJJ-MM oder JJJJ (sonst alles)"
    ),
    regel: Annotated[
        list[str] | None,
        typer.Option("--regel", help="nur diese Regel(n); mehrfach angebbar"),
    ] = None,
    stichtag: str | None = typer.Option(None, help="Stichtag (sonst heute)"),
    archiv: str | None = typer.Option(
        None, help="Belegarchiv für die Pflichtangaben (sonst pruefung.archiv)"
    ),
    ocr: bool = typer.Option(False, "--ocr", help="Scans mit OCR lesen (langsam)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Befunde mit Schweregrad — ändert nichts; Exit 1 bei Fehler-Befunden."""
    if ctx.invoked_subcommand is not None:
        return
    from accounti.belege.archiv import BelegArchiv
    from accounti.konfiguration import (
        KonfigurationError,
        lade_buchhaltung,
        lade_eigene_firma,
    )
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.pruefung.regeln import (
        Kontext,
        PruefungError,
        fuehre_regeln_aus,
        zeitraum,
    )

    try:
        einstellungen = lade_pruefung(config)
        buchhaltung = lade_buchhaltung(config)
        firma = lade_eigene_firma(config)
        von, bis = zeitraum(period)
    except (KonfigurationError, PruefungError) as fehler:
        ende(str(fehler))
    tag = datum(stichtag, "--stichtag") if stichtag else date.today()
    ordner = Path(archiv or einstellungen.archiv)
    engine = None
    if ocr:
        from accounti.belege.ocr.tesseract import TesseractEngine

        engine = TesseractEngine()
    with sitzung(db)() as s:
        k = Kontext(
            s,
            einstellungen,
            buchhaltung,
            tag,
            von,
            bis,
            firma=firma,
            archiv=BelegArchiv(ordner) if ordner.is_dir() else None,
            ocr=engine,
        )
        try:
            bericht = fuehre_regeln_aus(k, regel or None)
        except (KonfigurationError, PruefungError) as fehler:
            ende(str(fehler))
        s.rollback()  # Prüfregeln lesen nur
    titel = f"Prüfung {period or 'gesamt'} (Stichtag {tag:%d.%m.%Y})"
    if not bericht.befunde:
        console.print(
            f"[green]{titel}: keine Befunde[/green] ({len(bericht.regeln)} Regeln)"
        )
        return
    tabelle = Table(title=titel)
    for spalte in ("Schwere", "Regel", "Datum", "Betrag", "Gegenpartei", "Befund"):
        tabelle.add_column(spalte, overflow="fold")
    from accounti.anzeige import betrag_de, datum_de

    for b in bericht.befunde:
        farbe = _FARBE[b.schwere.value]
        tabelle.add_row(
            f"[{farbe}]{b.schwere.value}[/{farbe}]",
            b.regel,
            datum_de(b.datum) if b.datum else "",
            betrag_de(b.betrag) if b.betrag is not None else "",
            escape(b.gegenpartei or ""),
            escape(b.text)
            + (f"\n[dim]→ {escape(b.abhilfe)}[/dim]" if b.abhilfe else ""),
        )
    console.print(tabelle)
    from accounti.models.pruefung import Schwere

    console.print(
        f"[bold]{len(bericht.befunde)} Befunde:[/bold] "
        f"[red]{bericht.anzahl(Schwere.FEHLER)} Fehler[/red], "
        f"[yellow]{bericht.anzahl(Schwere.WARNUNG)} Warnungen[/yellow], "
        f"[cyan]{bericht.anzahl(Schwere.HINWEIS)} Hinweise[/cyan] "
        f"({len(bericht.regeln)} Regeln)"
    )
    if k.archiv is None:
        console.print(
            f"[dim]Belegarchiv {escape(str(ordner))} nicht gefunden — Pflichtangaben "
            "nur aus den gespeicherten Feldern (--archiv).[/dim]"
        )
    if bericht.fehler:
        raise typer.Exit(1)


@befehl.command("regeln")
def regeln(config: str = KONFIG_OPTION) -> None:
    """Alle Prüfregeln mit Kategorie, Schweregrad und Schwellen."""
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.pruefung.regeln import PRUEFREGELN, pruefe_konfiguration

    try:
        einstellungen = lade_pruefung(config)
        pruefe_konfiguration(einstellungen)
    except KonfigurationError as fehler:
        ende(str(fehler))
    tabelle = Table(title="Prüfregeln")
    for spalte in ("Regel", "Kategorie", "Schwere", "Schwellen", "Beschreibung"):
        tabelle.add_column(spalte, overflow="fold")
    for name, r in sorted(
        PRUEFREGELN.items(), key=lambda x: (x[1].kategorie.value, x[0])
    ):
        parameter = r.Parameter.model_validate(einstellungen.regeln.get(name, {}))
        aus = name in einstellungen.abgeschaltet
        schwere = einstellungen.schwere.get(name, r.schwere).value
        tabelle.add_row(
            f"[dim]{name} (aus)[/dim]" if aus else name,
            r.kategorie.value,
            schwere,
            ", ".join(f"{k}={v}" for k, v in parameter.model_dump().items()),
            r.beschreibung,
        )
    console.print(tabelle)
