"""``accounti regeln …`` — gelernte Kontierungsregeln der Gesellschaft (Baustein 10b).

Gelernte Regeln liegen in der Datenbank (``kontierungsregeln``), greifen vor der
Regeldatei und nur in der Zahlungsrichtung ihres Quellumsatzes. Sie werden nicht
bearbeitet, sondern deaktiviert und neu gelernt (``accounti lerne`` bzw. ``korrigiere
--lernen``); beides steht im Journal.
"""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.table import Table

from accounti.befehle import (
    DB_OPTION,
    KONFIG_OPTION,
    console,
    fachprobe,
    handelnde_person,
)
from accounti.befehle._anlagen_abschluss import ende, sitzung

NAME = "regeln"
befehl = typer.Typer(
    help="Gelernte Kontierungsregeln: anzeigen, deaktivieren, aus der Regeldatei "
    "übernehmen.",
    no_args_is_help=True,
)


@befehl.command("liste")
def liste(
    alle: bool = typer.Option(False, "--alle", help="auch deaktivierte"),
    db: str = DB_OPTION,
) -> None:
    """Gelernte Regeln in ihrem Vorrang: die neueste zuerst, aus der Regeldatei
    übernommene dahinter."""
    from accounti.klassifikation.lernen import lade_gelernte_regeln

    with sitzung(db)() as s:
        regeln = [g for g in lade_gelernte_regeln(s) if alle or g.regel.aktiv]
    if not regeln:
        console.print("[dim]Keine gelernten Regeln.[/dim]")
        return
    tabelle = Table(title="Gelernte Regeln")
    for spalte in ("ID", "Name", "Muster", "Richtung", "Soll", "Haben", "St"):
        tabelle.add_column(spalte)
    tabelle.add_column("Treffer", justify="right")
    tabelle.add_column("Angelegt")
    tabelle.add_column("Stand")
    for g in regeln:
        r = g.regel
        muster = r.muster if r.ist_text else f"/{r.muster}/"
        stand = (
            "aktiv"
            if r.aktiv
            else f"aus ({r.deaktiviert_von}: {r.deaktiviert_grund or '—'})"
        )
        tabelle.add_row(
            str(r.id)[:8],
            escape(r.name),
            escape(muster),
            r.richtung.value if r.richtung else "beide",
            r.soll_konto,
            r.haben_konto,
            str(r.steuer_schluessel or "—"),
            str(g.treffer),
            f"{r.angelegt_am:%d.%m.%Y} {escape(r.angelegt_von)}",
            escape(stand),
        )
    console.print(tabelle)


