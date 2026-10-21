"""``accounti buchung …`` — Storno und Verlauf einer Buchung (Baustein 7, Spec 4.4)."""

from __future__ import annotations

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console
from accounti.befehle._anlagen_abschluss import datum, ende, sitzung

NAME = "buchung"
befehl = typer.Typer(
    help="Einzelne Buchung: stornieren, mit Storno und Journal anzeigen.",
    no_args_is_help=True,
)


@befehl.command("storniere")
def storniere(
    buchung_id: str = typer.Argument(help="(Anfang der) Buchungs-ID"),
    grund: str = typer.Option(..., "--grund", help="Begründung (Pflicht)"),
    von: str | None = typer.Option(None, help="Wer storniert"),
    tag: str | None = typer.Option(
        None, "--datum", help="Storno-Datum, wenn der Zeitraum abgeschlossen ist"
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Freigegebene Buchung durch Gegenbuchung aufheben (ohne Neubuchung)."""
    from accounti.abschluss.kontenrahmen import KontenrahmenError, lade_kontenrahmen
    from accounti.db.tabellen import UnveraenderbarError
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung
    from accounti.pruefung.storno import StornoError
    from accounti.pruefung.storno import storniere as storno

    try:
        kr = lade_kontenrahmen(lade_buchhaltung(config).kontenrahmen)
    except (KonfigurationError, KontenrahmenError) as fehler:
        ende(str(fehler))
    am = datum(tag, "--datum") if tag else None
    with sitzung(db)() as s:
        try:
            k = storno(s, buchung_id, grund=grund, von=von, datum=am, kontenrahmen=kr)
            s.commit()
        except (StornoError, JahrGesperrtError, UnveraenderbarError) as fehler:
            ende(str(fehler))
    assert k.storno is not None
    console.print(
        f"[green]Storniert:[/green] {str(k.original.id)[:8]} durch Storno "
        f"{str(k.storno.id)[:8]} ({k.storno.soll_konto} an {k.storno.haben_konto}) — "
        "beide bleiben sichtbar"
    )


@befehl.command("zeige")
def zeige(
    buchung_id: str = typer.Argument(help="(Anfang der) Buchungs-ID"),
    db: str = DB_OPTION,
) -> None:
    """Buchung mit Storno-Bezug, Korrektur und Journal."""
    from accounti.anzeige import betrag_de, datum_de
    from accounti.db.repo_pruefung import korrektur_zu
    from accounti.db.repository import finde_buchung
    from accounti.pruefung.journal import lade_journal

    with sitzung(db)() as s:
        try:
            b = finde_buchung(s, buchung_id)
        except ValueError as fehler:
            ende(str(fehler))
        korrektur = korrektur_zu(s, b.id)
        eintraege = lade_journal(s, objekt_id=str(b.id))
    console.print(
        f"[bold]Buchung {str(b.id)[:8]}[/bold] {datum_de(b.datum)} {b.soll_konto} an "
        f"{b.haben_konto} {betrag_de(b.betrag_netto)} €"
        + (
            f" + Steuer {betrag_de(b.steuer_betrag)} € "
            f"(Schlüssel {b.steuer_schluessel})"
            if b.steuer_betrag
            else ""
        )
    )
    console.print(f"  Text       {escape(b.buchungstext)}")
    console.print(f"  Status     {b.status.value} {escape(b.geprueft_von or '')}")
    if b.transaktion_id:
        console.print(f"  Umsatz     {str(b.transaktion_id)[:8]}")
    if b.beleg_id:
        console.print(
            f"  Beleg      {str(b.beleg_id)[:8]} {escape(b.beleg_nummer or '')}"
        )
    if b.storniert_durch:
        console.print(
            f"  [yellow]storniert durch {str(b.storniert_durch)[:8]}[/yellow]"
        )
    if b.storno_von:
        console.print(f"  [yellow]Storno von {str(b.storno_von)[:8]}[/yellow]")
    if korrektur is not None:
        neu = str(korrektur.neubuchung_id)[:8] if korrektur.neubuchung_id else "—"
        console.print(
            f"  Korrektur  Original {str(korrektur.original_id)[:8]} · Storno "
            f"{str(korrektur.storno_id)[:8]} · Neubuchung {neu} · "
            f"{escape(korrektur.person)}: {escape(korrektur.grund)}"
        )
    if eintraege:
        console.print("[bold]Journal[/bold]")
        for e in eintraege:
            console.print(
                f"  {e.nr:>5} {e.zeitpunkt:%d.%m.%Y %H:%M} {e.vorgang:22} "
                f"{escape(e.person)} {escape(e.grund or '')}"
            )
