"""``accounti journal …`` — das unveränderbare Journal (Baustein 7, Spec 4.3)."""

from __future__ import annotations

import json

import typer
from rich.markup import escape
from rich.table import Table

# Journal-Ereignisse und Storno-Regel hängen am Import der Tabellen — die CLI lädt
# jede Befehlsgruppe beim Start, so gelten sie auch in Befehlen ohne init_db.
from accounti.befehle import DB_OPTION, KONFIG_OPTION, console, handelnde_person
from accounti.befehle._anlagen_abschluss import datum, ende, sitzung

NAME = "journal"
befehl = typer.Typer(
    help="Journal: jede Buchung, Änderung, Freigabe, Storno, Export — hash-verkettet."
)


@befehl.callback(invoke_without_command=True)
def journal(
    ctx: typer.Context,
    von: str | None = typer.Option(None, "--von", help="ab Datum (JJJJ-MM-TT)"),
    bis: str | None = typer.Option(None, "--bis", help="bis Datum (JJJJ-MM-TT)"),
    objekt: str | None = typer.Option(
        None, "--objekt", help="nur dieses Objekt (Anfang der ID)"
    ),
    vorgang: str | None = typer.Option(
        None, "--vorgang", help="z.B. buchung_storniert"
    ),
    db: str = DB_OPTION,
) -> None:
    """Journaleinträge im Zeitraum anzeigen."""
    if ctx.invoked_subcommand is not None:
        return
    from accounti.pruefung.journal import lade_journal

    ab = datum(von, "--von") if von else None
    ende_tag = datum(bis, "--bis") if bis else None
    with sitzung(db)() as s:
        eintraege = lade_journal(
            s, von=ab, bis=ende_tag, objekt_id=objekt, vorgang=vorgang
        )
    if not eintraege:
        console.print("[yellow]Keine Journaleinträge.[/yellow]")
        return
    tabelle = Table(title=f"Journal ({len(eintraege)} Einträge)")
    for spalte in ("Nr", "Zeitpunkt", "Person", "Vorgang", "Objekt", "Grund"):
        tabelle.add_column(spalte, overflow="fold")
    for e in eintraege:
        tabelle.add_row(
            str(e.nr),
            f"{e.zeitpunkt:%d.%m.%Y %H:%M:%S}",
            escape(e.person),
            e.vorgang,
            f"{e.objekt_typ} {escape(e.objekt_id[:8])}",
            escape(e.grund or ""),
        )
    console.print(tabelle)
    console.print("[dim]Einzelheiten: accounti journal zeige NR[/dim]")


@befehl.command("zeige")
def zeige(
    nr: int = typer.Argument(help="Nummer des Eintrags"),
    db: str = DB_OPTION,
) -> None:
    """Ein Eintrag mit Vorher/Nachher."""
    from accounti.pruefung.journal import lade_eintrag

    with sitzung(db)() as s:
        e = lade_eintrag(s, nr)
    if e is None:
        ende(f"Kein Journaleintrag {nr}")
    console.print(f"[bold]Eintrag {e.nr}[/bold] — {e.vorgang}")
    for name, wert in (
        ("Zeitpunkt", f"{e.zeitpunkt:%d.%m.%Y %H:%M:%S}"),
        ("Person", e.person),
        ("Objekt", f"{e.objekt_typ} {e.objekt_id}"),
        ("Grund", e.grund or "—"),
        ("Bezug", e.bezug or "—"),
        ("Hash", e.hash),
        ("Vorgänger", e.vorgaenger_hash),
    ):
        console.print(f"  {name:10} {escape(wert)}")
    vorher = json.loads(e.vorher) if e.vorher else {}
    nachher = json.loads(e.nachher) if e.nachher else {}
    if vorher and nachher:
        tabelle = Table(title="Geändert")
        for spalte in ("Feld", "vorher", "nachher"):
            tabelle.add_column(spalte, overflow="fold")
        for feld in sorted(set(vorher) | set(nachher)):
            if vorher.get(feld) != nachher.get(feld):
                tabelle.add_row(
                    feld, escape(str(vorher.get(feld))), escape(str(nachher.get(feld)))
                )
        console.print(tabelle)
    elif nachher or vorher:
        stand = nachher or vorher
        console.print("[bold]Nachher[/bold]" if nachher else "[bold]Vorher[/bold]")
        for feld in sorted(stand):
            console.print(f"  {feld:20} {escape(str(stand[feld]))}")


@befehl.command("pruefen")
def pruefen(
    kopf: str | None = typer.Option(
        None, "--kopf", help="zuletzt notierter Kopf NR:HASH (Anfang genügt)"
    ),
    db: str = DB_OPTION,
) -> None:
    """Verkettung prüfen und Bestand abgleichen — Exit 1 bei jedem Befund."""
    from accounti.pruefung.journal import pruefe_journal

    with sitzung(db)() as s:
        p = pruefe_journal(s, kopf=kopf)
    if not p.vorhanden:
        ende("Diese Datenbank hat kein Journal (accounti db init legt es an)")
    if p.in_ordnung:
        console.print(
            f"[green]Journal in Ordnung:[/green] {p.anzahl} Einträge, Kette "
            "geschlossen, Bestand stimmt mit dem Journal überein."
        )
    else:
        console.print(f"[red bold]{len(p.befunde)} Befunde im Journal:[/red bold]")
        for b in p.befunde:
            console.print(f"  [red]{b.art}[/red]  {escape(b.text)}")
    console.print(
        f"[dim]Kopf zum Notieren: {p.kopf_nr}:{p.kopf_hash[:16]} — beim nächsten Mal "
        "mit --kopf prüfen, ob davor etwas verschwunden ist.[/dim]"
    )
    if not p.in_ordnung:
        raise typer.Exit(1)


@befehl.command("uebernehmen")
def uebernehmen(
    von: str | None = typer.Option(
        None,
        help="Wer übernimmt (sonst ACCOUNTI_BENUTZER bzw. Anmeldename; mit "
        "eingerichteten Benutzern: Rolle und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Buchungen, Belege und Sperren von vor dem Journal als Bestand eintragen."""
    from accounti.models.auth import Recht
    from accounti.pruefung.journal import UebernahmeError, uebernehme_bestand
    from accounti.pruefung.person import aktuelle_person

    # Was ohne Journaleintrag vorgefunden wird, gilt danach als Bestand. Ein Schritt
    # des Upgrades (Betrieb, nicht Buchhaltung): verwalten (verwalter), mit
    # Einmalcode — und nur, solange das Journal außer Übernahmen leer ist
    with (
        handelnde_person(db, config, Recht.VERWALTEN, von) as person,
        sitzung(db)() as s,
    ):
        try:
            anzahl = uebernehme_bestand(s, person=aktuelle_person(person))
        except UebernahmeError as fehler:
            ende(str(fehler))
        s.commit()
    console.print(
        f"[green]{anzahl} Objekte als Bestand ins Journal übernommen.[/green]"
    )