@befehl.command("deaktivieren")
def deaktivieren(
    regel: str = typer.Argument(help="Name oder Anfang der ID"),
    grund: str = typer.Option(..., "--grund", help="Begründung (steht im Journal)"),
    von: str | None = typer.Option(
        None,
        help="Wer deaktiviert (sonst ACCOUNTI_BENUTZER bzw. Anmeldename; mit "
        "eingerichteten Benutzern: Rolle und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """Regel abschalten — sie greift ab dem nächsten Lauf nicht mehr."""
    from sqlalchemy.orm import Session

    from accounti.db.repo_kontierung import finde_kontierungsregel
    from accounti.klassifikation.lernen import RegelError, deaktiviere
    from accounti.models.auth import Recht
    from accounti.models.kontierung import Kontierungsregel
    from accounti.pruefung.person import aktuelle_person

    def ausfuehren(s: Session, wer: str) -> Kontierungsregel:
        r = finde_kontierungsregel(s, regel)
        return deaktiviere(s, r.id, wer, grund)

    # Fachprobe vor dem Einmalcode: ein unbekannter Name oder eine schon deaktivierte
    # Regel verbraucht ihn nicht (gw-storno N3, gw2-betrieb B-1)
    probe = fachprobe(
        sitzung(db),
        lambda s: ausfuehren(s, aktuelle_person(von)),
        (RegelError, ValueError),
        lambda f: ende(str(f)),
    )
    with (
        handelnde_person(db, config, Recht.REGELN_LERNEN, von, vorab=probe) as person,
        sitzung(db)() as s,
    ):
        try:
            aus = ausfuehren(s, aktuelle_person(person))
            s.commit()
        except (RegelError, ValueError) as fehler:
            ende(str(fehler))
    console.print(f"[green]Regel {escape(aus.name)} deaktiviert.[/green]")


NAME_OPTION = typer.Option(
    None,
    "--name",
    help="auch diesen Eintrag übernehmen (mehrfach; z. B. vor 10b mit accounti lerne "
    "--name angelegte Regeln ohne Präfix gelernt_)",
)


@befehl.command("uebernehmen")
def uebernehmen(
    probe: bool = typer.Option(
        False, "--probe", help="nur zeigen, was übernommen würde"
    ),
    name: list[str] | None = NAME_OPTION,
    von: str | None = typer.Option(
        None,
        help="Wer übernimmt (sonst ACCOUNTI_BENUTZER bzw. Anmeldename; mit "
        "eingerichteten Benutzern: Rolle und Einmalcode)",
    ),
    db: str = DB_OPTION,
    config: str = KONFIG_OPTION,
) -> None:
    """``gelernt_*``-Einträge der Regeldatei (und mit ``--name`` gewählte) in die
    Datenbank holen — vor 10b gelernte Regeln standen am Dateiende und griffen nach
    falsch treffenden eigenen Regeln. Übernommene Regeln stehen hinter den schon
    gelernten. Die Datei bleibt unverändert; die Einträge danach von Hand löschen.
    Einträge mit pruefen/confidence und Umbuchungen bleiben in der Datei."""
    from sqlalchemy.orm import Session

    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.abschluss.kontenrahmen import (
        KontenrahmenError,
        mit_eingerichteten_konten,
    )
    from accounti.betrieb.kontext import regeln_datei
    from accounti.klassifikation.lernen import (
        RegelError,
        Uebernahme,
        uebernehme_aus_datei,
    )
    from accounti.konfiguration import KonfigurationError, lade_buchhaltung
    from accounti.models.auth import Recht
    from accounti.pruefung.person import aktuelle_person

    datei = regeln_datei()
    try:  # Richtung aus der Bankseite: Bankkonto und Geldkonten der Gesellschaft
        buchhaltung = lade_buchhaltung(config)
        bank_konto = buchhaltung.bank_konto
        kontenrahmen = lade_abschluss(config).lade_kontenrahmen()
    except (KonfigurationError, KontenrahmenError) as fehler:
        ende(str(fehler))

    def ausfuehren(s: Session, wer: str, nur_probe: bool) -> Uebernahme:
        # eingerichtete Bank- und Kartenkonten zählen als Geldkonten
        return uebernehme_aus_datei(
            s, datei, wer, bank_konto=bank_konto,
            kontenrahmen=mit_eingerichteten_konten(kontenrahmen, s), probe=nur_probe,
            namen=name or (), buchhaltung=buchhaltung,
        )  # fmt: skip

    fachfehler = (RegelError, KonfigurationError)
    if probe:
        with sitzung(db)() as s:
            try:
                ergebnis = ausfuehren(s, "probe", True)
            except fachfehler as fehler:
                ende(str(fehler))
            finally:
                s.rollback()
    else:
        # Übernommene Regeln buchen künftig automatisch wie gelernte: buchen und
        # Regeln lernen (wie korrigiere --lernen) — der verwalter allein nicht. Erst
        # die Fachprobe (Datei lesbar, Namen frei), dann der Einmalcode
        vorab = fachprobe(
            sitzung(db),
            lambda s: ausfuehren(s, aktuelle_person(von), True),
            fachfehler,
            lambda f: ende(str(f)),
        )
        with (
            handelnde_person(
                db, config, Recht.BUCHEN, von, (Recht.REGELN_LERNEN,), vorab
            ) as person,
            sitzung(db)() as s,
        ):
            try:
                ergebnis = ausfuehren(s, aktuelle_person(person), False)
                s.commit()
            except fachfehler as fehler:
                ende(str(fehler))
    verb = "würde übernehmen" if probe else "übernommen"
    console.print(
        f"{len(ergebnis.uebernommen)} Regeln {verb} aus {escape(str(datei))}"
        + (
            f": {escape(', '.join(ergebnis.uebernommen))}"
            if ergebnis.uebernommen
            else ""
        )
    )
    if ergebnis.uebersprungen:
        console.print(
            "[yellow]Schon vorhanden (übersprungen): "
            f"{escape(', '.join(ergebnis.uebersprungen))}[/yellow]"
        )
    if ergebnis.ungueltig:
        console.print(
            f"[red]Ungültig (nicht übernommen): "
            f"{escape(', '.join(ergebnis.ungueltig))}[/red]"
        )
        for regelname in ergebnis.ungueltig:
            if grund := ergebnis.gruende.get(regelname):
                console.print(f"[red]  {escape(grund)}[/red]")
    if ergebnis.ohne_richtung:
        console.print(
            "[yellow]Ohne erkennbare Bankseite (gelten für Ein- und Ausgänge): "
            f"{escape(', '.join(ergebnis.ohne_richtung))} — bei Bedarf deaktivieren "
            "und mit accounti lerne --richtung neu anlegen[/yellow]"
        )
    if ergebnis.mit_pruefkennzeichen:
        console.print(
            "[yellow]Bleiben in der Regeldatei (pruefen bzw. confidence unter 1 — "
            "eine gelernte Regel hat kein eigenes Prüfkennzeichen und buchte "
            f"automatisch): {escape(', '.join(ergebnis.mit_pruefkennzeichen))}. Sie "
            "greifen dort wie bisher, jetzt hinter den gelernten Regeln.[/yellow]"
        )
    if ergebnis.umbuchungen:
        console.print(
            "[yellow]Bleiben in der Regeldatei (Soll und Haben sind Geldkonten — aus "
            f"einer Umbuchung wird keine gelernte Regel): "
            f"{escape(', '.join(ergebnis.umbuchungen))}[/yellow]"
        )
    if ergebnis.eigene:
        console.print(
            "[dim]Weitere Einträge bleiben eigene Regeln der Datei (greifen nach den "
            f"gelernten): {escape(', '.join(ergebnis.eigene))} — mit --name NAME "
            "übernehmen, z. B. vor 10b mit accounti lerne --name gelernte.[/dim]"
        )
    if ergebnis.unbekannt:
        console.print(
            f"[red]Nicht in der Regeldatei: {escape(', '.join(ergebnis.unbekannt))}"
            "[/red]"
        )
    if ergebnis.uebernommen and not probe:
        console.print(
            "[dim]Die Einträge stehen weiter in der Regeldatei — dort von Hand löschen "
            "(accounti schreibt die Datei nicht).[/dim]"
        )
