"""``accounti verfahrensdoku`` — Verfahrensdokumentation aus dem Systemzustand."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console
from accounti.befehle._anlagen_abschluss import sitzung

NAME = "verfahrensdoku"
befehl = typer.Typer(
    help="Verfahrensdokumentation (GoBD Rz. 151 ff.) aus dem eingerichteten System."
)


@befehl.callback(invoke_without_command=True)
def verfahrensdoku(
    ctx: typer.Context,
    ausgabe: str = typer.Option(
        "verfahrensdoku.md", "--ausgabe", help="Markdown-Datei"
    ),
    pdf: str | None = typer.Option(None, "--pdf", help="zusätzlich als PDF"),
    archiv: str | None = typer.Option(None, help="Belegarchiv (nur zur Angabe)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Erzeugen, speichern und die Fassung (SHA-256) im Journal vermerken."""
    if ctx.invoked_subcommand is not None:
        return
    from accounti.betrieb.kontext import aktueller_kontext
    from accounti.pruefung.verfahrensdoku import als_pdf, erzeuge, fassung, vermerke

    system_db = aktueller_kontext().systemdatenbank(db)
    with sitzung(db)() as s:
        text = erzeuge(s, config, db_url=db, archiv=archiv, system_db=system_db)
        ziel = Path(ausgabe)
        ziel.write_text(text, encoding="utf-8")
        vermerke(s, text, ziel.name)
        s.commit()
    console.print(
        f"[green]Verfahrensdokumentation:[/green] {escape(str(ziel))} (Fassung "
        f"{fassung(text)[:16]}, im Journal vermerkt)"
    )
    if pdf:
        als_pdf(text, pdf)
        console.print(f"[green]PDF:[/green] {escape(pdf)}")
    console.print(
        "[dim]Abschnitte ohne Angabe (z.B. Datensicherung) ergänzt der Betrieb.[/dim]"
    )
