"""``accounti nachfordern`` — fehlende Belege als Aufgabe anfordern (Spec 4.2)."""

from __future__ import annotations

from datetime import date

import typer
from rich.markup import escape

from accounti.befehle import DB_OPTION, KONFIG_OPTION, console, laufsperre_oder_ende
from accounti.befehle._anlagen_abschluss import datum, ende, sitzung

NAME = "nachfordern"
befehl = typer.Typer(
    help="Fehlende Belege als Aufgabe nachfordern; Anfrage beim Lieferanten (Entwurf)."
)


@befehl.callback(invoke_without_command=True)
def nachfordern(
    ctx: typer.Context,
    period: str | None = typer.Option(None, "--period", help="nur Umsätze aus JJJJ-MM"),
    stichtag: str | None = typer.Option(None, help="Stichtag (sonst heute)"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Aufgaben „Beleg fehlt“ aus der Prüfregel anlegen, Entfallenes schließen."""
    if ctx.invoked_subcommand is not None:
        return
    from accounti.aufgaben import AufgabenError, lade_aufgaben_einstellungen
    from accounti.aufgaben.prueflaeufe import fuehre_prueflaeufe_aus
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.pruefung.nachforderung import ART, mit_pruefeinstellungen

    try:
        aufgaben = lade_aufgaben_einstellungen(config)
        pruefung = lade_pruefung(config)
    except KonfigurationError as fehler:
        ende(str(fehler))
    tag = datum(stichtag, "--stichtag") if stichtag else date.today()
    # derselbe Prüflauf beleg_fehlt wie in aufgaben lauf: nie zwei gleichzeitig
    with (
        laufsperre_oder_ende(db, "aufgaben"),
        sitzung(db)() as s,
        mit_pruefeinstellungen(pruefung),
    ):
        try:
            (lauf,) = fuehre_prueflaeufe_aus(
                s, aufgaben, stichtag=tag, namen=[ART], zeitraum=period
            )
            s.commit()
        except AufgabenError as fehler:
            ende(str(fehler))
    a = lauf.abgleich
    offen = a.neu + a.aktualisiert + a.unveraendert + a.wieder_offen
    console.print(
        f"[bold]Beleg fehlt:[/bold] {len(a.neu)} neu, {len(a.wieder_offen)} wieder "
        f"offen, {len(offen)} offen, [green]{len(a.hinfaellig)} hinfällig[/green] "
        "(Beleg eingetroffen oder belegfrei)"
    )
    for x in a.neu + a.wieder_offen:
        console.print(f"  #{x.nr} {escape(x.titel)}")
    if offen:
        console.print(
            "[dim]Erinnerungen: accounti aufgaben erinnern · Anfrage an den "
            "Lieferanten: accounti nachfordern anfrage <Umsatz-ID>[/dim]"
        )


@befehl.command("anfrage")
def anfrage(
    umsatz: str = typer.Argument(help="(Anfang der) Umsatz-ID"),
    an: str | None = typer.Option(
        None, "--an", help="Empfänger (sonst Kontakt-E-Mail)"
    ),
    senden: bool = typer.Option(
        False, "--senden", help="diese eine Anfrage wirklich per E-Mail senden"
    ),
    von: str | None = typer.Option(None, help="Wer fordert an"),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Anfrage nach dem Beleg — Entwurf aus der Vorlage; gesendet nur mit --senden."""
    from accounti.erechnung.versand import SmtpVersand, VersandError, lade_versand
    from accounti.konfiguration import KonfigurationError, lade_eigene_firma
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.pruefung.nachforderung import (
        NachforderungError,
        baue_anfrage,
        sende_anfrage,
    )
    from accounti.pruefung.person import aktuelle_person

    try:
        pruefung = lade_pruefung(config)
        firma = lade_eigene_firma(config)
        versand = lade_versand(config) if senden else None
    except KonfigurationError as fehler:
        ende(str(fehler))
    with sitzung(db)() as s:
        try:
            entwurf = baue_anfrage(
                s,
                umsatz,
                pruefung,
                firma.name if firma else "",
                antwort=(versand.antwort_an or versand.absender) if versand else None,
                an=an,
            )
        except NachforderungError as fehler:
            ende(str(fehler))
        console.print(f"[bold]An:[/bold] {escape(entwurf.an or '— (keine Adresse)')}")
        console.print(f"[bold]Betreff:[/bold] {escape(entwurf.betreff)}")
        console.print(escape(entwurf.text))
        if not senden:
            console.print(
                "[dim]Entwurf — nichts gesendet. Senden: --senden (SMTP aus "
                "'versand').[/dim]"
            )
            return
        assert versand is not None
        try:
            sende_anfrage(
                s, entwurf, SmtpVersand(versand), versand.absender, aktuelle_person(von)
            )
            s.commit()
        except (NachforderungError, VersandError, OSError) as fehler:
            ende(f"nicht gesendet: {fehler}")
    console.print(f"[green]Anfrage gesendet an {escape(entwurf.an or '')}.[/green]")
